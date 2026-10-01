# Deterministic TEST preparation

The four typed preparation services accept a separately authenticated
`ProgressIdentity` and an exact `PreparationRequest`. `ProposalService` records
FITNESS or NUTRITION in S34, `DemandFeatureService` records S35,
`EvidenceResolver` records S36, and `ValidationService` records S37. Requests
contain the current root/request/attempt, expected owner/fence, manifest/epoch,
stage and immutable source IDs/hashes. FITNESS repair additionally names its
actual prior FITNESS revision. Callers cannot submit output payloads, certificates,
SQL callbacks, trusted time, lease expiry, new fences or budget changes.

The public owner matrix and command registry remain unchanged. Generic
`execute_preparation` cannot insert or update S34–S37. Read-only preparation
introspection and the merged KL078 projection/build ingress retain their existing
boundaries. The exact fixture service computes immutable bytes outside coordination,
then enables its private guarded entry. Persistence orders S01 → S27 → S02 → S29,
authenticates the registered TEST policy/environment/principal, and shares KL075's
current request, attempt, lease/fence, deadline, manifest/epoch, stage and protective
control guards. A post-S29-lock database clock determines acceptance. The same S03
event records that time; one output, receipt, event and outbox commit atomically.
The restricted output capability permits only the exact server-generated row.
Updates to output history are forbidden.

The fixture requires an explicit immutable policy, the bounded unrevoked runtime
artifact identity/hash/version, a published manifest and its real SEALED FULL
factset with at most 64 members. The merged canonical reader verifies reconstruction
outside coordination. Persistence rechecks the captured immutable rows and runtime.
Only admitted, same-policy, USER_REPORTED evidence with command authority NONE,
confirmed same-event associations and canonical WORKOUT_ACTUAL source facts can
supply actual quantities. Sealed membership includes the facts and their admission
and association revisions. Missing provenance or source/hash mismatches deny.

`kl076-mechanical-test-v1` has an intentionally small mechanical domain:
`fixture:cycle`, integer minutes from 1 through 60, empty equipment constraints,
an explicit aware half-open source window, and integer fixture units. Demand is
recomputed from the exact FITNESS payload: prescribed minutes equal action minutes,
target units equal minutes, and the estimate interval is `[2m, 2m+1]`. Nutrition
requires that exact Demand and sets target fuel to `3m`. These fields respectively
retain PRESCRIBED_QUANTITY, TARGET and ESTIMATE semantics. They never create actual
execution. Fixture units have no clinical or nutritional interpretation.

Resolution derives action-scoped support, contradictions, association status,
coverage, consistency, retractions and expiry from the captured admitted sources.
Coverage compares complete sealed membership with the policy's declared membership;
citations cannot assert completeness. Validation reconstructs the resolution and
recomputes Demand and Nutrition. It denies missing, contradictory, incomplete,
truncated, mixed, hash-swapped or expired sources. Exposure with an unknown upper
bound denies. Actual exposure deduplicates by underlying event ID; contradictory
duplicate quantities deny. An actual may replace exactly one named reservation
slot. Actual upper bounds, unreplaced reservations and the new prescribed minutes
must total at most 90. Validation also checks the cross-domain fuel equality and
binds the current execution-basis event. Only these mechanical predicates yield
the fixture semantic/envelope PASS fields.

S34 Nutrition's `demand_feature_id` → S35 `ref_s34_id` → S34 FITNESS is the existing
same-subject FK chain. Payloads duplicate and verify exact F/D identities/hashes,
snapshot/context, root/request/attempt, manifest/policy, version and source ranges.
The fixture needs no additional direct-F Nutrition column or migration. S37 binds
Nutrition, Demand, Resolution, manifest, policy, request, attempt and execution
basis. These records are preparation prerequisites and carry `executable=false`.

Only KL075 advances stages. F1 repair uses actual KL024 constraint revision under
the same root to create a new request and attempt, then acquire/snapshot and follow
the forward stage chain. F2 binds F1 as immutable parent and recomputes D2/N2.
Root budgets and deadline remain intact; F1/D1/N1 history remains immutable and
cannot validate the new attempt. This task stops at COMMIT_READY. It creates no
bundle, head, prescription, authorization, execution binding or root success.
Authenticated ACK-loss replay returns historical IDs with `executable=false`;
an independent new operation still requires current authority.

The PostgreSQL suite first proves its namespace in pure tests, then passes the
selected lifecycle to the migration bootstrap. Each case uses a fresh database
because the canonical principal has one subject binding. Its fixed fixture label,
HEAD first seven hex characters and SHA256 of the resolved root first twelve hex
characters derive both the Compose project and database. Construction, nested
bootstrap/reset and every cleanup validate that exact namespace; every connection
checks `current_database()`. Finally cleanup inventories only the owned Compose
resources. Legacy DB regressions remain in the unchanged hosted CI lifecycle.

Task checks, independent review, integration and product/release status remain
separate. This mechanical fixture makes no product quality, clinical, production
activation or real-data shadow release claim.
