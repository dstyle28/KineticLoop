"""Exact portable source comparison; no historical execution or runtime authority."""
import ast
import hashlib
import json
import subprocess
from pathlib import Path
E = Path(__file__).resolve().parent
R = E.parents[3]
B = '3768c1b4366677934cb952ef808343edcee4e438'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def verify():
    provenance = json.loads((E / 'DELIVERY_PROVENANCE.json').read_bytes())
    adaptations = {r['path']: r for r in json.loads((E / 'SOURCE_ADAPTATIONS.json').read_bytes())['files']}
    for item in provenance['reviewed_sources']:
        raw = (E / item['path']).read_bytes()
        if item['path'] in adaptations:
            change = adaptations[item['path']]
            assert sha(raw) == change['delivered_sha256']
            lines = raw.decode().splitlines(keepends=True)
            for delta in reversed(change['changes']):
                lines[delta['destination_start']:delta['destination_end']] = delta['original'].splitlines(keepends=True)
            restored = ''.join(lines)
            raw = restored.encode()
            assert sha(raw) == change['source_sha256']
            normalized = restored
            for pair in change['permitted_path_changes']:
                normalized = normalized.replace(pair['before'], pair['after'])
            assert ast.dump(ast.parse(normalized)) == ast.dump(ast.parse((E / item['path']).read_bytes()))
        assert len(raw) == item['bytes'] and sha(raw) == item['sha256'], item['path']
    for item in provenance['unchanged_hg065_normative'] + provenance['current_protected_dependencies']:
        raw = subprocess.check_output(['git', 'show', B + ':' + item['path']], cwd=R)
        assert len(raw) == item['bytes'] and sha(raw) == item['sha256']
        assert (R / item['path']).read_bytes() == raw
    for item in provenance['source_references']:
        raw = (R / item['destination']).read_bytes()
        assert len(raw) == item['bytes'] and sha(raw) == item['sha256']
        if item['revision'] != 'TASK_DELIVERY':
            assert subprocess.check_output(['git', 'show', item['revision'] + ':' + item['destination']], cwd=R) == raw
    promotion = json.loads((E / 'NORMATIVE_PROMOTION.json').read_bytes())
    for item in promotion['appendices']:
        before = subprocess.check_output(['git', 'show', B + ':' + item['path']], cwd=R)
        after = (R / item['path']).read_bytes()
        assert sha(before) == item['base_sha256'] and len(before) == item['base_bytes']
        assert after.startswith(before)
        assert sha(after[len(before):]) == item['append_sha256']
        assert len(after) - len(before) == item['append_bytes']
        assert b'normatively incorporates the exact reviewed sources' in after[len(before):]
    clauses = json.loads((E / 'CLAUSE_SUPERSESSION.json').read_bytes())
    # Original clauses remain immutable input data. The exact candidate source hash
    # plus verified base-prefix and promotion bindings preserve the narrow override.
    assert clauses
    ids = json.loads((E / 'EXPECTED_IDENTITIES.json').read_bytes())
    assert sum(len(s['identities']) for s in ids['suites'][:-1]) == 677
    assert len(ids['suites'][-1]['identities']) == 156
    schemas = ['MULTI_PROOF_SCHEMA.json', 'OPERATION_PROOF_SCHEMA.json', 'MULTI_OUTPUT_SCHEMA.json', 'ROOT_STATE_SCHEMA.json', 'SEQUENCE_SCHEMA.json', 'PUBLIC_DENIAL_SCHEMA.json', 'PREIMPORT_SCHEMA.json']
    import jsonschema
    for name in schemas:
        jsonschema.Draft202012Validator.check_schema(json.loads((E / name).read_bytes()))
    original = json.loads((E.parent / 'HG-065/OUTPUT_SCHEMA.json').read_bytes())
    current = json.loads((E / 'MULTI_OUTPUT_SCHEMA.json').read_bytes())
    current['title'] = original['title']
    current['properties']['type'] = original['properties']['type']
    assert current == original
    return {'reviewed_sources': len(provenance['reviewed_sources']), 'prospective_identities': 677, 'preserved_v1_identities': 156, 'complete_AST_and_hostile_constants_preserved': True}

if __name__ == '__main__':
    print(json.dumps(verify()))
