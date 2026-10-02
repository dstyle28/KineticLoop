# HG-046 DB_CONCURRENCY independent review

Status: PASS. Zero BLOCKER, REQUIRED_FOLLOWUP, or NONBLOCKING findings.

Identity: `harness-governance-v0.1/HG-046`; review contract v0.2.
Reviewed implementation/result: `2f7c4f50c08b21ed89ef361bd7f7b2161b6bf965`.
Tested implementation: `341333dd4b5140ac15f715ce28bd0d2a4a4ee1ec`.
Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.

## Independent scope and authority inspection

Read AGENTS, CURRENT_DOCUMENT_INDEX, HG-046 scope/governance, Thread Review Contract, pr-merge-reviewer and db-transaction-reviewer skills, frozen DB sections 4–5, and relevant KL-074 requirements. Inspected the actual protected-base diff and raw evidence. Git confirms base → tested → reviewed ancestry. The tested-to-reviewed suffix is one commit containing only HG-046 governance/evidence; the implementation did not change after execution.

No runtime, migration, Compose, frozen Protocol/DB/baseline, historical completed result, KL-074 hosted workflow/probe, or old HG-044 evidence changes. Only the two declared database-test workflow compatibility blocks change. KL-074 proposal equality, workflow hash, six negative mutations, branch/repository/head restrictions, hosted runner, locked uv, no continue-on-error, and always-upload checks remain unchanged. The generic legacy pins now assert the authorized prospective CI policy. The former review-push paths-ignore check now requires exclusive manual DB dispatch and no historical auto-writeback. These changes alter no DB fixture or behavior oracle. The exact HG-046 scope exception does not authorize other tasks or database tests.

An independent AST/source comparison confirms all 20 existing m2_* and m3_* validator functions are byte-identical to the protected base. Existing M3 collection/contribution rules and task-specific hosted requirements remain authoritative.

## DB isolation, lifecycle and concurrency

The wrapper creates one uniquely named disposable Linux container and a fresh owned Docker data volume. Source is copied by Git bundle; no host directory/socket mount or credential environment is supplied. Proxy forwarding and ambient remote-builder overrides are rejected. Inner preflight requires clean exact HEAD, supported Linux provenance, default local Unix daemon, and no initial containers or volumes before lifecycle/reset/destroy. Rejected preflight does not clean an unowned daemon.

Legacy fixture namespaces execute inside the owned nested daemon. The detached peer uses the same tested SHA with a distinct worktree-derived DB/Compose namespace. Cleanup uses existing lifecycle ownership, removes the peer checkout, then removes only the owned outer container and volume. Nonzero commands, interruption/timeouts, failed lifecycle cleanup and failed outer removal cannot return a passing run.

T1–T8 code, SafetyRegistry/S01 lock order, fencing, idempotency, call ledger, authorization and Evidence Admission remain unchanged. Image/dependency network work is CI orchestration outside coordination transactions. The unchanged real PostgreSQL regression suite supplies DB proof.

## Verified selected evidence

Ran the Git-bound full_database_evidence_errors validator against the reviewed SHA and tested SHA: no errors. Independently verified regular reviewed Git blobs, exact inspected bytes, required commands/selectors, exit codes, interruption flags, raw hashes/lengths, and collection/execution/JUnit agreement. All 11 execution checks have exit 0. Collection/execution contain the same 674 unique DB node IDs; JUnit reports 674 tests, zero failures/errors/skips. Raw output reports `674 passed in 1601.80s`.

Lifecycle logs prove Compose validity, readiness in the derived primary database, three resets with sentinel removal, distinct primary/peer namespaces and `peer_cannot_see_primary_probe: true`. Destroy and peer removal pass. Final inner inventories contain no containers or volumes.

The outer envelope binds the tested SHA and image ID. Container is `kineticloop-db-ci-341333d-cc86e43924e9`; its only mount is the named volume `kineticloop-db-ci-341333d-cc86e43924e9-data` at `/var/lib/docker`. Envelope status is PASS and both container_removed and volume_removed are true. This reviewer inspected committed cleanup records without executing a new Docker lifecycle.

All eight selected check JSON/raw-log pairs match the tested SHA, successful exits and exact raw SHA256/lengths: focused 58 PASS; harness 932 PASS; unit 241 PASS; lint PASS; typecheck PASS for 156 files; check-harness PASS; scope/frozen audit PASS; diff whitespace PASS. Earlier failed/interrupted attempts remain development records and are not selected evidence. The preliminary independent runner-test execution passed 35 cases; final assessment uses the final committed 58-case evidence and inspected source.

## Limits and disposition

This is local Linux ARM64 evidence, not hosted/x64 attestation. Hosted fallback was not dispatched for HG-046. The privileged executor is for trusted project code, not hostile-code isolation. Inner manifest validation is complemented here by separate inspection of the outer envelope. No product, M3/release, hosted CI, merge, or production activation PASS is inferred.

DB_CONCURRENCY PASS binds only the reviewed revision and permitted own-task REVIEW_RECORD_ONLY suffix. The result remains immutable. This reviewer performed no full DB rerun, commit, push, or merge.
