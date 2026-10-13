"""Fresh task-owned bounded observations only; no scratch acceptance dependency."""
import json
import os
from pathlib import Path

def read_json(name):
    assert name in ('CURRENT_ROOT_UNION_PROOF.json', 'CURRENT_GROUP_OBSERVATION.json')
    path = Path(os.environ['MULTI_PREPARATION_OUTPUT']) / name
    assert path.stat().st_size <= 1048576
    return json.loads(path.read_bytes())
