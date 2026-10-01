"""Research-only in-memory candidate against actual merged restricted gateway.

No application file is edited, DB lifecycle invoked, or PostgreSQL acceptance
claimed. Tiny source substitutions isolate the two missing capabilities while
retaining all other actual guards, including READY candidate completeness.
"""
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

from psycopg.pq import TransactionStatus

ROOT=Path(__file__).resolve().parents[4]
path=ROOT/'src/kineticloop/persistence/transactions.py'
source=path.read_text()
# DB revision is server-owned and caller insert columns remain restricted.
old='''        database_values = dict(values)
        if logical_id == "S24"'''
new='''        database_values = dict(values)
        if logical_id == "S21" and self.__command_kind == "RecordProjection":
            if "revision" in values:
                raise StatementRejected("server-owned S21 revision cannot be supplied")
            database_values["revision"] = 1
        if logical_id == "S24"'''
assert source.count(old)==1; source=source.replace(old,new)
old='''            required = REQUIRED_FIELDS.get(logical_id, frozenset())
            if not required <= requested:'''
new='''            required = REQUIRED_FIELDS.get(logical_id, frozenset())
            if logical_id == "S21" and self.__command_kind == "RecordProjection":
                required = required - {"revision"}  # injected server-side above only
            if not required <= requested:'''
assert source.count(old)==1; source=source.replace(old,new)
old='''            if field == "ref_s15_id" and self.__command_kind == "PublishManifest":
                requires_lock = False'''
new='''            if (field == "ref_s15_id" and referenced is not None
                and (self.__command_kind, logical_id) in {
                    ("RecordProjection", "S22"), ("BuildManifest", "S23")
                }):
                if not isinstance(referenced, UUID):
                    raise GuardRequired("exact immutable SEALED factset ID required")
                _cursor(self).execute(
                    "SELECT id FROM kineticloop.factset_revisions "
                    "WHERE subject_id=%s AND id=%s AND status='SEALED'",
                    (self.__subject_id, referenced),
                )
                if _cursor(self).fetchone() != (referenced,):
                    raise GuardRequired("actual same-subject SEALED factset required")
                requires_lock = False  # exact immutable verified input only
            if field == "ref_s15_id" and self.__command_kind == "PublishManifest":
                requires_lock = False'''
assert source.count(old)==1; source=source.replace(old,new)
module=types.ModuleType('kineticloop.persistence.hg040_candidate')
sys.modules[module.__name__]=module
exec(compile(source,str(path)+' [IN_MEMORY_RESEARCH_CANDIDATE]','exec'),module.__dict__)
SUBJECT,FACTSET,PROJECTION,POLICY,PROGRAM=[UUID(int=78000+n) for n in range(5)]

def run(label, owner, logical, values, *, sealed=True, incomplete=False, deny=False):
    connection=MagicMock(); connection.info.transaction_status=TransactionStatus.IDLE
    cursor=connection.cursor.return_value; cursor.rowcount=1
    def respond(query, params=None):
        text=str(query)
        if 'FROM kineticloop.factset_revisions' in text:
            cursor.fetchone.return_value=(FACTSET,) if sealed and params==(SUBJECT,FACTSET) else None
        elif 'FROM kineticloop.policy_bundles' in text:
            cursor.fetchone.return_value=({'manifest_projection_requirements':['EXPOSURE']},)
    cursor.execute.side_effect=respond
    error=None
    try:
        module.execute_preparation(connection,owner,SUBJECT,lambda session: session.insert(logical,values))
    except (module.GuardRequired,module.StatementRejected) as exc:
        error=str(exc)
    assert (error is not None)==deny,(label,error)
    calls=cursor.execute.call_args_list
    writes=[c for c in calls if 'INSERT' in str(c.args[0])]
    assert len(writes)==(0 if deny else 1),(label,calls)
    if logical=='S21' and not deny:
        assert 'revision' in str(writes[0].args[0]) and 1 in writes[0].args[1]
    print(json.dumps({'label':label,'owner':owner,'table':logical,'expected_denial':deny,
        'denial':error,'insert_sql_calls':len(writes),'all_sql_calls':len(calls),
        'actual_gateway_remaining_guards':True,'layer':'IN_MEMORY_CANDIDATE_DIAGNOSTIC',
        'postgresql_acceptance':False},sort_keys=True))

print(json.dumps({'source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 'source_file_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'candidate_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
 'application_files_edited':False,'database_opened':False,'lifecycle_invoked':False}))
p={'id':PROJECTION,'subject_id':SUBJECT,'projection_kind':'EXPOSURE','input_basis_hash':'basis'}
run('server_revision_complete','RecordProjection','S21',p)
run('caller_revision_denied','RecordProjection','S21',{**p,'revision':1},deny=True)
run('missing_basis_still_denied','RecordProjection','S21',{k:v for k,v in p.items() if k!='input_basis_hash'},deny=True)
d={'id':UUID(int=78100),'subject_id':SUBJECT,'dependency_kind':'FACTSET','dependency_semantic_key':'factset','ref_s21_id':PROJECTION,'ref_s15_id':FACTSET}
run('exact_sealed_dependency','RecordProjection','S22',d)
run('nonsealed_dependency','RecordProjection','S22',d,sealed=False,deny=True)
run('foreign_dependency','RecordProjection','S22',{**d,'ref_s15_id':UUID(int=999)},deny=True)
run('arbitrary_column','RecordProjection','S22',{**d,'privilege':'ADMIN'},deny=True)
run('foreign_owner_surface','BuildManifest','S22',d,deny=True)
b={'id':UUID(int=78200),'subject_id':SUBJECT,'build_identity':'test:kl078:build','captured_epoch':0,
 'ref_s05_id':POLICY,'ref_s06_id':PROGRAM,'ref_s15_id':FACTSET,'ref_s21_id':PROJECTION}
run('sealed_building','BuildManifest','S23',{**b,'status':'BUILDING'})
candidate={'manifest_hash':'manifest','dependency_basis_hash':'dependencies','artifact_dependency_closure_hash':'closure',
 'projection_bindings':[{'id':str(PROJECTION),'role':'EXPOSURE','basis_hash':'basis'}],
 'artifact_closure_ids':['artifact'],'artifact_root_ids':['artifact']}
run('sealed_complete_ready','BuildManifest','S23',{**b,'status':'READY','typed_payload':candidate})
run('ready_completeness_preserved','BuildManifest','S23',{**b,'status':'READY'},deny=True)
run('nonsealed_ready','BuildManifest','S23',{**b,'status':'READY','typed_payload':candidate},sealed=False,deny=True)
run('cross_subject','RecordProjection','S22',{**d,'subject_id':UUID(int=999)},deny=True)
print('CANDIDATE_GATEWAY_DIAGNOSTIC_PASS: 4 positive / 9 negative controls; no implementation or PG acceptance claim')
