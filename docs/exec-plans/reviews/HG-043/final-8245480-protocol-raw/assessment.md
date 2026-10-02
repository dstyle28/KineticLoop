# HG043 independent PROTOCOL review

Reviewed implementation/governance/evidence SHA: `8245480918251739339987de69bfe41fa0b39af5`.
Protected base: `1099d85bd4aa76ec8221700e55b4e77a84479126`.
Verdict: **PASS**. BLOCKER: 0; REQUIRED_FOLLOWUP: 0; NONBLOCKING: 0.

The reviewed diff is a harness governance provenance repair. No frozen table,
invariant ID, T1–T8 transaction boundary, application code, DB routine, migration,
provider adapter, production/shadow authority, task packet, product requirement,
release gate, CI configuration, or official integration record changes. Frozen
Protocol/DB and FROZEN_BASELINE bytes are unchanged; current authority hashes
are verified. No SPEC_CHANGE_REQUIRED condition was found.

Ordinary integration-review references require exact normalized repository-relative
paths to available mode 100644/100755 Git blobs at the reviewed SHA. The fallback
requires no exact Git entry of any type at reviewed, a regular available blob at
the exact recorded review commit, and ancestry plus a linear exclusively same-task
whole-component review suffix. Missing objects remain present entries and cannot
be replaced through the fallback. No ambient working-tree or later HEAD addition
supplies the bound evidence. Result, code and task-check evidence cannot be created
later through this exception. Reverted forbidden edits, other-task/prefix-collision
paths, nonancestral and nonlinear histories fail closed.

Independent reviewer checks at the reviewed implementation: 39 real-Git provenance
regressions passed; seven existing delayed-review/exact-tree-squash regressions
passed. Those cover delayed-review merge-tree identity, task changes after merge,
complete-tree equality, mode-only and unrelated-content differences, and ancestry
that exact-tree comparison cannot replace. The relevant delayed-postmerge freshness
and exact-tree squash implementation branches are unchanged by this patch. Delayed
ordinary evidence remains usable; delayed unrelated chronology cannot supply
review-created evidence through the stricter suffix proof.

A separate adversarial real-Git probe repeats the prior defect for reviewed
symlink, tree and gitlink replacements, then missing reviewed/recorded blobs.
The prior 2896d24 source accepted each constructed case; the final implementation
rejects all five with integration-review-evidence errors, even though their own-task
linear suffixes otherwise pass. The prior CHANGES_REQUIRED review round, old raw
probes and the 787663f missing-object reproduction remain untouched. Their prior
outcomes were not rewritten as PASS.

All eight declared final governance checks have committed evidence at the reviewed
SHA, exact tested/base/check/command binding, exit code zero, and verified raw
SHA256/byte count. The implementation, focused tests and two contracts are identical
between tested 97b76c7 and reviewed 8245480. The tested-to-reviewed governance suffix
is valid; the declared changed-file list exactly matches the protected-base diff.
The committed full harness suite reports 715 passes and the unit suite 232 passes;
those broad suites were audited rather than rerun for this independent review.

The reviewer reran all five real protected-ancestry normal-merge candidates and
independently audited their source objects with raw Git commands. Original/repaired
error counts are KL027 18/0, KL075 3/0, KL076 1/0, KL077 0/0 and KL079 0/0.
Each real merge has exactly two parents including the recorded review commit, and
is ancestral to the protected base. Every reviewed-to-recorded suffix commit is
linear and changes exclusively its own task review directory. Across the five
records, 497 ordinary references are regular available reviewed blobs and 22
review-created references are absent at reviewed and regular available recorded
blobs. The 66 PASS task-check references all resolve at reviewed; result bytes
match at result_commit and reviewed. Reviewer logs are classified as independent
review bookkeeping, never substituted for pre-review task acceptance.

Scope of the verdict: protocol review PASS for this exact SHA only. It is not
product requirement PASS, database runtime acceptance, release/production
activation, hosted CI PASS, or MERGED. Official integration records and other
work remain owned by their separate authorized tasks.
