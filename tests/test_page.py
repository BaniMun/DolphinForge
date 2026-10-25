"""Headless browser tests for index.html with a mocked GitHub API.

usage: python3 tests/test_page.py [screenshot_dir]
"""
import base64
import io
import json
import pathlib
import re
import sys
import tempfile
import zipfile

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = (ROOT / "index.html").as_uri()
SHOTS = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += 0 if cond else 1


class FakeGitHub:
    """Stateful fake of the few endpoints the page uses."""

    def __init__(self, dispatch_status=204, blob_status=201):
        self.dispatch_status = dispatch_status
        self.blob_status = blob_status
        self.blobs = []
        self.tree = None
        self.commit = None
        self.created_ref = None
        self.deleted_ref = None
        self.dispatched = None
        self.run_polls = 0
        self.list_polls = 0

    def handle(self, route):
        req = route.request
        url = req.url
        path = re.sub(r"^https://api\.github\.com", "", url.split("?")[0])
        auth = req.headers.get("authorization", "")

        def reply(body, status=200):
            route.fulfill(status=status, content_type="application/json",
                          headers={"access-control-allow-origin": "*"}, body=json.dumps(body))

        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers={
                "access-control-allow-origin": "*",
                "access-control-allow-headers": "*",
                "access-control-allow-methods": "GET,POST"})
        releases = {
            "/repos/flipperdevices/flipperzero-firmware/releases": [
                {"tag_name": "1.5.1"}, {"tag_name": "1.5.1-rc", "prerelease": True}, {"tag_name": "1.4.3"}],
            "/repos/Next-Flip/Momentum-Firmware/releases": [
                {"tag_name": "mntm-012"}, {"tag_name": "mntm-011"}, {"tag_name": "mntm-010"}],
            "/repos/DarkFlippers/unleashed-firmware/releases": [
                {"tag_name": "unlshd-094"}, {"tag_name": "unlshd-093"}, {"tag_name": "nightly", "draft": True}],
        }
        apps = {
            "owner/app": ("main", {"dev": ["apps/cfs/application.fam", "README.md"]}),
            "owner/one": ("main", {"main": ["application.fam", "src/app.c"]}),
            "owner/multi": ("master", {"master": ["a/application.fam", "b/application.fam"]}),
        }
        m = re.match(r"^/repos/(owner/[a-z]+)(/.*)?$", path)
        if m and m.group(1) not in apps:
            return reply({"message": "Not Found"}, 404)
        if m:
            default, trees = apps[m.group(1)]
            rest = m.group(2) or ""
            if rest == "":
                return reply({"default_branch": default})
            if rest == "/branches":
                return reply([{"name": b} for b in trees])
            t = re.match(r"^/git/trees/([^/]+)$", rest)
            if t and t.group(1) in trees:
                return reply({"tree": [{"type": "blob", "path": x} for x in trees[t.group(1)]]})
            if rest.endswith("application.fam"):
                fam = 'App(appid="cfs_tag_writer", name="CFS Tag Writer", apptype=FlipperAppType.EXTERNAL)'
                return reply({"content": base64.b64encode(fam.encode()).decode()})
            return reply({"message": "Not Found"}, 404)
        if path in releases:
            if auth and auth != "Bearer good-token":
                return reply({"message": "Bad credentials"}, 401)
            return reply(releases[path])
        if auth != "Bearer good-token":
            return reply({"message": "Bad credentials"}, 401)
        if path == "/repos/me/builder":
            return reply({"default_branch": "main"})
        if path == "/repos/me/builder/git/blobs" and req.method == "POST":
            if self.blob_status != 201:
                return reply({"message": "Resource not accessible by personal access token"}, self.blob_status)
            body = json.loads(req.post_data)
            self.blobs.append(base64.b64decode(body["content"]))
            return reply({"sha": f"blob{len(self.blobs)}"}, 201)
        if path == "/repos/me/builder/git/trees" and req.method == "POST":
            self.tree = json.loads(req.post_data)["tree"]
            return reply({"sha": "tree1"}, 201)
        if path == "/repos/me/builder/git/commits" and req.method == "POST":
            self.commit = json.loads(req.post_data)
            return reply({"sha": "commit1"}, 201)
        if path == "/repos/me/builder/git/refs" and req.method == "POST":
            self.created_ref = json.loads(req.post_data)
            return reply({"ref": self.created_ref["ref"]}, 201)
        if path.startswith("/repos/me/builder/git/refs/heads/") and req.method == "DELETE":
            self.deleted_ref = path
            return route.fulfill(status=204, headers={"access-control-allow-origin": "*"})
        if path.endswith("/dispatches") and req.method == "POST":
            if self.dispatch_status != 204:
                return reply({"message": "nope"}, self.dispatch_status)
            self.dispatched = json.loads(req.post_data)
            return route.fulfill(status=204, headers={"access-control-allow-origin": "*"})
        rid = self.dispatched["inputs"]["request_id"] if self.dispatched else "none"
        if path == "/repos/me/builder/actions/workflows/build.yml/runs":
            self.list_polls += 1
            runs = [] if self.list_polls == 1 else [
                {"id": 1, "display_title": "build other x/y", "html_url": "u0"},
                {"id": 77, "display_title": f"build {rid} owner/app", "html_url": "https://gh/run/77"}]
            return reply({"workflow_runs": runs})
        if path == "/repos/me/builder/actions/runs/77":
            self.run_polls += 1
            done = self.run_polls >= 2
            return reply({"id": 77, "status": "completed" if done else "in_progress",
                          "html_url": "https://gh/run/77"})
        if path == "/repos/me/builder/actions/runs/77/jobs":
            done = self.run_polls >= 2
            return reply({"jobs": [
                {"id": 1, "name": "prepare", "status": "completed", "conclusion": "success", "html_url": "j1"},
                {"id": 2, "name": "Official", "status": "completed", "conclusion": "success", "html_url": "j2"},
                {"id": 3, "name": "Momentum", "status": "completed" if done else "in_progress",
                 "conclusion": "failure" if done else None, "html_url": "https://gh/job/3"},
                {"id": 4, "name": "Unleashed", "status": "completed", "conclusion": "success", "html_url": "j4"},
            ]})
        if path == "/repos/me/builder/check-runs/3/annotations":
            return reply([{"annotation_level": "failure", "message": "src/app.c:12: error: unknown type <Foo>"}])
        if path == f"/repos/me/builder/releases/tags/build-{rid}":
            return reply({"assets": [
                {"name": "cfs_tag_writer-official.fap", "size": 20480, "browser_download_url": "https://dl/o.fap"},
                {"name": "cfs_tag_writer-unleashed.fap", "size": 20992, "browser_download_url": "https://dl/u.fap"},
                {"name": "notes.txt", "size": 1, "browser_download_url": "https://dl/n"}]})
        return reply({"message": "Not Found"}, 404)


