# Independent DB_CONCURRENCY assessment

Reviewed `harness-backlog-v0.2/KL-029` at implementation/result SHA
`eed165afbd56d3ae551c46166aaec776cf79e625`, protected base
`9268fc8dd8c071c02dc5c698274dbf6fcd112776` and tested implementation
`b9fbf9b475e07765db62e67f0104a800036dda4d`.

No blocker or required follow-up found. The change contains the two task test
modules, task contract, result and new task evidence. Production owners,
transactions, migrations, grants, lifecycle, shared fixtures and CI remain
unchanged. The one linear tested-to-reviewed commit only adds the result and new
evidence files. Twelve author check records were independently checked against
their actual log hashes and JUnit counts; all reported executed checks have
nonzero collection and zero errors, failures and skips.

The DB and independent review skills were applied against Protocol §§0.3a,
2.1a, 4.1a, 5.3–5.6 and 7.4, DB S15/S16/S38/S42/S45/S46/S47/S49–S51,
§§4.1/4.3/5 and R04, and current acceptance §§2–3. Prerequisite KL008,
KL017 and KL027 normal two-parent merges and exact reviewed-sha PASS records
are present at the protected base; M2 closure is PASS.

The independent current-head rerun executed exactly the two KL029 test modules:
6 passed in 42.51 seconds, zero skips or xfails. `suite-escalated.log` and XML
are fresh review evidence, not replacement task-check evidence. The initial
sandbox attempt is retained as `suite.log`/XML: both PU selectors passed and
four DB setups failed at Docker API permission before their case bodies.
The ordinary escalation was approved and the exact same suite then passed.
No denial was evaded or foreign fixture run.

The namespace is exactly `kineticloop-kl029-shadow-eed165a-01c8899b2807`,
database `kineticloop_kl029_shadow_eed165a_01c8899b2807`. The namespace code
checks full runtime HEAD, resolved-root bytes/digest, fixed shadow label,
selected lifecycle target and ambient overrides before construction and each
runner/reset/start/bootstrap/connect/destroy. Bootstrap explicitly receives
that lifecycle, including nested cleanup. The demo module is loaded read-only
for recipes with only its connection adapter replaced; no demo fixture executes.
Python bootstrap connections check the selected database and bounded connection,
statement, lock and idle-in-transaction deadlines. Owner connections additionally
verify the migration head; initial bootstrap is the explicit baseline-to-head
phase. All four final inventories show no owned containers, volumes or networks.

Four independent TEST trajectories use the actual source fact owner, canonical
Begin/Write/Complete/Seal, preparation/publication, admission/acquisition,
snapshot/forward stages, F/D/N, both resolutions, shared validation and T6.
The positive controls persist two ordered action prescriptions/issuances, exact
resolution and shared-validation references, certificate/closure digests and
server dependency-minimum expiries. Real START/CONTINUE/PAUSE/RESUME generate
the exact session/binding history and receipt/event/outbox joins. Twelve
unmodified actual T7 eligibility decisions are executable. The original START
binding survives RESUME; CONTINUE does not add a binding.

Fresh keys exclude historical replay masking. The raw evidence independently
contains 26 exact before/after full-history equalities: 3 authenticated
registration mismatches, 5 separately authenticated wire/hash mismatches,
1 valid TEST-B current-bundle membership denial, 10 strict owner ingress
denials and 7 database namespace-storage denials. Guards match actual source
entry ordering. TEST-B fails before T7 and is labeled accordingly; strict
ingress/registration/scope/ACL denials never claim downstream T6/T7 reach.
Fifteen live-table privilege denials use actual owner-produced S38/S42/S45
objects, explicitly declared evaluation identity and SQLSTATE 42501, with
full-history equality checked after each rollback.

Trusted-admin registrations and successful own-principal lookups establish
actual authenticated storage boundaries. The 27 scope denials return SQL NULL
and identical non-enumerating application payloads for missing/foreign objects.
Declared BOUNDED_SCOPE_LOOKUP metadata makes no measured constant-time claim.
Only external historical evaluation S46/S47 and their declared same-subject
archive/FK closure are raw fixtures; their IDs, source refs, row hashes,
recorded-output mode, cutoff and enabled triggers are logged. No live target
seed, session_replication_role bypass or global revision reset appears. Registry
revision and TEST history remain unchanged apart from explicitly inventoried
archive additions. These inputs do not claim ReplayService writer or shadow
workflow provenance.

No registry race is added by this packet: its conditional race oracle is not
applicable. Existing actual T6/T7 owners continue frozen S51→S01 ordering;
this tests-only suite neither replaces the transaction capability nor grants
new write authority. No external/model/network wait is introduced inside a
coordination transaction. Atomic bookkeeping and denied-operation rollback
are validated using real PostgreSQL rows rather than mocks or SQL-text claims.

Task-local mechanical evidence satisfies the named oracles. Product requirements
are not marked PASS. Real shadow store/API, R04@E2E, G-SHADOW usability, M3 and
release closure remain NOT_RUN, and production auto-activation stays disabled.
