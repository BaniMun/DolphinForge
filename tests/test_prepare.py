"""Tests for the input-validation step of .github/workflows/build.yml.

Runs the embedded Python exactly as the workflow does, with the same env vars.
usage: python3 tests/test_prepare.py
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
wf = yaml.safe_load((ROOT / ".github/workflows/build.yml").read_text())
step = next(s for s in wf["jobs"]["prepare"]["steps"] if s.get("id") == "parse")
script = step["run"].split("<<'EOF'\n", 1)[1].rsplit("EOF", 1)[0]


def run(repo, ref="", app_dir="", fw="official,momentum,unleashed", channel="release", rid="abc123-xyz", versions=""):
    with tempfile.NamedTemporaryFile("r+", delete=False) as out:
        env = dict(os.environ, IN_REPO=repo, IN_REF=ref, IN_DIR=app_dir, IN_FW=fw,
                   IN_CHANNEL=channel, IN_ID=rid, IN_VERSIONS=versions, GITHUB_OUTPUT=out.name)
        p = subprocess.run([sys.executable, "-I", "-c", script], env=env, capture_output=True, text=True)
        outputs = dict(line.split("=", 1) for line in open(out.name).read().splitlines() if "=" in line)
    os.unlink(out.name)
    return p.returncode, outputs, p.stdout


fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += 0 if cond else 1


code, out, _ = run("https://github.com/pwschattenberg/cfs-tag-writer.git/")
m = json.loads(out.get("matrix", "{}"))
check("URL normalised to owner/repo", code == 0 and out.get("repo") == "pwschattenberg/cfs-tag-writer")
check("three firmwares in matrix", [i["fw"] for i in m["include"]] == ["official", "momentum", "unleashed"])
check("official has no index url", m["include"][0]["index_url"] == "")
check("momentum index url", "momentum-fw.dev" in m["include"][1]["index_url"])
check("unleashed index url", "unleashedflip.com" in m["include"][2]["index_url"])

code, out, _ = run("owner/app", fw="Momentum, momentum", ref="v1.2", app_dir="apps/foo/")
m = json.loads(out["matrix"])
check("dedupe + case-insensitive firmware", code == 0 and [i["fw"] for i in m["include"]] == ["momentum"])
check("ref and dir passed through", m["include"][0]["ref"] == "v1.2" and m["include"][0]["app_dir"] == "apps/foo")

check("reject non-GitHub repo", run("https://gitlab.com/a/b")[0] != 0)
check("reject shell injection in repo", run("a/b; rm -rf /")[0] != 0)
check("reject unknown firmware", run("a/b", fw="roguemaster")[0] != 0)
check("reject empty firmware list", run("a/b", fw=" , ")[0] != 0)
check("reject .. in app dir", run("a/b", app_dir="../../etc")[0] != 0)
check("reject bad ref", run("a/b", ref="main;echo")[0] != 0)
check("reject bad channel", run("a/b", channel="nightly")[0] != 0)
check("reject bad request id", run("a/b", rid="x")[0] != 0)
check("dev channel accepted", run("a/b", channel="dev")[0] == 0)

# archived versions -> SDK from each firmware's official archive
code, out, _ = run("a/b", versions="official=1.3.4, momentum=mntm-010,unleashed=unlshd-090")
inc = {i["fw"]: i for i in json.loads(out["matrix"])["include"]}
check("official archive url",
      inc["official"]["sdk_url"] == "https://update.flipperzero.one/builds/firmware/1.3.4/flipper-z-f7-sdk-1.3.4.zip")
check("momentum archive url",
      inc["momentum"]["sdk_url"] == "https://up.momentum-fw.dev/builds/firmware/mntm-010/flipper-z-f7-sdk-mntm-010.zip")
check("unleashed archive url",
      inc["unleashed"]["sdk_url"] == "https://github.com/DarkFlippers/unleashed-firmware/releases/download/unlshd-090/flipper-z-f7-sdk-unlshd-090.zip")
check("version labels", [inc[f]["version"] for f in ("official", "momentum", "unleashed")] == ["1.3.4", "mntm-010", "unlshd-090"])

code, out, _ = run("a/b", fw="official,momentum", versions="momentum=mntm-011,official=latest")
inc = {i["fw"]: i for i in json.loads(out["matrix"])["include"]}
check("latest keeps index build", inc["official"]["sdk_url"] == "" and inc["official"]["version"] == "latest")
check("only chosen fw archived", inc["momentum"]["sdk_url"].endswith("mntm-011.zip"))

check("reject momentum version on official", run("a/b", versions="official=mntm-010")[0] != 0)
check("reject injected version", run("a/b", versions="unleashed=unlshd-090/../../x")[0] != 0)
check("reject unknown fw in versions", run("a/b", versions="xtreme=1.0")[0] != 0)
check("upload branch ref accepted", run("me/builder", ref="upload/mh3k2-ab12cd")[0] == 0)

jobs = wf["jobs"]
check("cleanup only for upload branches", "startsWith(inputs.ref, 'upload/')" in jobs["cleanup"]["if"])
check("cleanup runs after everything", jobs["cleanup"]["needs"] == ["prepare", "build", "release"])
check("build job is read-only", jobs["build"]["permissions"] == {"contents": "read"})
publish = next(st["run"] for st in jobs["release"]["steps"] if st.get("name") == "Publish release")
check("release tag points at the files commit", '--target "$commit"' in publish)
check("files commit has no parents", "parents: []" in publish)

# issue forms the page links to, with the field ids it fills in
forms = {f.name: yaml.safe_load(f.read_text()) for f in (ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml") if f.name != "config.yml"}
ids = lambda form: {b.get("id") for b in form["body"]}
check("feedback form fields", {"feedback", "device"} <= ids(forms["feedback.yml"]))
check("build problem form fields", {"app", "firmware", "error", "run"} <= ids(forms["build-problem.yml"]))

check("build request form fields", {"repo", "ref", "folder", "firmwares", "versions", "channel"} <= ids(forms["build-request.yml"]))
check("build request form labels it", forms["build-request.yml"]["labels"] == ["build-request"])

# ---- builds requested through issues (.github/workflows/issue-build.yml) ----
dispatch_inputs = wf[True]["workflow_dispatch"]["inputs"]  # YAML reads "on" as True
call_inputs = wf[True]["workflow_call"]["inputs"]
check("build.yml callable with the same inputs", set(call_inputs) == set(dispatch_inputs))
check("callable inputs are strings", all(v.get("type") == "string" for v in call_inputs.values()))

iwf = yaml.safe_load((ROOT / ".github/workflows/issue-build.yml").read_text())
ijobs = iwf["jobs"]
check("issue workflow runs on opened issues", iwf[True] == {"issues": {"types": ["opened"]}})
check("only for build-request issues", "build-request" in ijobs["accept"]["if"])
check("accept job can only touch issues", ijobs["accept"]["permissions"] == {"issues": "write"})
check("build reuses build.yml", ijobs["build"]["uses"] == "./.github/workflows/build.yml")
check("build gets request id from issue", ijobs["build"]["with"]["request_id"] == "${{ needs.accept.outputs.request_id }}")
check("report runs even if the build failed", "always()" in ijobs["report"]["if"])
issue_env = ijobs["accept"]["steps"][0]["env"]
check("issue text only through env", issue_env["ISSUE_BODY"] == "${{ github.event.issue.body }}"
      and "github.event.issue.body" not in ijobs["accept"]["steps"][0]["run"])


def script_of(step):
    return step["run"].split("<<'EOF'\n", 1)[1].rsplit("EOF", 1)[0]


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"args": args, "stdin": stdin}) + "\\n")
if args[:1] == ["api"] and any("/issues" in a for a in args):
    print(os.environ.get("FAKE_ISSUES", "[]"))
elif args[:2] == ["release", "view"]:
    assets = os.environ.get("FAKE_ASSETS")
    if assets is None:
        sys.exit(1)
    print(json.dumps({"assets": json.loads(assets)}))
"""