with sync_playwright() as p:
    browser = p.chromium.launch()

    # --- happy path (with one failing firmware) ---
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    gh = FakeGitHub()
    page.route("https://api.github.com/**", gh.handle)
    # Speed up polling: make every timer fire almost immediately.
    page.add_init_script("const _st = window.setTimeout; window.setTimeout = (f, ms, ...a) => _st(f, Math.min(ms || 0, 20), ...a);")
    page.goto(PAGE)

    check("hidden from search engines", "noindex" in (page.get_attribute("meta[name=robots]", "content") or ""))
    check("settings open when empty", page.locator("#setupDetails").get_attribute("open") is not None)
    page.wait_for_function("document.getElementById('led').dataset.led === 'error'")
    check("LED red without token", "repo and token" in page.inner_text("#ledText"))
    page.fill("#repo", "owner/app")
    page.click("#buildBtn")
    check("asks for settings first", "Repo and token" in page.inner_text("#formMsg"))
    page.wait_for_function("document.querySelector('.fw-ver[data-fw=momentum]').options.length > 1")
    opts = page.eval_on_selector_all(".fw-ver[data-fw=official] option", "els => els.map(e => e.textContent)")
    check("official latest from releases", opts == ["Latest (1.5.1)", "1.4.3"])
    uopts = page.eval_on_selector_all(".fw-ver[data-fw=unleashed] option", "els => els.map(e => e.textContent)")
    check("drafts/prereleases skipped", uopts == ["Latest (unlshd-094)", "unlshd-093"])
    page.select_option("#channel", "dev")
    check("dev disables versions", page.is_disabled(".fw-ver[data-fw=momentum]"))
    page.select_option("#channel", "release")
    page.select_option(".fw-ver[data-fw=momentum]", "mntm-010")

    page.fill("#builderRepo", "https://github.com/me/builder/")
    page.fill("#token", "good-token")
    page.click("#saveSettings")
    check("settings saved", page.inner_text("#settingsState") == "Saved")
    page.wait_for_function("document.getElementById('led').dataset.led === 'ready'")
    check("LED green when ready", page.inner_text("#ledText") == "Ready")

    page.fill("#repo", "https://github.com/owner/app/tree/dev/apps/cfs")
    page.wait_for_function("document.getElementById('repoHint').textContent.startsWith('Found')")
    check("autofill branch from link", page.input_value("#ref") == "dev")
    check("autofill folder from link", page.input_value("#appDir") == "apps/cfs")
    check("app name shown", "CFS Tag Writer (cfs_tag_writer) in apps/cfs" in page.inner_text("#repoHint"))
    page.click("#buildBtn")
    page.wait_for_selector("#files a.file", timeout=15000)

    inp = gh.dispatched["inputs"]
    check("dispatch on default branch", gh.dispatched["ref"] == "main")
    check("tree link split into repo/ref/dir",
          (inp["repo"], inp["ref"], inp["app_dir"]) == ("owner/app", "dev", "apps/cfs"))
    check("all three firmwares requested", inp["firmwares"] == "official,momentum,unleashed")
    check("archived version sent", inp["versions"] == "momentum=mntm-010")
    check("version shown in status", "mntm-010" in page.inner_text("#statusRows"))
    check("request id format", re.fullmatch(r"[a-z0-9]+-[a-z0-9]+", inp["request_id"]) is not None)
    files = page.locator("#files a.file")
    check("only .fap files listed", files.count() == 2)
    check("download link", files.first.get_attribute("href") == "https://dl/o.fap")
    rows = page.inner_text("#statusRows")
    check("official done", "Official" in rows and "Done" in rows)
    errs = page.inner_text("#errors")
    check("momentum error shown", "Failed" in rows and "Momentum didn't build" in errs and "unknown type <Foo>" in errs)
    check("error text escaped", "<Foo>" not in page.inner_html("#errors"))
    check("log link for failure", page.locator("#errors a").get_attribute("href") == "https://gh/job/3")
    check("summary on screen", page.inner_text("#lcdSummary") == "2 of 3 built")
    check("LED red after partial failure", page.get_attribute("#led", "data-led") == "fail")
    check("history shows partial", "◐" in page.inner_text("#history"))
    check("run link", page.locator("#runLink a").get_attribute("href") == "https://gh/run/77")
    check("button re-enabled", page.is_enabled("#buildBtn"))
    if SHOTS:
        page.screenshot(path=str(SHOTS / "mobile.png"), full_page=True)

    # history survives reload and settings persist
    page.reload()
    check("settings persisted", page.input_value("#token") == "good-token")
    check("history persisted", "owner/app" in page.inner_text("#history"))
    check("no JS errors", not errors)
    ctx.close()

    # --- bad token ---
    ctx = browser.new_context()
    page = ctx.new_page()
    page.route("https://api.github.com/**", FakeGitHub().handle)
    page.goto(PAGE)
    page.fill("#builderRepo", "me/builder")
    page.fill("#token", "wrong")
    page.click("#saveSettings")
    page.fill("#repo", "owner/app")
    page.click("#buildBtn")
    page.wait_for_function("!document.getElementById('formMsg').hidden")
    check("bad token message", "token is invalid" in page.inner_text("#formMsg"))
    check("LED shows rejected token", page.get_attribute("#led", "data-led") == "error")
    ctx.close()

    # --- upload scenarios ---
    tmp = pathlib.Path(tempfile.mkdtemp())

    def make_zip(name, files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for path, data in files.items():
                z.writestr(path, data)
        (tmp / name).write_bytes(buf.getvalue())
        return str(tmp / name)

    good_zip = make_zip("my_app.zip", {
        "my_app/application.fam": 'App(appid="cfs_tag_writer", name="CFS Tag Writer")',
        "my_app/app.c": "int main(void) { return 0; }\n" * 50,
        "my_app/.DS_Store": "junk",
        "__MACOSX/my_app/._app.c": "junk",
    })
    bad_zip = make_zip("no_fam.zip", {"src/app.c": "int x;"})

    def upload_page(fake):
        c = browser.new_context()
        pg = c.new_page()
        pg.route("https://api.github.com/**", fake.handle)
        pg.add_init_script("const _st = window.setTimeout; window.setTimeout = (f, ms, ...a) => _st(f, Math.min(ms || 0, 20), ...a);")
        pg.goto(PAGE)
        pg.fill("#builderRepo", "me/builder")
        pg.fill("#token", "good-token")
        pg.click("#saveSettings")
        pg.click("#srcUploadBtn")
        return c, pg

    gh = FakeGitHub()
    ctx, page = upload_page(gh)
    check("upload panel shown", page.is_visible("#drop") and not page.is_visible("#repo"))
    page.set_input_files("#upFiles", bad_zip)
    page.wait_for_function("!document.getElementById('formMsg').hidden")
    check("zip without application.fam rejected", "No application.fam" in page.inner_text("#formMsg"))
    page.set_input_files("#upFiles", good_zip)
    page.wait_for_selector("#upSummary:not([hidden])")
    summary = page.inner_text("#upSummary")
    check("upload summary", "CFS Tag Writer (cfs_tag_writer)" in summary and "2 files" in summary)
    page.click("#buildBtn")
    page.wait_for_selector("#files a.file", timeout=15000)
    check("junk files skipped, app re-rooted", sorted(t["path"] for t in gh.tree) == ["app.c", "application.fam"])
    check("file contents uploaded", any(b.startswith(b"int main") for b in gh.blobs))
    check("orphan commit", gh.commit["parents"] == [])
    rid = gh.dispatched["inputs"]["request_id"]
    check("upload branch created", gh.created_ref["ref"] == f"refs/heads/upload/{rid}")
    inp = gh.dispatched["inputs"]
    check("build points at upload branch", (inp["repo"], inp["ref"], inp["app_dir"]) == ("me/builder", f"upload/{rid}", ""))
    check("screen shows upload name", page.inner_text("#statusTitle") == "CFS Tag Writer (upload)")
    check("history shows upload", "CFS Tag Writer (upload)" in page.inner_text("#history"))
    ctx.close()

    gh = FakeGitHub(blob_status=403)
    ctx, page = upload_page(gh)
    page.set_input_files("#upFiles", good_zip)
    page.wait_for_selector("#upSummary:not([hidden])")
    page.click("#buildBtn")
    page.wait_for_function("!document.getElementById('formMsg').hidden")
    check("missing Contents write explained", "Contents set to read and write" in page.inner_text("#formMsg"))
    check("no build dispatched without upload", gh.dispatched is None)
    check("LED red when upload fails", page.get_attribute("#led", "data-led") == "error")
    ctx.close()

    # --- autofill scenarios ---
    ctx = browser.new_context()
    page = ctx.new_page()
    page.route("https://api.github.com/**", FakeGitHub().handle)
    page.goto(PAGE)
    page.fill("#repo", "owner/one")
    page.wait_for_function("document.getElementById('repoHint').textContent.startsWith('Found')")
    check("root app: folder stays empty", page.input_value("#appDir") == "")
    check("root app: default branch shown", page.get_attribute("#ref", "placeholder") == "main (default)")
    page.fill("#repo", "owner/multi")
    page.wait_for_function("document.getElementById('repoHint').textContent.includes('2 apps')")
    opts = page.eval_on_selector_all("#dirList option", "els => els.map(e => e.value)")
    check("multiple apps offered", opts == ["a", "b"])
    page.fill("#appDir", "keep/me")
    page.fill("#repo", "owner/app/tree/dev/apps/cfs")
    page.wait_for_timeout(900)
    check("typed folder not overwritten", page.input_value("#appDir") == "keep/me")
    page.fill("#repo", "owner/missing")
    page.wait_for_function("document.getElementById('repoHint').textContent.includes('public')")
    check("missing repo explained", "Can't find" in page.inner_text("#repoHint"))
    ctx.close()

    # --- input validation in the page ---
    ctx = browser.new_context()
    page = ctx.new_page()
    page.route("https://api.github.com/**", FakeGitHub().handle)
    page.goto(PAGE)
    page.fill("#builderRepo", "me/builder")
    page.fill("#token", "good-token")
    page.click("#saveSettings")
    page.fill("#repo", "not a repo")
    page.click("#buildBtn")
    check("rejects garbage repo", "owner/name" in page.inner_text("#formMsg"))
    for box in page.locator("#fwChips input").all():
        box.uncheck()
    page.fill("#repo", "owner/app")
    page.click("#buildBtn")
    check("requires a firmware", "firmware" in page.inner_text("#formMsg"))
    if SHOTS:
        page.set_viewport_size({"width": 1100, "height": 800})
        page.screenshot(path=str(SHOTS / "desktop.png"), full_page=True)
    ctx.close()
    browser.close()

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
