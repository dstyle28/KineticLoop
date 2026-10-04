# HG053 independent DB concurrency review

Review: PASS, zero BLOCKER or REQUIRED_FOLLOWUP findings.
Reviewed result R: `2936848abed73320db56f71a649e86eca1497502`.
Tested source C: `a75a41edfb1b58828b81053b4ac3afa51457a279`.
Protected base B: `c82e50aefad5c4d9e325d4928a8f96032b81192d`.

This is a prospective packet/governance review. KL036/KL037 runtime implementation,
their future PU/DC/WF selectors, product requirements, production permissions and
the installed App/fullDB gate remain separate and unproved by this PASS.

I read the actual B..R diff, execution packet, current index, frozen Protocol
sections 2, 6.2–6.7 and 8, frozen DB S01–S04/S27–S32 and sections 3–5, resource and
review contracts, relevant merged prerequisite result/integration records, actual
transaction/planning/progress/ledger/T6 code, baseline ACL and subject registration
migrations, lifecycle implementation and legacy transaction regression.
The repository pr-merge-reviewer and db-transaction-reviewer skills guided review.

The exact declared files match the 93-file B..R diff. Changes are limited to the two
active packets, their backlog/traceability projections, existing index/manifest
bindings and HG053 evidence/result bookkeeping. C is an ancestor of R; C..R changes
only HG053 evidence and governance result files. Runtime/tests/shared validators,
grants/migrations, completed records, frozen files and unrelated packets are not
changed. Actual prerequisite integrations are ancestors of B and their results
record task/check PASS. KL075 is the actual RecordSnapshot/AdvanceAttempt owner.

KL036 maps lease acquisition/renewal to the existing T5 owner and cleanup to T8.
The candidate scan releases its read transaction before S01; completion then uses
S01 → S27 → sorted applicable S31 → S02 → remaining S29. Post-lock trusted time,
exact request/attempt/owner/fence/deadline, positive current-worker execution,
stale-candidate denial, complete rollback, first-use idempotency and immutable
historical replay are explicit oracles. Independent OS worker/reaper processes,
bounded barriers/joins and PostgreSQL blocker witnesses exclude thread-only proof.
MarkUnknown/late settlement remain separate ledger owner transactions; unknown
occupation cannot refund budget or restore worker/T6 authority. Existing T6 commits
the positive success-preservation oracle rather than seeded committed outcomes.

Three preliminary feasibility findings were resolved in the actual final packet:

- The existing ReapIntent completion set incorrectly serves both S27 and S29.
  The new authenticated wrapper must establish private server-derived strict
  frozen target values, reject generic FAILED/caller-selected status/compatibility
  flags/absent or mismatched basis, and preserve the generic legacy branch for
  unchanged synthetic regressions. This avoids silently widening terminal sets or
  making existing `test_transaction_interfaces.py`'s FAILED assertion impossible.
- Actual admission produces NULL owner/fence0/current CREATED attempt. The
  specialized ReapIntent basis may accept only that exact unacquired root after
  its deadline using null-safe comparison, with a positive dedicated DC selector.
  Generic fencing/CAS and exact status/request/attempt/deadline checks remain intact.
- Registered TEST clients have no writer memberships; existing positive typed
  owners use privileged internal service sessions. Packets now disclose this
  architecture, retain the service/client distinction required by progress/T6
  guards, and require owner mediation of every tested effect. They make no
  restricted-login ACL containment or production permission claim. No ad hoc SQL,
  grant/trigger bypass or target-state seeding is authorized.

KL037's actual physical S04 has delivery_status, attempt_count, next_attempt_at,
typed_payload and immutable event reference, with the existing dispatcher SELECT/
UPDATE role. Operational claim identity/expiry/ACK diagnostics fit that metadata;
no new column/status/grant is needed. Queue-only claim/reclaim/ACK compare current
identity under S04 locks; stale ACK cannot overwrite replacement. Transport and
actual KL024 business consumer execute after queue locks release, on fresh idle
connections. Event/destination/operation keys and owner-computed canonical hashes
support first-use contention, ACK loss and redelivery without a synthetic receipt
store or duplicate business effect. Explicit event/destination policy excludes
self-triggering admission chains. Originating control invalidation commits before
delivery and is tested through fresh eligibility denial.

Both tasks serialize transaction_interfaces/user_coordination/planning_ledger and
the shared transactions.py path. Disjoint new files or database names do not
override serialization. SHA7/resolved-root SHA12 namespaces, before/after database/
Compose/process inventories, nested lifecycle validation before I/O, bounded child
cleanup and unchanged foreign resources are explicit acceptance conditions using
the existing lifecycle. Missing capabilities outside these exact scopes require
separate prospective governance; frozen semantic changes require SPEC_CHANGE_REQUIRED.

Evidence was independently recovered from regular Git blobs at exact R, not the
working tree or referenced temporary logs. For every required capture I verified
stored/raw byte counts and SHA256, decompressed bytes, exact C/command/exit metadata
and result/index agreement. Recovered unit JUnit contains 247 unique passing cases.
Harness serial and both worker collections, 1492 unique started nodes, JUnit IDs
and all 4476 setup/call/teardown passing reports agree; runner manifest binds C,
clean source, complete execution and exit0. Failed/skipped/error counts are zero.
Parameterized JUnit node IDs were normalized without splitting parameter contents.
Envelope regex counts were not used as semantic execution counts. Superseded
failure/interruption captures are retained and are not final acceptance evidence.

Reproducible independent audit: `db/verify_review.py`; results: `db/VERIFICATION.json`.
No database/App execution, source mutation, foreign review edit or commit was done
by this reviewer. Final runtime concurrency behavior still requires the future
task implementations and exact process/SQL oracles described above.
