# KL-080 independent protocol review under HG049

Reviewed implementation/result: `275d7f849b31c9fe123c8d8594b88a85d1c25355`.
Protected base: `034d6301316d0dade784a61b159c027b83fbce3a`.
Corrective tested implementation: `f85277e27ab5393b7f77b6fea25d4197294d3153`.

**CHANGES_REQUIRED — the normal evidence gate and packet DoD remain unsatisfied.**
The review found no runtime protocol defect requiring a frozen-spec amendment.
This report supersedes the prior protocol conclusion for the revised HG049 oracle;
the earlier report files and historical evidence are preserved.

The review independently read AGENTS, the current authority index, the protected-base
HG049 packet/record, merged prerequisites, reviewer and protocol-guardian skills,
Protocol 3.2–3.3/6.2/coordination/T6–T7 clauses, DB S12/S13/S27/S36/S37/4.1,
and the current acceptance and merge/evidence contracts. All ten direct prerequisite
integration records are MERGED ancestors of the protected base. The tested-to-reviewed
diff contains only own task result/evidence/review artifacts; runtime and tests are
the tested bytes. No parent or sibling review conclusion supplied an oracle.

The actual runtime diff changes three files: pure admission/association comparisons,
strict persistence reader comparisons, and the narrowly extracted full-T6 exact-S13
freshness read. Physical S13 requires ELIGIBLE and physical S12 requires MATCHED.
Invalid source states fail closed; no alias conversion or mutation is introduced.
S27 ADMITTED remains an intent state, and S36 CONFIRMED remains a derived association
summary. Nutrition stays TARGET and Fitness prescribed values stay separate from
canonical actual execution. Registry and S01 lock order, command ownership, ingress,
request/fence/lease/control/revocation guards and transaction boundaries are unchanged.
No migration, wire/runtime registration, CI, frozen authority or requirement-status
change occurs. No new external wait appears inside a coordination transaction.

`HG049_PROTOCOL/verify.py` losslessly decodes committed captures at the exact reviewed
revision, validates hashes and lengths, and examines raw JUnit and row witnesses.
The 17 task commands have matching successful captures: 106 own real-PG suite cases,
6 pure cases, 247 unit and 1,347 harness cases, with no failure/error/skip in their
JUnit. The independent raw hosted DB JUnit contains 780 successful cases. This is
tested-implementation regression evidence; it does not establish every normal PR gate.
The own suite has 106 namespace and 106 empty cleanup witnesses.

The raw owner trajectory independently binds exact source IDs/hashes/revision,
F→D→N, distinct TRAINING/NUTRITION S36 identities, one shared S37 action closure,
both T6 prescriptions/issuances and finite minimum validity, and both members'
START and RESUME bindings. Each START, RESUME and CONTINUE passes the actual
current-authorization guard twice. The test also verifies ordinary PAUSE and complete
source/preparation history equality. Exact identities are retained in the small
`HG049_PROTOCOL/verification.json` report. Production/evaluation peer assertions and
TEST_ONLY issuance/binding assertions preserve the non-executable shadow boundary.

The mechanical request uses its untouched owner-produced S37. Correct authenticated
ingress, current fence and daily-head locking pass before native
`prepare_authorization_basis` rejects `S37.ref_s34_id=N` against `D.ref_s34_id=F`;
N's demand link remains correct. The raw witness observes an empty first-use head
inside that transaction, then proves the entire before/after snapshot is identical
and no head remains. No request-construction, policy downgrade or later certificate
guard claim substitutes for that actual denial. The prior-deployment reconstruction
case verifies all 65 captured helper/runtime blob hashes against the protected Git
base and denies at `_progress_sources → _verify_full_progress` before freshness.
The seven predicate-support cases remain separately labeled support. F2 forward
repair, mixed-old-source denials, receipt-only historical replay, revocation/expiry,
concurrent dedup and rollback evidence preserve their stated boundaries.

**BLOCKER KL080-PROTOCOL-HG049-01:** independent normal-budget audit of protected base
to reviewed SHA finds 38,263,916 changed evidence/review bytes across 351 blobs,
exceeding the inclusive 16,777,216-byte budget. Four retained plain artifacts also
exceed 262,144 bytes: both prior source-suite logs and both prior harness JUnit files.
New lossless captures do not remove those normal-gate failures. The packet requires
all normal gates and DoD to pass; the result correctly remains BLOCKED/UNMERGED with
no product/M3/release PASS. Resolve this through authorized evidence storage/history
work without truncation, waiver or historical rewriting, then supply a new reviewable
revision and fresh SHA-bound review. No merge recommendation is made.

This review performed no DB lifecycle, implementation edit, commit, publication,
shared-governance/controller edit or external message. The only writes are its own
task-scoped review record, report and nested verification evidence.
