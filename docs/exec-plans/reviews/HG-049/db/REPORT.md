# HG-049 independent DB concurrency review

Review status: PASS for `harness-governance-v0.1/HG-049` at
`ceed78db431a348aae0b599a5e1b09bb082fb968`. Protected base is
`95ddd75d3eb410b7dffa15a1017276c504adc9a6`; implementation checks bind
`4db695230c2158f67394c8ac79a5f0fdf511849a`.

No BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING defect found in this governance
change. This is a review of the prospective definition and its enforcement,
not execution evidence for KL-080 or a merge recommendation with pending gates.
The repository db-transaction-reviewer and pr-merge-reviewer skills were applied.

## Database boundary and actual consumer

Frozen DB S12 defines physical association MATCHED/AMBIGUOUS/RETRACTED; S13
defines action-scoped ELIGIBLE/NOT_ELIGIBLE/UNRESOLVED. S27's ADMITTED root
state and S36's derived CONFIRMED association result have separate meanings.
S37 is an immutable ValidationService result consumed only while every binding
remains current. A preparation PASS does not grant execution authority.

The existing mechanical owner pipeline produces F, D, N, S36 and S37 through
COMMIT_READY. `deterministic_planning.py:675` sets S37.ref_s34_id to N, while
the Demand owner sets S35.ref_s34_id to F; N.demand_feature_id points to D.
The unchanged legacy consumer's `prepare_authorization_basis` reads these
physical columns and requires S37's proposal anchor equal Demand's Fitness
anchor unless full_execution_members exists, and requires the proposal's
demand_feature_id equal the S37 Demand identity. The actual denial expected for
untouched mechanical owner S37 is `GuardRequired: policy, demand, and calendar
authorization bounds must exist` at `transactions.py:3968`. The dependency
condition at lines 3965-3966 precedes the later synthetic certificate check.
`idempotent_outcome` calls prepare_authorization_basis before
require_execution_request, so a report of later certificate reach would be
incorrect for this input. This expectation is derived from exact Git source;
no PostgreSQL consumer execution was performed by this governance review.

The refined oracle demands a well-formed legacy CommitBundle, separately
authenticated current ingress, correct mechanical policy and artifact closure,
owner, request, attempt, fence, live lease, epoch, execution basis, fresh key
and correctly computed result fingerprint. It requires the exact actual guard,
complete zero effects and first-use head rollback. Construction, registration,
unrelated ingress/lifecycle/hash failure and full-policy downgrade cannot pass.
The owner creates an absent S38 only after S51/S01/S27 and fence verification;
the transaction and first-use finish guard require complete outcome bookkeeping.
The future real-PG test must prove rollback of this placeholder along with
output, receipt, event, outbox, head, root and session state.

Canonical full kl079-full-actions-v1 remains the positive execution path: actual
F/D/N owners, distinct TRAINING/NUTRITION S36, shared S37, full T6 and actual
START, ordinary PAUSE, RESUME and CONTINUE for both members. Explicit full
bindings permit the N anchor. The unchanged policy guard rejects use of a full
policy through legacy T6. Synthetic legacy execution remains mandatory support
and cannot substitute for canonical source-to-execution evidence.

Frozen S51 → S01 → quota/intent → reservation → S38 → S44 → receipt/remaining
aggregate order, lease/fence/idempotency semantics, T1–T8 boundaries, S37
binding requirements and server validity closure are preserved. No runtime,
DB-test, migration, schema, certificate conversion, new consumer, authorization,
registry, model/network coordination or production/shadow behavior changes.
Therefore fresh DB execution is a future KL-080 obligation; governance does
not claim to have executed those oracles.

## Scope and evidence

Independent exact-revision verification confirms only the selected trajectory
oracle and second deliverable changed in KL-080. All other sixteen oracles,
seventeen selectors/checks, ten dependencies, eight resource keys, nineteen
write paths and four review requirements remain intact. The exact backlog and
traceability projections agree. M3 task/exit mappings, regression commands,
fixture guards and plan hash remain intact; only this oracle's pinned digest
changes. KL-080 remains NOT_STARTED with empty requirement/evidence claims.

All ten dependency results are PASS and their MERGED integrations precede the
protected base. M2 closure remains PASS. The 3,896 pre-existing historical
artifact paths are unchanged. Frozen files, FROZEN_BASELINE, requirement set,
project plan, M3 contract, lockfile and application/DB-test/CI sources retain
their protected-base bytes. There is no KL-080 result, integration, review or
M3 closure added. The tested-to-reviewed suffix is permitted own record/new
evidence only, and the exact governance file list matches the Git diff.

All seven committed check outputs were retrieved from regular Git blobs at the
reviewed SHA using compact_evidence.read with the exact tested SHA, command
and zero exit code. Complete harness evidence has 1,347 unique serial nodeids,
matching both worker collections, exactly one start and setup/call/teardown
PASS per case, and clean 1,347-case JUnit. This includes 59 source-scope cases
and M3 closure tests. Unit JUnit contains 241 executed cases with no failures,
errors or skips. The harness manifest records clean source at the tested SHA
and complete execution. Raw parameter text can contain failure/skip words;
the observer phases and JUnit dispositions supply actual execution status.

The independent verifier preserved its executed source hash and raw stdout.
Compact evidence audit of the reviewed diff passed (3,252,716 stored bytes,
45 evidence files). Every new regular nongzip reviewer file was classified
with compact_evidence.envelope before handoff; no source misclassification or
malformed reserved storage object was accepted.

Normal exact-final-head hosted checks, App-bound admission and complete isolated
DB gate remain pending under the root coordinator. No lifecycle, database,
installation, controller configuration, admission, publication or historical
acceptance recertification was attempted. Review PASS, task PASS, product PASS,
M3/release closure and MERGED remain separate facts; this review supplies only
the DB_CONCURRENCY governance review.
