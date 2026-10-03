import copy, hashlib, importlib.util, json, subprocess, sys, tempfile
from pathlib import Path
import yaml
root=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
base='b877db0edd2e4550d6ea81750656112fb7f2e223'
source='0557dbd8f2196df871af20c0982bdc2526f0ad6e'
def git(*args): return subprocess.check_output(['git',*args],cwd=root)
def data(path, rev=source): return git('show',rev+':'+path)
def digest(raw): return hashlib.sha256(raw).hexdigest()
with tempfile.TemporaryDirectory(prefix='hg051-r2-protocol-installed-',dir='/private/tmp') as work:
    installed=Path(work)/'gate/tools/harness'; installed.mkdir(parents=True)
    for name in ('validate_harness.py','compact_evidence.py','db_ci_pytest.py','db_ci.py','gate_validate.py','gate_pytest.py'):
        (installed/name).write_bytes(data('tools/harness/'+name))
    spec=importlib.util.spec_from_file_location('hg051_r2_protocol_validator',installed/'validate_harness.py')
    v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v); ce=v.compact_evidence
    assert not (Path(work)/'gate'/ce.MAPPING_SCHEMA).exists()
    assert ce.HISTORICAL_SCHEMA_BYTES == data(ce.MAPPING_SCHEMA)
    index=json.loads(data('CURRENT_DOCUMENT_INDEX.json'))
    assert next(x['sha256'] for x in index['machine_readable'] if x['path']==ce.MAPPING_SCHEMA)==digest(ce.HISTORICAL_SCHEMA_BYTES)
    inventory=json.loads(data('docs/exec-plans/evidence/HG-051/INVENTORY.json'))
    measured=[]
    for original in ce.historical_originals():
        raw=ce.archive_original(root,original)
        expected=next(x for x in inventory['overlimit'] if x['path']==original['path'])
        assert (len(raw),digest(raw),original['blob_id'])==(expected['raw_bytes'],expected['raw_sha256'],expected['git_blob'])
        assert git('ls-tree',source,'--',original['path'])==git('ls-tree',base,'--',original['path'])
        manifest,stored=ce.archive_envelope(original,raw)
        assert len(stored)==expected['gzip9_bytes']
        ref=original['execution_record']; recorded=data(ref['path'],ref['revision'])
        assert (len(recorded),digest(recorded))==(ref['bytes'],ref['sha256'])
        metadata=json.loads(recorded)
        if 'executions' in metadata:
            metadata=next(x for x in metadata['executions'] if x['evidence_ref']==original['path'])
        for key in ('tested_commit','command','exit_code','result'):
            assert original['execution'][key]==metadata[key]
        assert original['execution']['timestamp'] is None
        assert original['revision'] in git('rev-list',inventory['head']).decode().splitlines()
        measured.append({'path':original['path'],'bytes':len(raw),'sha256':digest(raw),'historical_execution':original['execution'],'regular_original_preserved':True,'HG051_tree_unchanged':True})
    preserved=[]
    for ref in ce.historical_template()['preserved_records']:
        raw=data(ref['path'],ref['revision']); assert (len(raw),digest(raw))==(ref['bytes'],ref['sha256'])
        assert git('ls-tree',source,'--',ref['path'])==git('ls-tree',base,'--',ref['path'])
        record=yaml.safe_load(raw)
        status=record.get('task_status',record.get('status'))
        preserved.append({'path':ref['path'],'bytes':len(raw),'sha256':digest(raw),'status':status})
    for filename in ('KineticLoop_Harness_Backlog_v0.2.json','KineticLoop_Harness_Traceability_v0.3.json'):
        old=json.loads(data(filename,base)); now=json.loads(data(filename))
        def tasks(obj): return obj['tasks'] if 'tasks' in obj else obj['task_matrix']
        old_tasks=tasks(old); now_tasks=tasks(now)
        before=next(x for x in old_tasks if x['id']=='KL-080'); after=next(x for x in now_tasks if x['id']=='KL-080')
        assert after['definition_of_done'].startswith(before['definition_of_done'])
        after=copy.deepcopy(after); after['definition_of_done']=before['definition_of_done']; assert after==before
        replacement=copy.deepcopy(now)
        next(x for x in tasks(replacement) if x['id']=='KL-080')['definition_of_done']=before['definition_of_done']
        assert replacement==old
    packet=data('docs/exec-plans/active/KL-080.md').decode(); old_packet=data('docs/exec-plans/active/KL-080.md',base).decode()
    qualified='\n'.join(line for line in packet.split('\n') if not line.startswith('HG051 preservation qualification:'))
    extra=' HG051 permits only the four schema-pinned historical current-tree storage representations and one task-owned archival mapping under EVIDENCE_STORAGE_POLICY; original bytes/commits/bindings/failures and all non-migrated evidence remain unchanged, archival retrieval never certifies execution or PASS, and migration precedes a new tested SHA.'
    assert qualified.replace(extra,'')==old_packet
    unchanged=['05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','12_KineticLoop_Integration_Spec_v0.1.md','09_KineticLoop_Acceptance_and_Release_Gates_v1.2.2.md','06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md']
    for name in unchanged: assert data(name)==data(name,base)
    for path in git('diff','--name-only',base,source).decode().splitlines():
        assert v.matches(path,v.governance_allowed_patterns('HG-051')),path
    assert not git('diff','--name-only',base,source,'--','src','migrations','protocol_model','.github','tools/harness/local_gate.py','tools/harness/github_app.py','docs/exec-plans/evidence/KL-080','docs/exec-plans/reviews/KL-080','docs/exec-plans/completed/KL-080_RESULT.yaml')
    candidate=Path(work)/'candidate'; candidate.mkdir()
    (candidate/ce.MAPPING_SCHEMA).write_bytes(ce.HISTORICAL_SCHEMA_BYTES)
    assert not v.historical_schema_authority_errors(candidate)
    (candidate/ce.MAPPING_SCHEMA).write_bytes(ce.HISTORICAL_SCHEMA_BYTES+b' ')
    assert v.historical_schema_authority_errors(candidate)==['historical-schema-authority:mismatch']
    print(json.dumps({'base':base,'source':source,'status':'PASS','installed_schema_file':False,'candidate_changed_bytes_rejected':True,'originals':measured,'preserved_records':preserved,'unchanged_frozen':unchanged,'KL080_only_preservation_wording':True,'migration_occurred':False},indent=2))
