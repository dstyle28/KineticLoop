import hashlib
import importlib.util
import json
from pathlib import Path

root = Path.cwd()
p = root / 'KineticLoop_Harness_Backlog_v0.2.json'
backlog = json.loads(p.read_text())
task = next(t for t in backlog['tasks'] if t['id'] == 'KL-026')
assert 'cancellation_identity_pu' not in task['checks_required_for_this_task'], 'one-time HG038-base draft only'
check = {'check_id':'cancellation_identity_pu', 'command':'uv run pytest -q tests/unit/protocol/test_interleaving_namespace.py::test_cancellation_identity', 'pass_oracle':'Strict immutable independent TEST-local cancellation request binds trusted existing PlanningIdentity(TEST), exact isolated subject/policy/environment and registered TEST principal; canonical server-computed key/hash binds exact root/attempt/reservation/request revision/fence. Positive construction and installed candidate execute; non-TEST identity, foreign registration/scope/subject, malformed types/bounds, altered hash, wrong root/attempt/reservation, stale request/fence deny before mutation. Public TEST_ONLY CancelIntent still rejects and the public command registry/validator remain unchanged; no model_construct, public subclass, SUBJECT translation or self-attested actor/hash. Same-key conflict, concurrent same-key historical replay and terminal-success preservation require separate real-PG I03 evidence; PU never substitutes for DC.'}
task['check_contracts'].insert(9,check)
task['checks_required_for_this_task'].insert(9,check['check_id'])
task['context_files'].append('docs/exec-plans/evidence/HG-039/PREPARATION.md')
p.write_text(json.dumps(backlog,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('v',root/'tools/harness/validate_harness.py')
v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
p=root/'KineticLoop_Harness_Traceability_v0.3.json'; trace=json.loads(p.read_text())
trace['tasks']=[v.traceability_projection(task) if t['id']=='KL-026' else t for t in trace['tasks']]
p.write_text(json.dumps(trace,indent=2)+'\n')
p=root/'docs/exec-plans/active/KL-026.md'; text=p.read_text()
text=text.replace('- interleaving_namespace_pu','- cancellation_identity_pu\n- interleaving_namespace_pu',1)
text=text.replace('- docs/exec-plans/completed/KL-074_RESULT.yaml','- docs/exec-plans/completed/KL-074_RESULT.yaml\n- docs/exec-plans/evidence/HG-039/PREPARATION.md',1)
start=text.index('```json\n')+len('```json\n'); end=text.index('\n```',start)
text=text[:start]+json.dumps({'check_contracts':task['check_contracts'],'evidence_paths':task['evidence_paths']},indent=2)+text[end:]
text=text.replace('validate strict existing CancelIntent identity, expected revision/fence and active root.', 'validate strict independent TEST-local TestCancelIntentRequest identity, expected revision/fence and active root. This request is independent of public contracts.commands.CancelIntent; public TEST_ONLY construction continues to reject T4/T8 and public registry/validator remain unchanged.')
text=text.replace('Cancellation/dispatch/acquire/publish/commit/START/seal use actual merged typed owners.', 'Dispatch/acquire/publish/commit/START/seal use actual merged typed owners. Cancellation uses the existing restricted CancelIntent owner through the independent TEST-local typed request recipe below.')
section='''\n## TEST-local cancellation identity (HG-039)\nOnly KL026 tests may define strict immutable TestCancelIntentRequest, independent of the public wire model, with command_kind=CancelIntent, boundary=T8, canonical subject/policy/environment/principal, bounded nonblank key, exact intent/attempt/reservation IDs, positive expected_request_revision and nonnegative expected_fence. The request carries no caller actor, authorization grant or request_hash; the trusted recipe computes canonical hash from the entire strict payload server-side and uses separately trusted existing PlanningIdentity(TEST). Use the existing ProtocolExecutionService._guard registered TEST subject/policy/environment/principal recipe before replay; repeat exact persisted registration under S01 with SELECT-only reads. No SUBJECT translation, public subclass, model_construct, validator relaxation or new production request is allowed. Proposal feasibility in HG039 is not an implementation or DC PASS.\n\nHistorical replay uses existing replay_outcome on the idle connection before transaction. Under S01, a bounded SELECT-only successful S02 lookup on that same owned connection repeats subject/actor scope/CancelIntent/key/hash/outcome binding before live-root guards; no receipt lock precedes intent/reservation locks and no unavailable planning_historical_outcome accessor or nested replay_outcome is used; changed payload on the same key denies, concurrent same-key replay returns original non-sendable facts with no second mutation/receipt/event/outbox. After lock_subject→lock_intents(exact root)→lock_reservations(exact reservation), read current subject/request/root/attempt/fence and exact reservation linkage/status/accounting. Reject foreign identities, malformed types/bounds, wrong hash/root/attempt/reservation, stale revision/fence and terminal non-success before mutation. Completed SUCCESS/FOUND_VALID_PLAN returns original completed fact without fabricated cancellation. Root cancellation only updates S27.status and the existing idempotent receipt/event/outbox; no owner grant or ledger accessor changes.\n\nThe named cancellation_identity_pu selector must run positive construction and the installed legitimate candidate, immutable payload/canonical hash and all above negative identity/scope/type/basis checks; prove public TEST_ONLY CancelIntent still rejects and public registry/validator stay unchanged. I03 DC additionally proves stale/cross-root denials have zero target/bookkeeping effects, same-key different-payload conflict, concurrent same-key historical replay and terminal-success preservation. Preserve both race orders, intermediate terminal-with-RESERVED no-send/no-new-reservation/T6 safety, separate actual CancelUndispatched exact ledger cleanup and dispatch-first unchanged occupation/identity with cleanup rejection/no refund/resend. Missing candidate or unexecuted PU/DC evidence is NOT_RUN, never PASS.\n'''
text=text.replace('\n## Source and output boundary',section+'\n## Source and output boundary')
p.write_text(text)
p=root/'tools/harness/validate_harness.py'; text=p.read_text()
text=text.replace(v.M3_NEXT_WAVE_DEFINITION_HASHES['KL-026'],hashlib.sha256(json.dumps(task,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
text=text.replace(v.M3_NEXT_WAVE_PACKET_HASHES['KL-026'],hashlib.sha256((root/'docs/exec-plans/active/KL-026.md').read_bytes()).hexdigest())
p.write_text(text)
