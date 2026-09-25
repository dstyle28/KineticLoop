# T1–T8 command and result contracts

`kineticloop.contracts.commands` is the public, strict Pydantic v1 wire surface
for the frozen transaction owners. Models are immutable, reject unknown fields,
and serialize an explicit boundary. A boundary is not inferred from a service
name and cannot be changed by a caller.

| Boundary | Public commands |
|---|---|
| T1 | `ReceiveEvidence` |
| T1-PREPARATION | `RecordCandidate` |
| T2-IN | `DecideAssociation`, `DecideAdmission`, `AcceptFactRevision`, `ApplyControl`, `ClearControl`, `ApproveChange`, `ActivateApprovedProgram`, `RecordActualExecution`, `CompleteReportedWorkout` |
| BUILD-PREPARATION | `BeginBuild`, `WriteCandidate`, `CompleteFactset` |
| T2-SEAL | `SealFactset` |
| REGISTRY-MANAGEMENT | `RegisterArtifact` |
| T2-GLOBAL | `RevokeArtifact` |
| T3-PREPARATION | `RecordProjection`, `BuildManifest` |
| T3 | `PublishManifest` |
| T4 | `AdmitOrReviseIntent`, `CancelIntent` |
| T5 | `AcquireLease`, `RenewLease`, `ReserveCall`, `PermitDispatch` |
| T5-PREPARATION | `RecordToolResult`, `RecordProposal`, `RecordDemandFeatures` |
| T6-PREPARATION | `ResolveEvidence`, `RecordValidation` |
| T6 | `CommitBundle`, `Reauthorize` |
| T7 | `StartSession`, `ResumeSession`, `ContinueSession` |
| T8 | `SettleCall`, `MarkUnknown`, `ReapIntent`; `CancelIntent` may also execute at T8 |

Every subject command carries exactly one canonical `subject_id`, no explicit
global scope, the merged three-field role-identity wire value, a client
idempotency key, a request hash, and command-specific immutable basis fields.
Capabilities and trust assertions are never accepted on the command wire; the
coarse capability is derived from the service-bound role. Registry commands
carry no fabricated subject: their scope is exactly
`global:safety-registry`, and their actor must derive the admin capability.

T2 input decisions, factset build/seal, and T3 publication bind the input
frontier as an explicit `*_input_frontier_hash` SHA-256 value. The frontier is
the digest of the immutable input revision set; it is not a protocol counter.

Preparation commands are independent short transactions. In particular,
factset build preparation never acquires S01, registry registration is outside
T2-GLOBAL, and projection/tool/evidence preparation cannot be serialized as the
corresponding atomic T transaction. `IssueAuthorization`,
`InvalidateAuthorization`, `RecordSnapshot`, `AdvanceAttempt`, and
`CancelUndispatched` remain internal owner operations and have no public model.

Worker-produced T5/T6 preparation writes bind intent, attempt, current request
revision, lease owner, fence, lease expiry, and expected RUNNING status. Their
domain payloads also carry the immutable S33–S37 result identities and hashes:
tool scope/coverage, typed proposal dependencies, Fitness-to-Demand basis,
resolver coverage/consistency, and the validation certificate's proposal,
demand, resolver, policy, epoch, and execution-head bindings. Owners still read
authoritative lease time and state under the frozen locks; these fields do not
replace those guards.

Production subject commands require the production subject scope and actor.
`TEST_ONLY` is accepted only by the real T6 and T7 command models, requires a
TEST actor, binds isolated non-production subject/policy/environment identities,
forbids direct writes, and explicitly preserves the command-owner guard. Shadow
evaluation artifacts remain governed by `shadow_test_semantics.md` and cannot be
used as command scope.

For T6, the isolated policy in `TestOnlyScope` must equal the policy bound by
the command itself. This prevents an isolated test scope from authorizing a
commit or reauthorization evaluated under a different policy.

`kineticloop.contracts.results` defines a distinct typed success result for each
public command plus `CommandRejected`. Historical T6/T7 success includes a
separate current-eligibility value; it is not a new authorization. A replayed
`PermitDispatchSuccess` can never grant another provider send. T1 receipt
success explicitly does not claim that a protective T2 action was applied.
Lease acquisition and renewal results return the authoritative owner, newly
committed fence token, and bounded lease expiry required by subsequent writes.
