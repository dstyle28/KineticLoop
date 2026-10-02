# HG043 independent DB/concurrency review

Reviewed SHA: `2896d2422999fdf8a2cbca75eb316798c015ad17`.
Protected base: `1099d85bd4aa76ec8221700e55b4e77a84479126`.

Status: **CHANGES_REQUIRED**. One BLOCKER: the review-evidence fallback treats an
existing nonregular path as absent. `review_evidence_exists` first asks whether the
reviewed path is a regular blob, then permits a regular blob at the recorded review
commit if the suffix is own-review-only. A symlink, tree, or gitlink can therefore
be replaced at the same own-review path and accepted. The new contract permits this
fallback only for a reference absent at the reviewed SHA. Exact reviewed-source
reproductions in `nonregular-replacement.json` prove all three cases pass with zero
integration errors. Require explicit Git-entry absence before fallback and real Git
regressions for all three modes, followed by fresh SHA-bound reviews.

The actual change has no T1–T8, transaction owner, PostgreSQL privilege, SQL,
coordination row, lock, fencing, idempotency, outbox, migration, DB test launcher,
namespace, CI, frozen authority, task packet, task result, requirement or production
activation change. Frozen Protocol section 8 and DB sections 4.1–4.2 remain byte
identical. S51 before S01 and the remaining frozen lock order, external work outside
coordination transactions, DISPATCH_INTENT-before-send and lost-owner denial are
unaffected. No real database lifecycle is needed to establish this validator-only
finding; no database namespace was started, reset, seeded or destroyed.

The reviewer independently audited the actual five candidate chains from protected
Git ancestry, without using the implementation's suffix or blob helpers for that
proof. KL027, KL075, KL076, KL077 and KL079 all have genuine two-parent normal
merge commits containing their recorded review commit as a parent. Their
reviewed-to-recorded suffixes are ancestral, linear, and limited to their exact own
review directory. Task results are byte identical from result commit to reviewed
SHA. All 12/13/13/14/14 task-check references respectively are regular Git blobs at
reviewed SHA and unchanged at recorded review commit. Review-created references
number 18/3/1/0/0 respectively; every such reference is a regular Git blob at the
exact recorded review endpoint and has unchanged bytes in its normal merge.

KL075's independent 56-case DB log/XML, KL076's independent 68-case DB log, and
KL027's independent namespace plus four-operation DB logs/XML are committed review
bookkeeping. They are distinct from the tasks' pre-review acceptance evidence.
KL027's earlier unavailable attempts remain explicitly classified as unsuccessful
attempts in the audit. No independent reviewer run is promoted to task acceptance,
requirement PASS, release PASS or production activation. KL077/KL079 use ordinary
reviewed-revision references and need no evidence fallback. The original validator
rejects 18/3/1/0/0 refs respectively; repaired candidate replay otherwise accepts all
five. These records remain hypothetical integration fixtures; this review writes no
official integration record.

The focused real-Git regressions pass all 34 cases, covering regular blobs, strict
endpoint binding, working-tree independence, traversal/prefix/foreign/missing paths,
directories and symlinks, later unbound additions, code/result/task-evidence edits
and reversions, nonlinear suffixes, nonancestral exact-tree attempts, delayed review
with unrelated chronology, and complete-tree squash versus near match. Existing
task semantic evidence validation remains bound to reviewed SHA and rejects a task
check that claims a future reviewer log. The additional independently constructed
nonregular replacement cases expose the gap missed by these passing tests.

All eight final committed governance checks were independently checked for exact
tested SHA, PASS exit status, raw byte count and SHA256. Earlier failed fixture
evidence is retained and is not used as PASS evidence. Applicable final hosted CI,
the corrected implementation and fresh independent reviews remain merge conditions;
this review does not approve the current SHA for merge.

The broader existing validator regression run was safely interrupted (exit 130) on
review coordinator request after the exact-SHA blocker was established. Its partial
pytest output was not returned by the subprocess capture, so no counts or PASS are
inferred. Duplicate dynamic candidate replay was not reached (NOT_RUN); the separate
independent static five-chain audit is complete. The corrected revision requires its
own checks and fresh reviews.
