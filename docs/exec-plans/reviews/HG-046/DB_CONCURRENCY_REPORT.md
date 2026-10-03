# HG-046 DB_CONCURRENCY independent review

Status: CHANGES_REQUIRED. One BLOCKER; no other findings.

Identity: `harness-governance-v0.1/HG-046`; review contract v0.2.
Reviewed implementation/result: `dedf063f909419dd05e0f49e8a7e646903e3548a`.
Tested implementation: `c91d2635427a13a97a53fe4e52ec4655e1e7d866`.
Protected base: `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`.

## BLOCKER HG046-DB-001: manual executor leaks resources after uncertain creation

Location: `tools/harness/db_ci.py:327`, creation flags at 328/333 and conditional cleanup at 370–384.

The newly documented `db_ci.py local` entrypoint sets volume_created and container_created only after Docker returns success. A volume-create timeout after server-side creation skips all volume cleanup and records volume_removed=true. A docker run startup failure (including exit 126 after container creation) or timeout skips container cleanup and records container_removed=true; volume removal can then fail because the container still references it. With acknowledgement lost after successful startup, a privileged nested daemon can remain running. Returning overall FAIL does not fulfill promised owned-resource cleanup or make those removal assertions true.

Independent reproduction used the real db_ci.local with mocked Docker operations and temporary evidence paths; no Docker lifecycle was executed. Scenario 1: volume-create registered a created volume then raised TimeoutExpired; result exit 1, no remove calls, volume_removed=true. Scenario 2: volume creation succeeded and docker run registered a created container then raised CalledProcessError(126); result exit 1, only volume-rm attempted, container_removed=true and volume_removed=false. The mandatory controller fixes the analogous problem, but this separate public manual entrypoint still ships the defect.

Required correction: reserve exact ownership before uncertain creation; check absence first; inspect exact ownership labels before removal; attempt both cleanups after failed creation/start; record removal only after verified absence. Add focused tests for uncertain volume creation and container start/ACK loss on the manual entrypoint. This is an implementation correction, not a frozen-spec change. New implementation/results and reviews must bind the corrected revision.

## Scope and authority inspection

Read AGENTS, CURRENT_DOCUMENT_INDEX, own scope/governance, merged HG-045 governance, review contract, pr-merge-reviewer and db-transaction-reviewer skills, frozen DB sections 4–5, local CI policy and execution records. HG-046 is a governance change whose packet is its own scope/governance record. Inspected the protected-base diff and reviewed Git blobs independently.

Git confirms protected base and tested SHA are ancestors of reviewed SHA. The tested-to-reviewed commit changes only own HG-046 governance/evidence. No runtime, tools/db lifecycle, migrations, frozen Protocol/DB/baseline, historical completed result, or KL-074 hosted workflow/probe changes. Only the two authorized tests/db workflow compatibility blocks change; fixtures and behavior oracles remain intact. All 20 existing m2_/m3_ validator function source bodies are byte-identical to merged HG-045 base. M3 closure changes only add isolated local execution and preserve every existing command/contribution/hash/raw-identity requirement.

T1–T8, SafetyRegistry/S01 lock order, idempotency, leases/fencing, call ledger and provider/production/shadow boundaries are unaffected. Image/dependency waits are orchestration outside coordination transactions. Real PostgreSQL regression uses unchanged fixtures/selectors; aggregate PASS is not new product/source-conformance certification.

## Mandatory controller and selected execution evidence

Mandatory local_gate uses a unique outer container and fresh named data volume, Git bundle source copy, no host path/socket mount, local Unix Docker endpoint and initially empty nested daemon. Candidate code does not select the controller plan. Reserved ownership and cleanup_owned handle uncertain create/start outcomes, validate exact labels, remove only owned resources and verify absence. Cleanup failure cannot publish PASS. The installation lock serializes a controller installation; separate nested daemons isolate runs despite legacy fixture names.

Read controller-c91d263 receipt and worker-receipt as regular blobs at reviewed SHA and verified embedded worker equality. Snapshot binds repository 1377771702, PR90, protected base and tested SHA; tree is a04b4c35d37f763ead147a6b9789de85256a54ab and controller identity f3525a8ca06c09da26620640c6ea24d0823d41771dc2b2c86f5d32603b17754a. Verified all 21 artifact hashes and all 16 command raw hashes/lengths, successful exits and uninterrupted flags. Commands cover image/dependency setup, lint/typecheck, unit/harness, test-only harness validation, DB collection/execution, Compose/readiness/reset, peer creation/isolation and destroy/removal.

Collection/execution contain identical 674 unique DB nodes, both exit 0. Exact JUnit classname/name identities match those nodes. DB JUnit contains 674 cases, harness 1037, unit 241; every suite has zero failures, errors or skips. Raw logs report 674 passed in 1456.64s, 1037 passed in 133.24s and 241 passed in 9.71s.

Reset proves three resets and sentinel removal. Isolation binds primary kl_workspace_5b88c45d9ce0 and peer kl_evidence_bdea8a308b1f with peer_cannot_see_primary_probe=true; peer checkout uses tested SHA. Destroy and peer-remove exit 0. Outer container kl-gate-2440e41bd01a45e48ef7ffa52ad6fdbf has only its named data volume mounted at /var/lib/docker. Receipt records verified outer removal and environment readback records both absent. Image sha256:72743a669165200bc169ab62f78f99f4979a43f86ef40c1993da87b86add1069 is Linux ARM64.

Independent focused run: `/private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_local_gate.py tests/harness/test_db_policy.py tests/harness/test_local_db_ci.py` — 112 passed in 2.88s. The additional mocked reproduction exposes manual-runner coverage missing from those passing cases.

## Limits and disposition

Selected controller evidence is valid local test-only quality/DB/lifecycle proof. It is not final App publication, review admission, hosted/x64 qualification, M3/product/release PASS, merge or activation. Final exact-current-head controller execution/publication remains after reviews. No credential/configuration access, installation, full DB rerun, Docker lifecycle, commit, push or merge was performed.

CHANGES_REQUIRED binds reviewed SHA above. Valid execution evidence does not close HG046-DB-001. Correct manual cleanup and obtain a fresh SHA-bound review.
