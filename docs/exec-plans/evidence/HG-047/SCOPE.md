# HG-047 integrated compact evidence

Protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
This continues PR 91 on its existing branch/worktree. The HG-047 validator allowlist
enumerates the exact compact implementation, tests, policy/contracts, derived
metadata, own governance/evidence/reviews, and the minimal trusted decoder
installation/copy compatibility paths. GENERAL, PROTOCOL and
SECURITY_DATA_BOUNDARY fresh review are mandatory.

Merged HG-045 source-decision authorities and HG-046 CI governance, evidence,
reviews, workflows, classifier and execution policy are preserved. The only
controller implementation changes add the compact decoder to the pinned asset
set and worker copy set. Existing tests and new isolated tests cover that trust
boundary. Historical compact runs remain accessible at the exact original SHA
and paths documented in HISTORY.md; none is new HG-047 PASS.

Local required checks: compact/controller/M3 focused regressions, full harness,
unit suite, lint, typecheck, check-harness, protected-base scope/frozen preservation
audit, Git diff hygiene, and exact committed compact retrieval/budget audit.
The full DB suite is intentionally left to one final reviewed-head trusted
controller run. This change is classified as full DB required by the unchanged
HG-046 policy. Task-local PASS does not claim CI, review, merge, requirement or
release PASS. Product requirements remain NOT_RUN.

Before final App publication, the administrator must install the reviewed
controller/validator/decoder release and updated full pins, then issue exact
final-head/controller admission. No installed configuration, key, admission or
protection is changed by this work. Root coordinates reviews, installation,
the mandatory full DB/controller gate and final merge.