def run_script(code_text, env_extra):
    with tempfile.TemporaryDirectory() as d:
        gh = pathlib.Path(d) / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        log = pathlib.Path(d) / "log.jsonl"
        log.write_text("")
        out = pathlib.Path(d) / "out.txt"
        out.write_text("")
        env = dict(os.environ, PATH=f"{d}:{os.environ['PATH']}", FAKE_LOG=str(log), GITHUB_OUTPUT=str(out),
                   GH_REPO="me/DolphinForge", ISSUE_NUMBER="42", AUTHOR="someone", RUN_URL="https://run/1",
                   DAILY_LIMIT="5", **env_extra)
        p = subprocess.run([sys.executable, "-I", "-c", code_text], env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
        calls = [json.loads(l) for l in log.read_text().splitlines()]
    return p.returncode, outputs, calls, p.stderr


accept = script_of(ijobs["accept"]["steps"][0])


def form(repo="https://github.com/owner/app", ref="_No response_", folder="_No response_",
         fws="official, momentum, unleashed", versions="_No response_", channel="release"):
    return (f"### App repo\n\n{repo}\n\n### Branch or tag\n\n{ref}\n\n### App folder\n\n{folder}\n\n"
            f"### Firmwares\n\n{fws}\n\n### Firmware versions\n\n{versions}\n\n### SDK channel\n\n{channel}\n")


import datetime
now = datetime.datetime.now(datetime.timezone.utc)
recent = lambda n: json.dumps([{"created_at": (now - datetime.timedelta(hours=h + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")}
                               for h in range(n)])

code, o, calls, err = run_script(accept, {"ISSUE_BODY": form(), "FAKE_ISSUES": recent(1)})
check("issue form accepted", code == 0 and o.get("ok") == "true" and o.get("repo") == "https://github.com/owner/app")
check("empty fields become empty", o.get("ref") == "" and o.get("app_dir") == "" and o.get("versions") == "")
check("firmwares normalised", o.get("firmwares") == "official,momentum,unleashed")
check("request id from issue number", o.get("request_id") == "issue-42")
check("starts with a reply", any(c["args"][:2] == ["issue", "comment"] and "Building" in c["stdin"] for c in calls))
check("issue stays open while building", not any(c["args"][:2] == ["issue", "close"] for c in calls))

code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(repo="https://github.com/owner/app/tree/dev/apps/cfs",
                                                          fws="Momentum", versions="momentum=mntm-010"),
                                       "FAKE_ISSUES": recent(1)})
check("tree link split into repo/ref/folder", (o.get("repo"), o.get("ref"), o.get("app_dir")) == ("owner/app", "dev", "apps/cfs"))
check("chosen firmware and version", o.get("firmwares") == "momentum" and o.get("versions") == "momentum=mntm-010")

code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(), "FAKE_ISSUES": recent(6)})
check("6th build in a day refused", o.get("ok") == "false"
      and any("limit of 5" in c["stdin"] for c in calls) and any(c["args"][:2] == ["issue", "close"] for c in calls))
