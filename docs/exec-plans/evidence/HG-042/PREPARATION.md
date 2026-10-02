# HG-042 preparation and unresolved prerequisites

This is preparation, not governance/task/product/review/MERGED PASS. No final
protected base, tested revision, result, review or PR is recorded here. The
prospective KL028/KL029 checks and all 31 B-layer dispositions remain NOT_RUN.
Final tests and independent SHA-bound reviews wait for actual normal KL027 PR83
merge and a refreshed protected base with verified actual contracts/evidence.

Prepared scope: KL028/KL029 packets, their exact backlog/traceability projections,
the explicit M3 isolated parallel test and deferred-layer plan, suite resource
declarations, validator scope/ledger guards and own targeted harness tests.
Current authority and delivery-manifest hashes are refreshed mechanically.
No completed task definition/result/evidence, frozen authority, production
implementation, migration/grant, lifecycle/Compose or CI content is changed.

Read-only audits found 31 B obligations: 8 PU + 14 DC + 8 E2E + 1 WF. There are
19 definite prospective mechanical obligations plus conditional B04@DC; at least
11 remain deferred, or 12 if complete owner-produced reauthorization is absent.
Guard coverage cannot substitute for the full frozen B04 oracle. Missing product
API/rendering, B11/B12 pure commit-state evaluator, and B14 independent STOP lane
and worker-fault infrastructure remain explicit. No M3-to-M4 cycle is introduced.
M3 milestone schema/closure support remains a separate focused governance gap.

## Integration provenance barrier and separate remedy

`integration-preflight.json` records actual immutable results, reviewed SHAs,
review-only suffixes and normal merge ancestry, not fabricated integrations.
KL077 and KL079 candidates validate with zero errors. KL075 fails three cited
review-created refs absent from reviewed 5543bfb; KL076 fails one such ref absent
from reviewed 290a4d6. KL027 is still unmerged in this preflight and has 18
equivalent review-created references absent from reviewed ff93c08. Normal merge
does not retroactively place those bytes at the reviewed revision.

The current integration rule checks every review reference at reviewed_head_sha.
The task merge gate permits reviewer-created files in the proven linear,
task-scoped REVIEW_RECORD_ONLY suffix. Ordinary post-merge remediation cannot
replace existing required task review JSON because the governance gate requires
those review paths to be additions absent at its protected base.

Reserve a separate focused governance PR for this contract inconsistency; do not
mix it into HG042. A narrowly bounded prospective remedy can admit references
under the exact task review directory at review_record_commit only after proving
the complete reviewed-to-review-record suffix is linear REVIEW_RECORD_ONLY. Every
non-review reference must continue to exist at reviewed_head_sha. Negative guards
must reject wrong-task/foreign/missing refs, path-component prefix collisions,
non-review content changes, unrelated/merge suffixes and stale SHA chains. Retain
all existing result semantics and ancestry/normal-merge/full-tree rules. No
arbitrary HEAD fallback or historical PASS relabeling is admissible. Revalidate
all five candidates after that governance change and KL027's actual normal merge.

If the separate route instead uses fresh reviews of exact historical merge trees,
it requires an explicit narrowly scoped amendment permitting replacement of the
existing review records, followed by all required fresh reviews bound to the exact
merge SHA and matching integrations. It cannot use the existing additions-only
remediation rule unchanged. No such exception is implemented by HG042.

## Preparation verification only

Working-tree preparation checks: targeted scope/ledger suite 74 passed; harness
validator HARNESS_CHECK_PASS (76 tasks, 73 active); changed Python lint passed;
changed Python typecheck passed. These checks are diagnostics before the required
refreshed final base, not final tested-SHA governance evidence. A cached Python
3.12 runtime was used with this checkout's explicit src PYTHONPATH; no DB lifecycle
or unrelated resources were touched. Final checks must run again on committed
HG042 source after all prerequisites and the separate provenance remedy merge.
