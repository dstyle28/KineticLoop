"""Recover the exact approved inventory in an ephemeral Git repo, never repository fixtures."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location('hg051_inventory_compact', ROOT / 'tools/harness/compact_evidence.py')
assert SPEC and SPEC.loader
ce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ce)


def run(root, *args):
    return subprocess.check_output(['git', *args], cwd=root).decode().strip()


def main():
    tested = run(ROOT, 'rev-parse', 'HEAD')
    inventory = json.loads((ROOT / 'docs/exec-plans/evidence/HG-051/INVENTORY.json').read_bytes())
    source = inventory['head']
    objects = Path(run(ROOT, 'rev-parse', '--git-path', 'objects')).resolve()
    if not objects.is_absolute():
        objects = (ROOT / objects).resolve()
    results = []
    with tempfile.TemporaryDirectory(prefix='hg051-inventory-', dir='/private/tmp') as work:
        root = Path(work)
        run(root, 'init', '-q')
        run(root, 'config', 'user.name', 'HG051 ephemeral inventory')
        run(root, 'config', 'user.email', 'hg051@example.invalid')
        (root / '.git/objects/info/alternates').write_text(os.fsdecode(objects) + '\n')
        run(root, 'update-ref', 'HEAD', source)
        run(root, 'read-tree', source)
        installed = root / 'gate/tools/harness'
        installed.mkdir(parents=True)
        # Exact unchanged local_gate.worker Python asset copy set; no schema file.
        for asset in ('validate_harness.py', 'compact_evidence.py', 'db_ci_pytest.py',
                      'db_ci.py', 'gate_validate.py', 'gate_pytest.py'):
            shutil.copyfile(ROOT / 'tools/harness' / asset, installed / asset)
        installed_spec = importlib.util.spec_from_file_location(
            'hg051_installed_decoder', installed / 'compact_evidence.py')
        assert installed_spec and installed_spec.loader
        installed_ce = importlib.util.module_from_spec(installed_spec)
        installed_spec.loader.exec_module(installed_ce)
        assert not (root / 'gate' / ce.MAPPING_SCHEMA).exists()
        assert installed_ce.HISTORICAL_SCHEMA_BYTES == (ROOT / ce.MAPPING_SCHEMA).read_bytes()
        originals = installed_ce.historical_originals()
        # Index retains the complete original tree; only four representations
        # are materialized/changed. No copy of the bulk raw data is written.
        for original in originals:
            raw = ce.archive_original(ROOT, original)
            measured = next(x for x in inventory['overlimit'] if x['path'] == original['path'])
            assert (len(raw), ce.digest(raw)) == (measured['raw_bytes'], measured['raw_sha256'])
            manifest, stored = ce.archive_envelope(original, raw)
            assert len(stored) == measured['gzip9_bytes']
            target = root / original['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(manifest, indent=2) + '\n')
            (root / manifest['payload']).write_bytes(stored)
            run(root, 'add', '--', original['path'], manifest['payload'])
        run(root, 'commit', '-qm', 'ephemeral authorized four-blob forward storage')
        storage = run(root, 'rev-parse', 'HEAD')
        mapping = installed_ce.archive_mapping(root, storage)
        (root / ce.MAPPING_PATH).write_text(json.dumps(mapping, indent=2) + '\n')
        run(root, 'add', '--', ce.MAPPING_PATH)
        run(root, 'commit', '-qm', 'ephemeral archival mapping')
        head = run(root, 'rev-parse', 'HEAD')
        for entry in mapping['entries']:
            original = entry['original']
            restored = installed_ce.read_archive(root, original['path'], head)
            assert restored == ce.archive_original(root, original)
            assert restored == ce.read(root, original['path'], original['revision'])
            try:
                ce.read(root, original['path'], head)
            except ValueError:
                pass
            else:
                raise AssertionError('archival representation accepted as execution evidence')
            results.append(dict(path=original['path'], raw_bytes=len(restored),
                                raw_sha256=ce.digest(restored), blob_id=original['blob_id'],
                                original_revision=original['revision'],
                                stored_bytes=entry['storage']['payload_bytes'], exact=True,
                                historical_execution=original['execution']))
        audit = installed_ce.audit(root, source, head, 'KL-080')
        assert not audit['errors'], audit
        report = dict(tested_commit=tested, command='uv run python docs/exec-plans/evidence/HG-051/inventory_roundtrip.py',
                      status='PASS', installed_layout=True, installed_schema_file=False,
                      installed_decoder_sha256=ce.digest((installed / 'compact_evidence.py').read_bytes()),
                      temporary_storage_commit=storage,
                      temporary_mapping_commit=head, results=results, storage_audit=audit,
                      purpose='Archival byte recovery only; original executions/statuses unchanged')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
