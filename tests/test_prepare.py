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


def run(repo, ref="", app_dir="", fw="official,momentum,unleashed", channel="release", rid="abc123-xyz"):
    with tempfile.NamedTemporaryFile("r+", delete=False) as out:
        env = dict(os.environ, IN_REPO=repo, IN_REF=ref, IN_DIR=app_dir, IN_FW=fw,
                   IN_CHANNEL=channel, IN_ID=rid, GITHUB_OUTPUT=out.name)
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

print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
sys.exit(1 if fails else 0)
