"""Run real HG053 governance checks, then append lossless C-bound captures."""
from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def main() -> int:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
    temp = Path("/private/tmp") / ("hg053-checks-" + revision)
    temp.mkdir(exist_ok=False)
    commands = [
        ("packet_refinement_audit", "uv run python docs/exec-plans/evidence/HG-053/verify_refinement.py"),
        ("authority_resolution", "uv run python tools/harness/document_index/check.py current_document_index_resolves"),
        ("harness_validation", "uv run kl check-harness"),
        ("lint", "uv run kl lint"),
        ("typecheck", "uv run kl typecheck"),
        ("unit", f"uv run kl test-unit --junitxml={temp}/unit.xml"),
        ("harness", f"uv run kl test-harness --evidence-dir {temp}/harness"),
    ]
    # No repo writes while any command is collecting/validating committed source.
    def run(entry: tuple[str, str]) -> dict:
        check_id, command = entry
        start = time.time()
        log = temp / (check_id + ".log")
        with log.open("wb") as output:
            result = subprocess.run(command.split(), cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=False)
        print(f"{check_id}: exit={result.returncode} seconds={time.time() - start:.1f}", flush=True)
        return {"check_id": check_id, "command": command, "result": "PASS" if result.returncode == 0 else "FAIL", "exit_code": result.returncode, "seconds": round(time.time() - start, 3), "log": str(log)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(run, commands))
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == revision
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
    output_root = ROOT / "docs/exec-plans/evidence/HG-053" / ("checks-" + revision)
    output_root.mkdir(exist_ok=False)
    for record in records:
        envelope = output_root / (record["check_id"] + ".json")
        subprocess.run([sys.executable, "tools/harness/compact_evidence.py", "capture", "--input", record["log"], "--output", str(envelope), "--tested", revision, "--command", record["command"], "--exit-code", str(record["exit_code"])], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        record["evidence_ref"] = str(envelope.relative_to(ROOT))
        if record["check_id"] in {"unit", "harness"}:
            paths = [temp / "unit.xml"] if record["check_id"] == "unit" else sorted((temp / "harness").iterdir())
            record["ancillary_refs"] = []
            for path in paths:
                if not path.is_file():
                    continue
                envelope = output_root / (record["check_id"] + "-" + path.name + ".json")
                subprocess.run([sys.executable, "tools/harness/compact_evidence.py", "capture", "--input", str(path), "--output", str(envelope), "--tested", revision, "--command", record["command"], "--exit-code", str(record["exit_code"])], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
                record["ancillary_refs"].append(str(envelope.relative_to(ROOT)))
    index = {"tested_commit": revision, "checks": records, "runtime_checks": "NOT_RUN", "product_claims": []}
    (output_root / "CHECK_INDEX.json").write_text(json.dumps(index, indent=2) + "\n")
    print(json.dumps(index, indent=2))
    return int(any(r["exit_code"] for r in records))


if __name__ == "__main__":
    raise SystemExit(main())
