# HG-038 preparation barrier and owner mapping

Prepared on actual KL019 normal merge cfbfae0c366e654060d5d52f961a37abf956f2a0.
PR72/KL074 owns the next merge slot. Until its actual normal merge, only this
HG038 evidence directory may change. Drafts are proposals, not scheduled packets,
task/product PASS, review evidence or M3 closure.

Authority read: current index; governance, result, review and merge contracts;
Protocol 5.3–5.6, 6.1–6.9; DB S26–S29, S34–S45; acceptance sections 2–4;
actual KL019/KL047 results and existing transaction/planning/execution code.

Verified gaps:
- contracts/commands.py explicitly excludes RecordSnapshot and AdvanceAttempt
  from the 39 public commands. Neither has an existing typed persistence owner.
- KL019 require_execution_request consumes one synthetic F/D/resolution/certificate
  shape; commit inserts exactly one TRAINING S40/S41/S42. Its upstream test helper
  inserts S26 and directly marks COMMIT_READY. It is not full F/D/N progress.
- START exists as a typed adapter. CONTINUE/RESUME have transaction owners and
  current-authorization evaluators but no typed service methods in KL019.
- KL026 and KL027 are unstarted, contain symbolic checks, broad protocol/workflow
  write globs, overlapping authorization resources, and no DB isolation contract.

Proposed coherent decomposition:
- KL026: tests-only real-PG I01–I09 DC suite against actual merged owners;
  I04@WF remains a distinct unfulfilled obligation. No production repair scope.
- KL075: internal snapshot and attempt-stage persistence, current guard and frozen
  state transitions. No public command addition, F/D/N engine or authorization.
- KL076: deterministic isolated TEST preparation owners for immutable F/D/N,
  complete source-bound resolution and fixture semantic/envelope certificates;
  no clinical/model/production policy decisions or authorization writer.
- KL077: full TEST bundle consumption plus current CONTINUE/RESUME adapters over
  T6/T7, exact immutable member/issuance bindings and server validity closure.
- KL027: tests-only composed full trajectory using the merged prerequisites.

KL075/076/077 each require fresh bounded packets and serialized shared transaction
interfaces. KL026 may run alongside them using merged dependencies and separate
task-owned DB/Compose resources. KL027 waits for all three. No prerequisite result
or product PASS is manufactured. Any discovered production fix from KL026 becomes
another bounded task; its test scope cannot silently expand.

Trusted test-local T2 recipes are explicitly ratified for DC instrumentation:
ApplyControl uses execute_command, lock_subject, RestrictedSqlSession S17 STOP/
HOLD, S18 ACTIVE, S43 epoch invalidation, S01 old epoch+1/control pointer and
idempotent_outcome/invalidation_scope TEST_ONLY with receipt/event/outbox.
AcceptFactRevision uses the actual KL023 input_revision recipe: admitted S14
revision, S43 invalidation and S01 frontier/old epoch+1 under the same owner.
Raw SQL epoch/frontier mutation outside those owners is not a raced operation.
These recipes establish internal owner DC evidence, not a public ingress/control
implementation or authentication assurance.

No frozen authority, requirement set, release status, completed task definition,
result or evidence may change. Normal CI and merge gates remain mandatory; the
KL074 branch-specific hosted workflow cannot execute any of these tasks.
