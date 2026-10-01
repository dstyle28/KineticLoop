# KL-076 upstream preparation capability blocker

Task: `harness-backlog-v0.2/KL-076`. Assessed protected base and actual normal
KL075 PR74 merge: `d0470badf0ccf6bec28a9bc7e6836b57d9df93ce`.

KL076 is **BLOCKED**, with no implementation or product PASS. No DB lifecycle
has started. The five expected exceptions below were reproduced through the
actual merged `execute_preparation` gateway using an idle connection double.
This is a pure capability diagnostic, not PostgreSQL DC or packet acceptance.
Every rejection preceded any cursor SQL call.

## Missing upstream capabilities

1. **RecordProjection cannot insert S21 at all.** The S21 natural key requires
   `revision` (`src/kineticloop/persistence/metadata.py:118,150`). Its generated
   insert capability excludes that column (`transactions.py:599,725`). Omitting
   revision produces `StatementRejected: S21 insert omits required fields
   ['revision']`; supplying revision produces `StatementRejected:
   RecordProjection cannot insert columns ['revision'] on S21`. Both run before
   SQL (`transactions.py:965,1063`), so a SQL default cannot rescue the insert.
2. **RecordProjection S22 and BuildManifest S23 cannot bind a sealed factset.**
   `execute_preparation` constructs a restricted session without `locked_ids`
   (`transactions.py:5380`). Insert binding checks require a non-null `ref_s15_id`
   to name an exact locked `factset_revisions` row (`transactions.py:1204–1250`).
   Neither preparation owner has an exemption or a capability to acquire that
   lock. S22 FACTSET dependency insertion and both BUILDING/READY S23 insertion
   produce `GuardRequired: S22/S23.ref_s15_id must bind an exact locked row`.

Omitting dependencies is not a valid alternative: actual T3 joins S23 to its
same-subject factset and requires the exact current SEALED identity
(`transactions.py:4000`); every projection role requires a FACTSET dependency
and T3 validates its exact FK (`transactions.py:4066,4176`). S22 has no update
capability; BuildManifest updates cannot add the missing factset reference.
`execute_command` rejects preparation owners. Caller-created restricted sessions
with fabricated lock inventories would bypass the prescribed gateway.

Frozen DB S21–S23 already requires immutable, source-bound projection/build
preparation under these owners. This is a missing implementation capability,
not evidence that any frozen protocol semantic change is required.

## Evidence and disposition

- `entry-d0470ba.json` and `.log`: indexed hashes, actual prerequisite PASS
  results/reviews, result byte identity, normal two-parent merge ancestry and
  M2 PASS checked. KL075 integration bookkeeping is absent at this base;
  actual PR74 merge metadata and reviewed-SHA ancestry independently establish
  the normal merge, without manufacturing an integration record.
- `pr74-normal-merge.json`: actual GitHub merge metadata.
- `upstream_gateway_probe.py` and `upstream-gateway-d0470ba.log`: five expected
  gateway rejections; zero SQL calls; no lifecycle, PG or acceptance claim.
- `upstream-feasibility-d0470ba.json`: fresh independent read-only preliminary
  source assessment confirming both gaps. This is not the required final
  GENERAL/PROTOCOL/DB_CONCURRENCY implementation review set.

The packet's Source and output boundary and dispatch explicitly require a
separately bounded prerequisite for a missing upstream capability. No raw S15/S16,
S21/S22/S23, S24/S25, S26/S29, or S34–S37 output seeds may replace the actual chain.
Accordingly no application/test/contract/governance/CI/migration changes were made.
Twelve KL076 required checks remain NOT_RUN. `uv run kl check-harness` returned
HARNESS_CHECK_PASS for this BLOCKED bookkeeping, recorded separately; raw gateway
diagnostic evidence does not count as any selector, real-PG suite, or
production/layer acceptance PASS.

A separate bounded prerequisite must provide exact owner capabilities for
server-generated S21 revision completeness and immutable same-subject SEALED S15
references through RecordProjection/BuildManifest's independent short preparation
transactions. It must preserve public PREPARATION boundaries, execute_command
rejection, immutable history and frozen T3 current-basis guards, with fresh tests,
review and normal merge. Resume KL076 from that normal merged prerequisite and
latest protected base, after the authorized HG039 -> KL026 -> KL076 order.

No DB resources require cleanup. The blocked branch/worktree is retained; no
completed-task archive, implementation PR, or merge is claimed.

Coordinator disposition: the separate prerequisite route was accepted, with HG040
governance preparation underway. Keep the branch/worktree intact and wait for the
actual normal prerequisite merge and coordinator resume; no user intervention is
required for this implementation gap.
