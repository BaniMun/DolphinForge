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

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