code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(), "FAKE_ISSUES": recent(5)})
check("5th build in a day allowed", o.get("ok") == "true")
old = json.dumps([{"created_at": (now - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")}] * 9)
code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(), "FAKE_ISSUES": old})
check("older requests don't count", o.get("ok") == "true")
code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(repo="_No response_"), "FAKE_ISSUES": "[]"})
check("missing repo closes the issue", o.get("ok") == "false" and any(c["args"][:2] == ["issue", "close"] for c in calls))
code, o, calls, _ = run_script(accept, {"ISSUE_BODY": form(repo="a/b; rm -rf /"), "FAKE_ISSUES": "[]"})
check("odd repo text left for build.yml to reject", code == 0 and run(o.get("repo", ""))[0] != 0)

report = script_of(ijobs["report"]["steps"][0])
assets = json.dumps([{"name": "my_app-official-latest.fap", "url": "https://dl/o"},
                     {"name": "my_app-momentum-latest.fap", "url": "https://dl/m"}])
code, o, calls, err = run_script(report, {"TAG": "build-issue-42", "FIRMWARES": "official,momentum,unleashed",
                                          "FAKE_ASSETS": assets})
reply = next((c["stdin"] for c in calls if c["args"][:2] == ["issue", "comment"]), "")
check("report lists the files", code == 0 and "[my_app-official-latest.fap](https://dl/o)" in reply and "| Momentum |" in reply)
check("report names the firmware that failed", "Didn't build for: Unleashed" in reply)
check("issue closed as completed", any(c["args"][:2] == ["issue", "close"] and "completed" in c["args"] for c in calls))
code, o, calls, err = run_script(report, {"TAG": "build-issue-42", "FIRMWARES": "official"})
reply = next((c["stdin"] for c in calls if c["args"][:2] == ["issue", "comment"]), "")
check("no release: says it didn't build", code == 0 and "didn't build for any firmware" in reply
      and any(c["args"][:2] == ["issue", "close"] and "not planned" in c["args"] for c in calls))

# ---- daily cleanup (.github/workflows/cleanup.yml) ----
cwf = yaml.safe_load((ROOT / ".github/workflows/cleanup.yml").read_text())
check("cleanup runs daily", "schedule" in cwf[True] and "workflow_dispatch" in cwf[True])
cjob = cwf["jobs"]["cleanup"]
check("cleanup keeps 30 days", cjob["env"]["KEEP_DAYS"] == "30")
crun = cjob["steps"][0]["run"]
check("cleanup only touches build-* tags", 'startswith(\\"build-\\")' in crun and "^build-[A-Za-z0-9-]{6,64}$" in crun)
check("cleanup removes the tag too", "--cleanup-tag" in crun)

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
