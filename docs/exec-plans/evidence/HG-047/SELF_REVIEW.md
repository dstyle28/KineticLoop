# HG-047 integration self-review

This review binds implementation `2dc15b7c79b835197449ca705f82f221eee6f05d`
against protected base `391c9198fa8ec647e377a0572700bc7568468c85`.
It is author self-review, not an independent review or merge authorization.

The normal two-parent merge `ab4f21b9432240547555b73b4be341ad843bef39`
preserved current master ancestry. Shared index/manifest hashes were regenerated
from merged bytes. Conflicts in governance/M3/merge contracts retained the merged
CI/source-decision text and appended compact policy references. Both M3 test
families and validator gates were retained. HG-047 now has its own exact write
allowlist and mandatory GENERAL/PROTOCOL/SECURITY_DATA_BOUNDARY reviews.

The selected scope audit proves zero changes to merged HG-045/HG-046 evidence,
reviews and governance, source-decision packet/schema, workflows, DB tests,
runtime, migrations, frozen authorities, requirement set and task projections.
The only controller edits add the decoder to installed pins and worker copy
lists. Negative tests prove missing/drift/symlink pin rejection, isolated import
from the installed release, no candidate decoder fallback, and installed worker
copy provenance. No live controller, key, admission or protection was changed.

Selected command envelopes preserve exact raw bytes, hashes, lengths, timestamps,
commands and exit codes. Full harness includes the compact and M3 semantic
negatives. The initial repeated-read regression is corrected through a bounded,
validation-operation success-verdict cache and fewer uncached Git calls. It
retains no raw bytes, caches no mutable refs/working files/failures, keys all
bindings, and clears on operation exit. New regressions verify missing/corrupt
objects in later operations, owner/repository/constraint separation, mutable
freshness and cleanup. The committed bounded benchmark records exact prior/new
source SHAs, call counts and monotonic durations. Lint, typecheck, unit, authority, scope and source-diff checks passed
at the same implementation SHA. Old compact rounds and reviews remain historical
at their original Git paths/revisions; none is relabeled as HG-047 evidence.

Full DB, fresh independent reviews, quality/merge checks and the dedicated App
gate remain separate obligations. The administrator must first install a reviewed
controller/validator/decoder release with a complete new pin map, then admit the
final reviewed PR SHA. Product/release requirements remain NOT_RUN.
