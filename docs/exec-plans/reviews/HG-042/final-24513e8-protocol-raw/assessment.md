# HG-042 independent PROTOCOL review

Reviewed implementation/governance head: `24513e86d90799edb951fa2bdf52ba433c59318a`.
Protected base: `93b38f20a3f3d71206515fb0f4d852f5b0b6d344`.
Tested source: `e4134f963450db1522fd6c3339e4cb036fcf5ffe`.

Recommendation: PASS for this bounded governance change, with zero blockers and no
new required corrections. This is independent PROTOCOL review evidence, not task,
product requirement, milestone, release or merge evidence.

## Authority and scope

Read AGENTS.md, pr-merge-reviewer and protocol-guardian skills, current authority
index, governance/result/review/merge contracts, HG042 record, exact protected-base
diff, KL028/KL029 packets, merged KL008/KL017/KL021/KL022/KL023/KL027 result records
and named current acceptance/protocol/DB clauses. The review compares Protocol
0.3a, 2.1a, 2.3, 4.1a, 5.3–5.6, 7.4 and T2/T3/T6/T7 against DB S15/S16,
S38/S42/S45–S51, unique owner/Reauthorize, lock order and validity-certificate rules.

The exact diff changes only the two unstarted definitions and declared governance,
derived metadata, evidence, integration and harness guard files. Frozen Protocol,
logical DB, FROZEN_BASELINE, requirement authority, milestone schema, completed
task artifacts, production source, migrations and CI are unchanged. Both packets
remain NOT_STARTED, have exact disjoint three-file tests/contracts scopes and
separate task/SHA/resolved-root namespaces. The declared parallel exception shares
read-only owners and forbids foreign lifecycle fixtures or shared helper writes.

## Protocol and layer assessment

The independently extracted ledger exactly matches all 31 frozen Given/When/Then
and layer tuples: 8 PU, 14 DC, 1 WF, 8 E2E. Nineteen are prospective executable
obligations (6 PU + 13 DC); twelve are deferred. Every check and layer is NOT_RUN.
The packets preserve explicit output-owner, current-state, fresh-key, valid
lifecycle, exact guard cause, immutable-history and zero-effect requirements.
Registry races require PostgreSQL blocker witnesses and S51→S01 ordering; exact
half-open equality remains PU, while real post-lock trusted time belongs to DC.
No model/network wait or new coordination transaction is introduced.

B04's complete DC oracle is deferred because the actual merged full TEST owner
only prepares CommitBundle, requires full issuance AI_PLAN and rejects full
replacement/reauthorization modes. Full issue plus actual Reauthorize registry
guard support remain mandatory task checks; neither can claim full B04 DC PASS.
Its separate owner follow-up requires a newly admitted intent/current attempt and
latest manifest, never terminal reopening, legacy policy downgrade or target seed.
B11/B12 lack a pure commit-state evaluator and remain deferred PU. B14 support is
explicitly task DC support, with actual STOP through independent S01; complete WF
and API/rendering E2E remain deferred to their missing owners/infrastructure.

Actual merged validity evaluation supports inherited/tied minima and immutable
certificates. Actual complete-dependency validation supports the three-node
transitive path with registration-required extra closure edges. A direct review
probe exercised that validator's complete/incomplete graph cases and the actual
validity evaluator's revoked-leaf denial with unrevoked A/B. No invented graph or
commit-state model is used. B17's actual PostgreSQL revocation is separately DC.

KL029 distinguishes strict shadow construction from real store/API usability
(KL045), public parser rejection from genuine ProductionScope require_wire
rejection, owner ingress from registration/privilege/scope and later transaction
guards. Actual ExecutionIdentity/ProtocolExecutionService implementations support
the named reach labels. Positive TEST outputs must be produced by full merged
owners. S46/S47 plus same-subject archived S24/S48/FK backing closure are declared
external historical evaluation inputs with enabled constraints/triggers, not
owner-produced TEST/live or shadow workflow outputs. No live head, production
issuance, execution binding, provider command authority or planned-to-actual
conversion is introduced. Auto-activation remains disabled.

The MILESTONE_CLOSURE schema still supports only M1/M2. M3 closure support is an
explicit separate governance gap; neither packet creates M3 PASS or an M3→M4 cycle.
Missing API/workflow/rendering and full reauthorization owners remain future work.

## Revision and evidence verification

The own audit independently checks exact changed-file declaration, ancestor chain
and linear tested-to-reviewed suffix containing only own governance/new evidence.
All nine selected final raw records bind the exact tested/base SHA and commands,
exit zero/PASS, and recompute their recorded raw hashes and byte counts. The full
task check evidence reports 790 harness tests and 232 unit tests passed; these
existing raw logs were inspected, not rerun as full suites during review.

HG043 integration provenance functions remain byte-identical. All five appended
normal integrations replay successfully through the merged validator, bind actual
two-parent merges already in the protected base and preserve byte-identical
historical results with UNMERGED status. Reviewed regular Git blobs or proven
own-task linear review-only suffixes supply the review references; new integration
facts do not rewrite historical task facts.

Fresh focused command:
`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_m3_boundary_shadow_scope.py tests/unit/protocol/test_authorization.py tests/unit/contracts/test_artifact_registry.py::test_artifact_dependency_closure_required tests/unit/contracts/test_shadow.py tests/unit/protocol/test_execution.py::test_identity_and_wire_scope tests/unit/protocol/test_full_test_execution.py::test_strict_ingress --junitxml=docs/exec-plans/reviews/HG-042/final-24513e8-protocol-raw/focused.xml`

Result: 84 passed, zero skips/xfails. Own pure probes pass. The initial production
probe was rejected because the reviewer fixture used a SUBJECT actor ID different
from its subject; that initial log is retained. Correcting the review-only fixture
to a genuine valid production command proves parser acceptance followed by actual
TEST require_wire rejection. This was no implementation failure.

No full harness, local DB/Docker lifecycle, shared resource, GitHub action, source
edit or commit was performed. Hosted CI and other specialist review gates remain
separate prerequisites for merge.
