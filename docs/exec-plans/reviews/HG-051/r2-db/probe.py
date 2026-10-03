from pathlib import Path
import hashlib, importlib.util, json, subprocess, shutil, tempfile
ROOT=Path('/Users/davetian/.codex/worktrees/83f7/KineticLoop')
BASE='b877db0edd2e4550d6ea81750656112fb7f2e223'
def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT)
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
ce=load(ROOT/'tools/harness/compact_evidence.py','db_ce')
head=git('rev-parse','HEAD').decode().strip()
paths=git('diff','--name-only',BASE,head).decode().splitlines()
protected=[p for p in paths if p.startswith(('src/','migrations/','.github/','protocol_model/','tests/db/','tests/integration/')) or p in ['FROZEN_BASELINE.json','CURRENT_REQUIREMENT_SET.json','05_KineticLoop_Protocol_v1.2_FROZEN.md','04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md','12_KineticLoop_Integration_Spec_v0.1.md']]
assert not protected,protected
klpaths=[p for p in paths if p.startswith(('docs/exec-plans/evidence/KL-080/','docs/exec-plans/reviews/KL-080/'))]
assert not klpaths,klpaths
for file,array in [('KineticLoop_Harness_Backlog_v0.2.json','tasks'),('KineticLoop_Harness_Traceability_v0.3.json','tasks')]:
    old=json.loads(git('show',BASE+':'+file)); new=json.loads((ROOT/file).read_bytes())
    # Preserve every nested key and byte-value except exact authorized DoD suffix.
    def strip(value):
        if isinstance(value,dict):
            return {k:strip(v) if k!='definition_of_done' else v.split(' HG051 permits only')[0] for k,v in value.items()}
        if isinstance(value,list):return [strip(v) for v in value]
        return value
    assert strip(old)==strip(new),file
assert ce.HISTORICAL_SCHEMA_BYTES==(ROOT/ce.MAPPING_SCHEMA).read_bytes()
assert (ce.PLAIN_LIMIT,ce.STORED_LIMIT,ce.RAW_LIMIT,ce.TOTAL_LIMIT)==(262144,8388608,67108864,16777216)
inv=json.loads((ROOT/'docs/exec-plans/evidence/HG-051/INVENTORY.json').read_bytes())
originals=ce.historical_originals()
assert len(originals)==len(inv['overlimit'])==4
result=[]
for original,expected in zip(originals,inv['overlimit'],strict=True):
    raw=ce.archive_original(ROOT,original)
    assert original['path']==expected['path']
    assert original['blob_id']==expected['git_blob']
    assert (len(raw),ce.digest(raw))==(expected['raw_bytes'],expected['raw_sha256'])
    assert ce.read(ROOT,original['path'],original['revision'])==raw
    assert original['execution']['timestamp'] is None
    if original['path'].endswith('.log'):
        assert original['execution']['result']=='FAIL' and original['execution']['exit_code']==1
    git('merge-base','--is-ancestor',original['revision'],inv['head'])
    rec,stored=ce.archive_envelope(original,raw)
    assert len(stored)==expected['gzip9_bytes']
    result.append({'path':original['path'],'revision':original['revision'],'blob':original['blob_id'],'raw_bytes':len(raw),'sha256':ce.digest(raw),'exit':original['execution']['exit_code']})
with tempfile.TemporaryDirectory(prefix='hg051-r2-db-installed-',dir='/private/tmp') as tmp:
    root=Path(tmp); installed=root/'gate/tools/harness'; installed.mkdir(parents=True)
    for p in ('compact_evidence.py','validate_harness.py','db_ci_pytest.py','db_ci.py','gate_validate.py','gate_pytest.py'):
        shutil.copyfile(ROOT/'tools/harness'/p,installed/p)
    decoder=load(installed/'compact_evidence.py','installed_db_ce')
    validator=load(installed/'validate_harness.py','installed_db_validator')
    assert not (root/'gate'/ce.MAPPING_SCHEMA).exists()
    assert decoder.historical_originals()==originals
    candidate=root/'candidate'; candidate.mkdir()
    schema=candidate/ce.MAPPING_SCHEMA
    errors=validator.historical_schema_authority_errors(candidate)
    assert errors and errors[0].startswith('historical-schema-authority:')
    schema.write_bytes(ce.HISTORICAL_SCHEMA_BYTES)
    assert not validator.historical_schema_authority_errors(candidate)
    schema.write_text('{}')
    assert validator.validate(candidate,None)==['historical-schema-authority:mismatch']
    assert decoder.historical_originals()==originals
    (root/'gate'/ce.MAPPING_SCHEMA).write_text('{}')
    assert decoder.historical_originals()==originals
report={'head':head,'base':BASE,'status':'PASS','unchanged_DB_runtime_migrations_workflows_frozen_provider_boundaries':True,'unchanged_KL080_checks_resources_oracles':True,'HG051_KL080_migration_absent':True,'installed_schema_adjacent_file_unneeded':True,'candidate_schema_mismatch_missing_rejected':True,'budgets_unchanged':True,'original_inventory':result,'historical_outcome':ce.historical_template()['historical_outcome'],'purpose':'Independent DB/concurrency review; no DB lifecycle or App/fullDB completion claim'}
print(json.dumps(report,indent=2))
