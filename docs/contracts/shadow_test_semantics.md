# Shadow/test semantic contract v1

KL-008 defines two deliberately separate, immutable wire contracts. It does not
implement storage, migrations, T6/T7 command owners, transaction logic, or live
authorization.

## Real-data shadow evaluation artifact

`ShadowEvaluationArtifact` is always `SHADOW_ONLY / NOT_EXECUTABLE`. Its only
persistence boundary is an isolated evaluation artifact. The contract carries
explicit null targets for the live S38 daily-plan head, S42 production issuance,
S45 execution binding, and live PlanningIntent-success transition. Construction
and deserialization fail closed if any such target is supplied, if the mode or
persistence boundary changes, or if a schema field is missing, duplicated, or
added.

The isolated boundary is the later evaluation-artifact storage path described by
the frozen S46/S47 model. This contract grants no ability to write that storage;
it only prevents a shadow artifact from being represented as a live-state target.

## TEST_ONLY authorization scope

`TestOnlyAuthorizationScope` accepts exactly a KL-007 `ActorRole.TEST` identity,
whose immutable role matrix supplies `RUN_TEST_SIMULATION`. It binds canonical
identifiers for an explicitly isolated, non-production subject, policy, and
environment. SUBJECT, ADMIN, and EVALUATION actors and any production or
evaluation resource boundary are rejected.

The scope records that direct writes are forbidden and that both the T6 and T7
command-owner guards remain required. It is therefore only guarded input to the
future real command entrypoints. It is not an authorization, command permission,
receipt, storage API, or bypass around normal authentication, current-state,
registry, epoch, dependency-validity, idempotency, and transaction guards.

## Validation and compatibility

Both contracts use closed v1 schema identifiers, exact field sets, exact enum and
boolean values, canonical UUID identifiers, deterministic canonical JSON, and
strict duplicate-key rejection. Unknown schema versions and unknown values are
rejected rather than upgraded or interpreted. Any future schema needs a new
version and explicit compatibility decision; it must not weaken the separation
required by INV-09, INV-10, T6, and T7.
