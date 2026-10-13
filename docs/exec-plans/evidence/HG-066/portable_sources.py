"""Bounded immutable original Git bytes, always inert data; no historical imports."""
import hashlib
import subprocess
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
START = time.monotonic_ns()
USED = {'operations': 0, 'bytes': 0}
CACHE = {}

def git(*args):
    assert USED['operations'] < 16384 and time.monotonic_ns() - START <= 120000000000
    USED['operations'] += 1
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, timeout=10)
    USED['bytes'] += len(result.stdout) + len(result.stderr)
    assert result.returncode == 0 and USED['bytes'] <= 67108864
    assert time.monotonic_ns() - START <= 120000000000
    return result.stdout

def original_bytes(row):
    obj = row['object']
    key = (row['revision'], obj['path'], obj['mode'], obj['blob'], obj['bytes'], obj['sha256'])
    if key not in CACHE:
        assert len(CACHE) < 1024 and 0 <= obj['bytes'] <= 262144
        assert sum(len(v) for v in CACHE.values()) + obj['bytes'] <= 16777216
        entries = [x for x in git('ls-tree', '-l', '-z', row['revision'], '--', obj['path']).split(b'\0') if x]
        assert len(entries) == 1
        fields, name = entries[0].split(b'\t', 1)
        mode, kind, oid, size = fields.split()
        assert (mode.decode(), kind, oid.decode(), int(size), name.decode()) == (obj['mode'], b'blob', obj['blob'], obj['bytes'], obj['path'])
        assert mode in (b'100644', b'100755')
        raw = git('cat-file', 'blob', obj['blob'])
        assert len(raw) == obj['bytes'] and hashlib.sha256(raw).hexdigest() == obj['sha256']
        assert hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == obj['blob']
        CACHE[key] = raw
    return CACHE[key]
