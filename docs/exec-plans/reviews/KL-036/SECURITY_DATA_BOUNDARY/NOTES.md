# Independent SECURITY_DATA_BOUNDARY review

Task: `harness-backlog-v0.2/KL-036`.
Reviewed SHA: `96ebb9e0e95211fc684273e7b69a49dc11e11e87`.
Protected base: `af09be228fbc89d074b6e863c83e1fdda343d55b`.
Verdict: PASS; no BLOCKER, REQUIRED_FOLLOWUP or NONBLOCKING findings.

This review independently read the packet, current index, AGENTS.md, review skill,
review/storage/resource/M3 contracts, named prerequisite results and integrations,
the relevant frozen Protocol sections 2, 6.2–6.7 and T5/T8, DB S01–S04/S27–S32 and
sections 3–5, relevant release/plan boundaries, and merged owner contracts/APIs.
All five prerequisite merges are ancestors of the protected base. The 387 changed
paths stay within the packet implementation and task bookkeeping scope. The full
source/test/contract diff and committed result were inspected directly; no other
review verdict was used. No source changes, tests, lifecycle operations, installation
changes, App/full-DB gates, commits or network calls were performed during review.

## Authority and data boundaries

`persistence/worker_reaper.py:30–46,83–91` requires an exact typed TEST identity,
registered subject/policy/environment/principal, idle internal service session,
`current_user=session_user`, and a service user separate from the registered client.
`transactions.py:5429–5447` repeats registration under S01 and binds the active policy
before historical replay or first-use work. Requests cannot supply callbacks, SQL,
accepted time, terminal targets, compatibility flags or budget authority. The
nullable owner is restricted to the unacquired ADMITTED/PENDING, fence-zero, CREATED,
null-expiry basis and matched again against current database facts.

The private prepared entrypoint derives S27/S29 terminal targets after exact locked
request/attempt/owner/fence/deadline/status comparison and fresh database time
(`transactions.py:5476–5506`). Deadline closure uses DEADLINE_EXCEEDED/LEASE_LOST;
lease-only closure requires the exact registered TEST recovery-cancellation policy.
Restricted mutation/completion guards require the entire prepared values for one
exact chain. The old generic synthetic branch remains byte unchanged, separate from
this private branch. The new worker calls existing acquire/renew/progress owners;
neither new loop grants authorization, dispatch or success.

Discovery commits before coordination. Required SQL witnesses show S01 then S27,
sorted S31, S02 and S29; stale candidates and tampered facts preserve all relations.
Historical outcomes remain authenticated and executable=false, changed hashes
conflict, and absent receipts cannot fabricate replay. Unknown cleanup delegates to
the existing ledger owner in separate transactions. Occupation survives interrupted
cleanup; permit beats cancellation; reliable late settlement preserves terminal
planning state and cannot restore dispatch or T6 authority. Actual T6 success is
produced by the merged owner and its complete history survives reaper competition.

No remote model/provider call, health-data export or actual-execution write is added.
Frozen files, grants, schemas, migrations, CI and shared lifecycle helpers are
unchanged. Production auto-activation and shadow execution remain disabled.

## Environment and credential evidence

The task-owned constructor and nested lifecycle gates validate full tested HEAD,
resolved root, SHA7/ROOT12 names, fixed Compose file, exact command shapes and SQL
targets before runner I/O (`tests/unit/workflow/test_worker_reaper.py:31–139`).
Negative assertions cover nested overrides and readiness/SQL targets; the runner is
never called on those paths. Seed resets also verify the exact database/service
identity before setup. Recovered before/after inventories are equal for foreign
databases/projects/containers/volumes/networks. The exact own namespace is removed;
all 18 owned suite children are joined/terminated, including the intentionally killed
worker. Real worker/reaper/admission PIDs 12120/12122/12121 are distinct; the worker
exits -15 after a committed heartbeat while the reaper reaches terminal closure.
Wait witnesses show idle sessions, null transaction starts and no tuple locks.

Local DSN/container representations are redacted, connection/bootstrap errors avoid
credential details, and inventory excludes command arguments and connection strings.
The launcher refuses capture of known local setup credential tokens or PostgreSQL
URLs. Its only exception removes the exact tracked synthetic password-mutation test
identifier from inspection while preserving raw captured bytes. Independent scanning
of every changed diagnostic recovered no matching setup credentials outside that
identifier. Source guard literals were inspected separately, not classified as
diagnostic disclosures.

The early failed captures remain FAIL and explicitly sanitized/non-eligibility
diagnostics. The five original local files were read only for length/hash comparison;
all pinned hashes match and the containing quarantine directory is mode 0700. No
original content or credential was printed, copied into review evidence or recaptured.
Sanitized records were never treated as lossless final execution evidence.

## Exact evidence verification and limitations

The audit reads regular Git blobs at the reviewed SHA, verifies each compact payload's
stored/raw lengths and SHA256, single-member gzip closure and same-directory path,
and checks exact tested SHA/command/exit metadata. All 16 final checks are present.
Every final pytest collection ID matches execution start, all setup/call/teardown
phases pass, and JUnit identities/counts match without skip/error/failure substitutes.
Counts are 1 per selector, 2 task unit cases, 7 DB cases, 249 unit regressions and
1,492 harness cases. The final harness manifest is clean, complete and SHA-bound.
Raw lint, typecheck and harness-validation logs show successful exits. All 187
changed diagnostic envelopes were hash-verified, including superseded failures.
The tested-to-reviewed diff contains only the own result and evidence; implementation
and tests are unchanged since `6a3f10ef424f41bb690d8835f952484b0ca4f87b`.

Privileged internal TEST service sessions and S26/S34–S37/COMMIT_READY preparation
seeds are declared instrumentation. They do not prove restricted-login ACL
containment, complete planner workflow, product/W/I/M4/release readiness or installed
App/full-DB admission. The result correctly has empty requirements_covered, UNMERGED
integration and null merge_commit. Those coordinator gates remain separate.

`AUDIT.json` records independent verification counts and witness kinds; `audit.py`
reproduces the read-only checks without emitting recovered raw data.
