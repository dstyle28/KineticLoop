"""Task-local immutable-data retrieval and delivery verification; no host authority."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
START = time.monotonic()
USED = {"operations": 0, "bytes": 0}
CACHE = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    assert USED["operations"] < 16384 and time.monotonic() - START <= 120
    USED["operations"] += 1
    p = subprocess.run(["git", *args], cwd=REPO, capture_output=True, timeout=10)
    USED["bytes"] += len(p.stdout) + len(p.stderr)
    assert p.returncode == 0, (args, p.returncode, p.stderr)
    assert USED["bytes"] <= 67108864 and time.monotonic() - START <= 120
    return p.stdout


def git_source(entry):
    o = entry["origin"]
    key = (o["revision"], o["path"], o.get("mode", "100644"), o["blob"], entry["bytes"], entry["sha256"])
    if key not in CACHE:
        assert len(CACHE) < 1024 and 0 <= entry["bytes"] <= 8388608
        assert sum(len(v) for v in CACHE.values()) + entry["bytes"] <= 16777216
        rows = [x for x in git("ls-tree", "-l", "-z", o["revision"], "--", o["path"]).split(b"\0") if x]
        assert len(rows) == 1
        meta, path = rows[0].split(b"\t", 1)
        mode, kind, blob, size = meta.split()
        assert mode in (b"100644", b"100755") and ("mode" not in o or mode.decode() == o["mode"])
        assert (kind, blob.decode(), int(size), path.decode()) == (b"blob", o["blob"], entry["bytes"], o["path"]), (o, meta)
        data = git("cat-file", "blob", o["blob"])
        assert len(data) == entry["bytes"] and sha(data) == entry["sha256"]
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == o["blob"]
        CACHE[key] = data
    return CACHE[key]


def verify_delivery_sources():
    candidate = json.loads((ROOT / "PREPARATION_MANIFEST.json").read_bytes())
    delivery = json.loads((ROOT / "DELIVERY_PROVENANCE.json").read_bytes())
    assert sha((ROOT / "PREPARATION_MANIFEST.json").read_bytes()) == delivery["candidate_manifest_sha256"] == "73bc70e560791de77c04da8c229db5c2bc90135fd3a2b574c63ad05600af5e7e"
    inputs_data = (ROOT / "INPUT_MANIFEST.json").read_bytes()
    assert sha(inputs_data) == candidate["input_manifest_sha256"] == "1839a86d914ca9c0cfd2f4ece8a41eae973138a8646bb858cbb6626d21e4cef6"
    inputs = json.loads(inputs_data)["inputs"]
    assert len(inputs) == 646 and len({i["snapshot"] for i in inputs}) == 646
    original = [i for i in inputs if i["origin"]["kind"] == "IMMUTABLE_GIT_BLOB"]
    assert len(original) == 239
    for item in original:
        git_source(item)
    # Scratch-only history is immutable provenance, not a portable acceptance dependency.
    # Required actual input bytes are Git-bound above or exact delivered projections below.
    for item in delivery["normative"]:
        raw = (ROOT / item["path"]).read_bytes()
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    fixture = json.loads((ROOT / "FIXTURE_INPUTS.json").read_bytes())
    for p in delivery["fixture_projections"]:
        original_pin = next(i for i in inputs if i["snapshot"] == p["source"])
        assert (p["source_bytes"], p["source_sha256"]) == (original_pin["bytes"], original_pin["sha256"])
        encoded = json.dumps(fixture[p["projection_field"]], sort_keys=True, separators=(",", ":")).encode()
        assert sha(encoded) == p["projection_sha256"]
    source_bindings = json.loads((ROOT / "ORIGINAL_SOURCE_BINDINGS.json").read_bytes())
    for item in source_bindings["inputs"]:
        assert item in inputs
        git_source(item)
    for item in json.loads((ROOT / "SOURCE_ADAPTATIONS.json").read_bytes())["files"]:
        data = (ROOT / item["path"]).read_bytes()
        assert sha(data) == item["delivered_sha256"]
        restored = data.decode()
        for replacement in reversed(item["replacements"]):
            assert restored.count(replacement["after"]) == 1
            restored = restored.replace(replacement["after"], replacement["before"])
        assert sha(restored.encode()) == item["source"]["sha256"]
    assert sha((ROOT / "custody_study.py").read_bytes()) == next(i["sha256"] for i in candidate["candidate_files"] if i["path"] == "custody_study.py")
    return {"original_git_bindings": len(original), "preparation_pins": len(inputs), "normative": len(delivery["normative"])}
