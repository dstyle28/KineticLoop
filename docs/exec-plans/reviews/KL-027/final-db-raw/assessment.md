# Independent final DB concurrency assessment

Reviewed HEAD: `ff93c08c7c32fba9e8dede0c161bb4f97bc98259`.
The reviewer independently applied db-transaction-reviewer, inspected the entire
task fixture and the merged transaction/service owners, and exclusively held
`test_only_demo_suite` for the database rerun. No foreign/default DB fixture or
direct lifecycle was invoked; HEAD stayed unchanged through cleanup.

The namespace PU ran first: 1 PASS. The exact selector
`tests/db/test_test_only_demo.py::test_trusted_post_lock_expiry` then ran all four
T6/START/CONTINUE/RESUME cases: 4 PASS, zero errors/failures/skips. Execution used
`uv run --offline pytest -q -s` with explicit JUnit output and a writable temporary
UV_CACHE_DIR. Initial attempts are honestly retained: uv default cache was denied
before collection; the sandboxed four-case run had four setup errors due to Docker
socket denial. The authorized escalated rerun is the fresh PASS basis.

The own fixture validated exact SHA/root namespace
`kineticloop-kl027-demo-ff93c08-02d718cec5f6` and database
`kineticloop_kl027_demo_ff93c08_02d718cec5f6`, with migration `e8c2f1a6b904`.
Nested bootstrap receives the already selected owned lifecycle. Connections verify
current_database. Each finally cleanup has bootstrap/reset/start/destroy inventory
and empty container/volume/network remnants. All four are present in audit.json.

For each operation, the real owner-produced source and forward workflow were used.
T6 waits on S29, absent new START on S38 before first-use creation, and CONTINUE/
RESUME on S44. RESUME's PAUSED lifecycle comes from the authenticated ordinary
pause owner, not a raw lifecycle update. Each pg_stat_activity witness includes
actual pg_blocking_pids, blocked query and the same query's clock_timestamp.
The independent timestamp assertions verify
before_wait <= blocked_at < immutable admission expiry < after time.
The reader crosses expiry while the owned blocker remains held, then finally
rollback releases it. The merged owner timeout remains unchanged. T6 rejects the
expired resolution; all T7 operations reject TIME_INELIGIBLE. Exhaustive snapshots
match before/after, including source/history/bookkeeping and first-use placeholders.

The source owner ordering remains S51 shared gate -> S01 -> intent -> daily head
-> execution -> receipt/remaining aggregate as applicable. User STOP/input invalidation
begin at S01 with no reverse registry acquisition. Strict SafetyRegistry revocation
uses exclusive management coordination without user fanout. Fresh post-lock DB
time controls all permits; old prelock fence proof is rechecked. Idempotent replay
is historical and non-executable. Receipt/event/outbox and mutations finish in
the same transaction; failed guards roll back early head/session placeholders.
No model/network wait or full external history computation is added inside locks.

Final task evidence is separately audited: all twelve commands/log hashes/JUnit
counts match PASS at tested72a9a5f, with 61 suite executions, four timing witnesses
and 61 empty cleanup witnesses. This reviewer reran four critical cases, not the
whole 61-case suite. Full legacy DB regressions remain final hosted CI conditions.
No DB BLOCKER is found. Resource was released after four empty cleanup witnesses.
