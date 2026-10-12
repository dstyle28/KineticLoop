"""Fresh HG065 definitions and immutable component observations; no runtime gate."""
import argparse
import ast
import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

E = Path(__file__).resolve().parent
ROOT = E.parents[3]
sys.path.insert(0, str(E))
sys.path.insert(0, str(ROOT))
from portable_support import verify_delivery_sources


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--tested", required=True)
    args = parser.parse_args()
    assert args.base == "e8e93bd32a83bd2fd6bf89951863d59b37e9d2b3"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert args.tested == head
    scratch = Path(tempfile.mkdtemp(prefix="hg065-definitions-", dir="/private/tmp"))
    print("definition_observations=" + str(scratch), flush=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONPATH=str(E) + ":" + str(ROOT) + ":" + str(ROOT / "src"), HG065_OBSERVATIONS=str(scratch))
    runs = []
    def observe(name, argv, extra=None):
        actual_env = dict(env, **(extra or {}))
        start = time.monotonic_ns()
        with (scratch / (name + ".log")).open("wb") as output:
            result = subprocess.run(argv, cwd=E, env=actual_env, stdout=output, stderr=subprocess.STDOUT, timeout=180)
        meta = {"name": name, "argv": argv, "cwd": str(E), "exit_code": result.returncode,
                "elapsed_ns": time.monotonic_ns() - start, "environment": {k: actual_env[k] for k in env if k in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTEST_DISABLE_PLUGIN_AUTOLOAD", "HG065_OBSERVATIONS")},
                "sha256": hashlib.sha256((scratch / (name + ".log")).read_bytes()).hexdigest()}
        if extra: meta["environment"].update(extra)
        runs.append(meta)
        (scratch / "COMMANDS.json").write_text(json.dumps(runs, indent=2) + "\n")
        assert result.returncode == 0, (name, (scratch / (name + ".log")).read_text())
    delivery = verify_delivery_sources()
    # HG065 exact source reuse is a prospective packaging comparison, never old PASS.
    provenance = json.loads((E / "HG064_SOURCE_PROVENANCE.json").read_bytes())
    for item in provenance["sources"]:
        raw = subprocess.check_output(["git", "show", item["source_revision"] + ":" + item["source_path"]], cwd=ROOT)
        actual = (ROOT / item["destination"]).read_bytes()
        assert len(raw) == item["source_bytes"] and hashlib.sha256(raw).hexdigest() == item["source_sha256"]
        assert len(actual) == item["destination_bytes"] and hashlib.sha256(actual).hexdigest() == item["destination_sha256"]
        assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == item["source_blob"]
        changes = [{"operation": tag, "source_start": a, "source_end": b, "destination_start": c, "destination_end": d}
                   for tag, a, b, c, d in difflib.SequenceMatcher(None, raw.splitlines(), actual.splitlines(), autojunk=False).get_opcodes() if tag != "equal"]
        assert changes == item.get("changed_lines", [])
    old = provenance["source_revision"]
    original_test = subprocess.check_output(["git", "show", old + ":docs/exec-plans/evidence/HG-064/test_custody_definition.py"], cwd=ROOT)
    original_test = original_test.replace(b"HG064", b"HG065").replace(b"HG-064", b"HG-065").replace(b"hg064", b"hg065")
    assert ast.dump(ast.parse(original_test)) == ast.dump(ast.parse((E / "test_custody_definition.py").read_bytes()))
    original_fixture = json.loads(subprocess.check_output(["git", "show", old + ":docs/exec-plans/evidence/HG-064/FIXTURE_INPUTS.json"], cwd=ROOT))
    delivered_fixture = json.loads((E / "FIXTURE_INPUTS.json").read_bytes())
    assert {k: v for k, v in original_fixture.items() if k != "group"} == {k: v for k, v in delivered_fixture.items() if k != "group"}
    assert delivered_fixture["group"] == {"members": [{"path": m["path"]} for m in original_fixture["group"]["members"]], "payload_paths": original_fixture["group"]["payload_paths"]}
    observe("original-components", [sys.executable, str(E / "observe_immutable.py")])
    observe("inherited-components", [sys.executable, str(E / "observe_inherited_components.py")])
    actual = json.loads((scratch / "ACTUAL_CUSTODY_PROOF.json").read_bytes())
    assert actual == json.loads((E / "ACTUAL_CUSTODY_PROOF.json").read_bytes())
    base = [sys.executable, "-m", "pytest", "test_custody_definition.py", "-q", "--import-mode=importlib",
            "--rootdir=" + str(E), "--confcutdir=" + str(E), "-c", "/dev/null", "-p", "definition_observer",
            "-p", "no:cacheprovider", "-o", "xfail_strict=true"]
    for phase, extra in [("collection", ["--collect-only"]), ("execution", ["--junitxml=" + str(scratch / "definition-junit.xml")])]:
        observe("definition-" + phase, base + extra, {"CUSTODY_STUDY_OBSERVER": str(scratch / ("definition-" + phase + ".json"))})
    c = json.loads((scratch / "definition-collection.json").read_bytes())
    x = json.loads((scratch / "definition-execution.json").read_bytes())
    ids = json.loads((E / "FIXTURE_IDENTITIES.json").read_bytes())["identities"]
    assert len(ids) == len(set(ids)) == 156
    assert c["collections"] == x["collections"] == x["started"] == ids
    assert c["exit_code"] == x["exit_code"] == 0 and not c["errors"] and not x["errors"]
    assert not c["started"] and not c["reports"]
    assert len(x["reports"]) == 3 * len(ids)
    for phase in ("setup", "call", "teardown"):
        rows = [r for r in x["reports"] if r["when"] == phase]
        assert Counter(r["nodeid"] for r in rows) == Counter(ids)
        assert all(r["outcome"] == "passed" and r["wasxfail"] is None for r in rows)
    junit = ET.parse(scratch / "definition-junit.xml").getroot()
    cases = list(junit.iter("testcase"))
    assert len(cases) == len(ids) and not list(junit.iter("failure")) and not list(junit.iter("error")) and not list(junit.iter("skipped"))
    assert Counter((c.get("classname"), c.get("name")) for c in cases) == Counter(("test_custody_definition", i.split("::")[-1]) for i in ids)
    from tools.harness import validate_harness as v
    allowed = set(v.governance_allowed_patterns("HG-065"))
    assert len(allowed) == 11
    changed = subprocess.check_output(["git", "diff", "--name-only", args.base, args.tested], cwd=ROOT, text=True).splitlines()
    assert all(v.matches(p, list(allowed)) for p in changed)
    required = {"definitions", "validator", "unit", "harness", "lint", "typecheck", "authority", "diff"}
    assert v.HG065_REQUIRED_CHECKS == required
    for group in ("documents", "machine_readable"):
        for item in json.loads((ROOT / "CURRENT_DOCUMENT_INDEX.json").read_bytes())[group]:
            assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    # Prospective scope is packet-only: production HG058 allowlist is not implemented here.
    before = subprocess.check_output(["git", "show", args.base + ":docs/exec-plans/active/HG-058.md"], cwd=ROOT, text=True)
    after = (ROOT / "docs/exec-plans/active/HG-058.md").read_text()
    paths = lambda t: set(t.split("## Literal implementation write scope\n",1)[1].split("\nIndex edits",1)[0].strip().splitlines())
    assert paths(after) - paths(before) == {"- tools/harness/local_gate.py"} and not paths(before) - paths(after)
    report = {"base_commit": args.base, "tested_commit": args.tested, "definition_checks": 156,
              "positive_identities": ids, "delivery": delivery, "six_envelopes": 6, "physical_paths": 8,
              "original_map_components": "FRESH_COMPONENT_OBSERVATIONS_ONLY", "historical_execution": "UNVERIFIED",
              "native_whole_inventory": "NOT_RUN", "private_installed_runtime": "NOT_RUN", "observations": str(scratch), "runs": runs}
    (scratch / "DEFINITION_REPORT.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    run()
