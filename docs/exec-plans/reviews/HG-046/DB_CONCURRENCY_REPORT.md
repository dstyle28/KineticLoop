# HG-046 DB_CONCURRENCY independent review

Status: PASS. Zero BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING findings.

Identity: `harness-governance-v0.1/HG-046`; review contract v0.2.
Reviewed implementation/result: `65ab5bfc3608b477a301ded604ab6a63374a247a`.
Tested implementation: `8fb35e9364deb5cfbe1424535f046c744bf3b369`.
Protected base: `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`.

## Prior finding resolved

Independently inspected the correction of HG046-DB-001. The manual `db_ci.py local` executor now reserves both unique resource names before volume/container creation, including uncertain outcomes. Cleanup checks existence, verifies the exact run owner label before removal and verifies absence afterward. Container and volume cleanup are both attempted; diagnostic timeouts cannot skip either cleanup. Failure or unverifiable cleanup retains FAIL. Sixteen added scenarios cover volume-create timeout, create/start failure, diagnostic timeout, cleanup failure, missing/owned/foreign resources, inspect failure and resources remaining after removal. This fixes the prior finding without changing frozen semantics.

Independent focused verification used `/private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider tests/harness/test_local_gate.py tests/harness/test_db_policy.py tests/harness/test_local_db_ci.py`: 128 passed in 2.89s. No Docker lifecycle or full database rerun was performed by this reviewer.

## Scope and authority

Read AGENTS, CURRENT_DOCUMENT_INDEX, own scope/governance, merged HG-045 governance, review contract, pr-merge-reviewer and db-transaction-reviewer skills, frozen DB sections 4–5, local CI policy and execution records. Inspected the protected-base diff and committed evidence independently. HG-046 is governance work with its scope/governance record serving as the packet.

Base and tested SHA are ancestors of the reviewed SHA. The tested-to-reviewed suffix contains only own governance/evidence records. Runtime, tools/db lifecycle, migrations, DB fixtures, frozen Protocol/DB/baseline, requirement states, historical completed results and KL-074 hosted workflow/probe remain unchanged. The two authorized tests/db compatibility blocks replace obsolete generic workflow assertions. All 20 m2_/m3_ validator function ASTs equal the merged HG-045 base; M3 closure retains its existing commands, contributions, hashes and raw identities.

T1–T8, SafetyRegistry/S01 lock order, idempotency, leases/fencing, call ledger and provider/production/shadow separation are unchanged. Image/dependency/network waits occur in orchestration outside coordination transactions. Aggregate regression PASS does not resolve the separately recorded source-conformance work or create product/M3/release PASS.

## Isolation and failure behavior

Both local execution paths use a unique outer container and fresh owned data volume, Git bundle source copying, local Unix Docker endpoint and an initially empty nested daemon. No host path/socket mount or host networking is admitted. Separate nested daemons isolate existing fixture namespaces between runs. The controller installation lock serializes its own execution; its installed code selects the complete command plan and observes command exits.

Controller and manual cleanup reserve ownership before mutations, remove only resources with the exact owner label and verify absence. Failed commands, timeouts, incomplete execution, cleanup failure and stale live refs cannot yield successful publication. Collection/JUnit checks reject missing, skipped, mismatched or zero-case DB execution. Negative tests cover populated/remote environments before lifecycle, evidence drift, command/selector drift, timeout handling, cleanup ownership and stale controller publication. The privileged executor is restricted to explicitly admitted trusted project code as documented.

## Committed evidence verification

Read selected `controller-8fb35e9` and `checks-8fb35e9` evidence as regular Git blobs at the reviewed SHA. Verified receipt embedded worker equality; exact repository 1377771702 / PR 90 / base / tested snapshot; tested tree `1349cef6005fe2cf84624d652207ea4a5307e8cd`; controller identity `013d08d7a39ae1e6edc66ac490a4d5cca2cd772ad8c7ebc45a50fc03ec5eb319`; all 21 worker artifact hashes; all 16 command raw hashes/lengths, exits and interruption flags; and four focused/lint/typecheck/scope capture hashes and tested identities.

Commands cover image/dependency setup, lint/typecheck, unit/harness, test-only harness validation, DB collection/execution, Compose/readiness/reset, peer creation/isolation, destroy and peer removal. All passed. Collection/execution contain exactly 674 identical unique DB node IDs with exit 0; JUnit classname/name identities match exactly. DB has 674 cases, harness 1053, unit 241; all have zero failures, errors and skips. Raw logs report 674 passed in 1365.21s, 1053 passed in 120.56s and 241 passed in 7.91s. Selected focused evidence reports 128 passing tests.

Reset evidence proves three resets and sentinel removal. Isolation proves distinct primary `kl_workspace_5b88c45d9ce0` and peer `kl_evidence_bdea8a308b1f` namespaces and `peer_cannot_see_primary_probe=true`; peer checkout binds the tested SHA. Destroy and peer-remove exit 0. Outer container `kl-gate-c70a76f744034eaab83a1fe8b079f3b7` mounts only its owned data volume at `/var/lib/docker`. Both cleanup flags and independent environment readback prove container/volume absent. Image `sha256:77df0f68635d8cfc0e64f5a8270c22b9a5a14dde5d4b00ab43d86ebcc94f0bd6` is explicitly Linux ARM64.

## Disposition and limits

DB_CONCURRENCY PASS binds the reviewed implementation/result SHA above and closes HG046-DB-001. Review records cite committed current result/proof rather than the overwritten historical report blob. Only own review records were written; no implementation/result/evidence edits, credentials/configuration reads, installation, full DB reruns, commits, pushes or merges were performed.

Selected execution is explicitly test-only. It proves local quality/DB/lifecycle execution, not final review admission, App publication, hosted/x64 qualification, product/M3/release PASS or activation. Exact-final-head controller execution/publication remains a separate prerequisite after review. Any implementation/result change requires a fresh review; only the task-scoped REVIEW_RECORD_ONLY suffix is permitted.
