# Full TEST action preparation

`kl079-full-actions-v1` is an isolated TEST policy profile. Its persisted
`deterministic_fixture.contract`, ordered `required_actions=[TRAINING,NUTRITION]`,
exact mechanical KL076 rules and both TEST_ONLY action scopes select the profile.
A caller cannot select legacy completeness. Existing FITNESS, Demand and Nutrition
owners and their mechanical payloads retain KL076's version and identity algorithm;
legacy resolution/validation requests retain their original domain and bytes.

`FullPreparationRequest` is a separate internal, closed, ProgressIdentity-bound
request, accepted only by EvidenceResolver and ValidationService. Resolution binds
one exact action, proposal ID/hash and parameters hash. TRAINING parameters are
F.action. NUTRITION parameters are precisely `{fuel_units:N.fuel_units,
semantic_class:TARGET,units:fixture_units}`. N is recomputed from exact D and F;
`N.fuel_units=F.action.minutes*3` is a fixture target, never nutrition intake, actual
fuel execution, or clinical coverage. Both actions use the actual admitted
WORKOUT_ACTUAL facts, associations and admissions in the sealed canonical source.
The shared mechanical source predicates remain complete; required policy members
cannot supply missing actual membership. Contradictory, retracted, unknown, future,
partial, truncated, mixed and expired evidence cannot yield full validation.

Each FullResolution has its own immutable UUID and content hash, action-specific
proposal and parameters, full F/D/N IDs/hashes, context/request/attempt/epoch,
manifest/policy/source IDs and hashes, exact source ranges/members/provenance and
runtime version. Its query_basis_hash covers this precise per-action basis. The
full discriminator and action participate in identity generation; TRAINING history
is never relabeled as NUTRITION. The full runtime is registered through the existing
SafetyRegistry RegisterArtifact owner with bounded validity and immutable
pre-registered dependencies. The profile consumes the owner's registration payload;
it does not require a custom runtime payload outside that owner contract.

Full validation accepts exactly ordered TRAINING and NUTRITION bindings. It loads
both S36 rows by exact same-subject ID/hash and reconstructs their physical columns
and payloads against actual immutable F/D/N and captured canonical inputs. Each
binding includes action_type, proposal_id/hash, action_parameters_hash,
resolution_id/hash and query_basis_hash. One S37 retains ref_s36_id=TRAINING,
ref_s34_id=N, ref_s35_id=D and ref_s03_id=current execution basis, alongside the
existing request/attempt/manifest/policy FKs. Its resolution_hash is the TRAINING
anchor. The additional NUTRITION resolution reference is owner-verified JSON, not
a new database FK. The finite expiry is the minimum of both exact resolutions,
manifest, registered runtime, policy and admitted-source deadlines.

Computation and canonical reconstruction happen before coordination. The existing
S01→S27→S02→S29 locks, current-chain/fence/lease/deadline/control/manifest/epoch
guards and fresh post-lock database time apply to append-only outputs and atomic
receipt/event/outbox. The full closure is rechecked after locks. ACK-loss replay
returns immutable historical identities with executable=false; changed same-key
payloads conflict and fresh operations still require current authority.

AdvanceAttempt retains its six-source map and TRAINING resolution anchor. Only the
full-profile COMMIT_READY branch in transactions._progress_sources loads and
reconstructs the second S36 and full S37, including current execution basis,
revocation and expiry. Planning progress modules and public wires are unchanged.
Same-root F2 uses actual KL024 revision/new attempt and forward snapshot/stages;
D2/N2 and both action resolutions are recomputed, old history stays immutable, and
root budgets/deadline are preserved. This profile stops at COMMIT_READY. KL077 owns
later T6/T7 consumption and per-member issuance. No production or shadow activation,
head, prescription, authorization, session, binding or root success is created.

Own fixtures register isolated subject/program/policy and immutable admitted
sources and the existing supporting context-builder/catalog artifacts. They never
seed S15/S16, S21–S26, stages, S34–S37 or downstream outputs. Source fact creation,
canonical seal, projection/build, publication, admission/acquire, snapshot/stages,
F/D/N, both resolutions and validation use actual owners. Supporting historical
context-builder seed shape remains necessary for the unchanged KL075 reader;
the new full runtime is registered using the actual trusted registry API.

All local lifecycle entrypoints derive
`kineticloop-kl079-full-<HEAD7>-<SHA256(resolved-root)12>` and the corresponding
underscore database name. Pure fail-closed preflight precedes bootstrap, reset and
cleanup. Nested bootstrap receives that selected lifecycle. Connections assert
current_database; logs record migration, namespace, persisted identities, observed
blockers, finite deadlines and cleanup inventories. No imported foreign pytest
fixture executes. Unchanged legacy DB regression coverage runs on hosted CI.
Expiry controls use distinct source-admission and registered planning-runtime
deadlines while the projection engine, manifest, policy, lease and root remain
valid. Both full validation and COMMIT_READY run before and after each earlier
bound through an observed S29 blocker; the logs identify the live current guard
and full consumer reached. Separate consumer controls cover current-manifest
replacement, attempt loss, stale fencing, actual takeover and post-lock lease
expiry, with complete persisted zero-effect comparisons.
Task checks, independent reviews, merge and product/release obligations remain
separate facts.
