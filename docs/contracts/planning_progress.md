# Internal planning progress

`ContextService.RecordSnapshot` and `PlanningWorkflowService.AdvanceAttempt` are
separately authenticated typed internal preparation operations. They do not extend
the public 39-command wire registry or T1–T8 boundaries. The current adapter accepts
registered isolated TEST subject/policy/environment/principal identities only.
Workers supply identities and expectations, never a callback, SQL, lease expiry,
trusted time, new fence, root budget or success authority.

Context capture reads immutable published manifest/request/program/policy inputs
outside coordination. The explicit TEST policy context summaries supply every
mandatory block. Missing blocks, a mismatched basis, truncation or an insufficient
byte budget deny. Accounting uses the versioned UTF-8 byte upper bound; it makes
no model tokenizer or clinical completeness claim. The exact registered bounded
RUNTIME artifact identity/hash/version with the CONTEXT_BUILDER operation label and source cutoff accompany the immutable
S26 record. A rebuild appends another sequence rather than altering history.

Persistence orders S01 → S27 → S02 → S29 and checks current authenticated TEST
registration, active policy/program, request ID/revision, attempt, owner/fence,
lease, deadline, current manifest/epoch, protective controls, manifest and builder
validity. Trusted `clock_timestamp()` is read again after the aggregate row lock,
and its exact acceptance time is committed in the same S03 event payload,
and the exact acceptance time is committed in the same S03 event payload, so queue
time cannot preserve expired work authority. Registry locks remain confined
to their frozen T3/T6/T7 owners. Context preparation is not authorization issuance.

AcquireLease leaves S29 CREATED. AdvanceAttempt verifies that actual lease before
CREATED → LEASED, records its fence and server start time, then permits only the
frozen forward chain through BUILDING_CONTEXT, FITNESS, DEMAND_FEATURES, NUTRITION,
VALIDATING and COMMIT_READY. COMMITTED and intent success remain exclusively T6.
FITNESS binds an owner-produced S26. Subsequent stages bind immutable S34 FITNESS,
S35(F), S34 N(F,D,manifest,policy), and coherent unexpired S36/S37. Each later
operation preserves earlier source identities/hashes. Placeholder immutable later
inputs in these tests instrument guards; KL076 remains responsible for composed
F/D/N preparation and completeness. No product, WF or release PASS is inferred.

The internal entrypoint derives an exact write capability from the current guarded
basis. RecordSnapshot may insert one S26 only; AdvanceAttempt may update one exact
S29 only. Attempt metadata and the receipt/event/outbox commit or roll back together.
Replay is authenticated under S01 before current work guards. Historical replay returns immutable IDs with executable=false and grants no current
work authority. Same operation keys with changed payloads conflict. Generic public
command and unguarded preparation entrypoints reject these internal owners.

Validation additionally binds the current execution-basis event, semantic and envelope PASS, and the resolution query basis including its exact action type. The action type is the locked root purpose and must map to TEST_ONLY in the active policy; a different resolution action denies even with self-consistent hashes. These are progression prerequisites, never bearer authorization. Terminal exits retain prior immutable source pointers and do not terminate or reset the root.

The test-only lifecycle validates `kineticloop-kl075-progress-<HEAD first7>-<root
SHA256 first12>` and the corresponding underscored database before construction,
bootstrap, every nested lifecycle command, reset, seed reset and finally cleanup.
It never invokes another task's fixtures, reset or cleanup. Broader legacy DB
regressions execute only in the unchanged hosted CI lifecycle.
