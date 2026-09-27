# Provider evidence boundary

## Scope and authority

`kineticloop.integrations.provider` defines the common provider identity,
transport-status, observation, and `EvidenceEnvelope` contracts. It ends at the
input to `EvidenceService.ReceiveEvidence`; an adapter has no canonical-fact,
admission, approval, progression, readiness, prescription, capability, or command
authority. `command_authority` is the fixed literal `NONE`.

The boundary preserves INV-01, INV-02, INV-15, and INV-16. Planned values never
fill missing actual execution, provider or model text never creates authority,
summarization cannot increase trust, and `known_at` is supplied by the receiving
server rather than copied from a provider timestamp. Admission, association,
correction, and replay remain downstream protocol operations.

## Canonical identity and subject binding

`ProviderId` and `StreamId` are bounded upper-case tokens with underscore-separated
segments. Examples are `HEVY` and `HEVY_STRENGTH`. A server-side
`TrustedProviderBinding` binds the authenticated subject, provider, stream,
source connection, source/trust classes, and adapter version. Provider payloads
contain none of those binding fields. `build_evidence_envelope` always copies them
from the trusted binding.

Before the T1 owner writes S09, `validate_receive_evidence_binding` compares the
envelope, registry binding, command subject, and command source connection. Every
mismatch produces only `SUBJECT_MISMATCH`; it does not identify whether another
subject or connection exists.

## Closed S09 envelope

The immutable envelope includes exactly:

- schema version, canonical subject/provider/stream/source-connection identities;
- source object type and identity;
- exactly one reliable provider revision or stable observation key;
- canonical `observed_at`, `effective_at`, and server-assigned `known_at` instants;
- exactly one canonical payload hash or controlled `blob://` reference;
- the fixed canonical hash scheme, source class, trust class, closed lineage,
  content schema version, and adapter version;
- `command_authority=NONE`.

Models are frozen, strict, and reject extra fields. Raw payload content is not
serialized in an `EvidenceEnvelope`; only its canonical hash or a controlled blob
reference crosses the boundary. Corrections create new provider revisions or stable
observations and never overwrite an older envelope.

## Credential and diagnostic boundary

Provider credentials come only from an explicit `ProviderSecrets` value. No
integration contract reads environment variables or opens a network connection.
`CredentialGuard` rejects registered raw credentials, bounded percent-encoded
forms, credential-shaped keys and assignments, Authorization material, and URL
userinfo before an observation is hashed or an envelope is created. The guard and
execution context have redacted representations. Adapter failures expose only a
provider identity, fixed failure code, and safe failure-class context; diagnostic
presentation uses the merged recursive redactor.

Committed provider fixtures are synthetic, explicitly non-production, and use only
the documented KL-009 credential and health sentinels. Every fixture under
`tests/fixtures/synthetic/providers/` is loaded through the hardened KL-009 fixture
validator before it can be used by an adapter contract test.

## Transport health and coverage

`ProviderSourceStatus.connection_status` follows the Integration Spec lifecycle:
`UNCONFIGURED`, `AUTH_REQUIRED`, `CONNECTED`, `DEGRADED`, `REAUTH_REQUIRED`, and
`DISABLED`. `coverage` is an independent field. A connected source can therefore be
partial or unknown, and a transport outage does not turn missing evidence into zero.
Watermarks are provider-specific identities rather than universal time.
The diagnostic status factory runs raw cursor/error inputs through the context's
credential guard, stores only a one-way SHA-256 watermark token and a bounded
canonical error code, and redacts these fields from the default representation.
Serialized valid status values therefore contain no raw provider cursor or error
message. Runtime status validation rechecks the closed model, provider/stream
binding, and credential boundary before exposure.

## Adapter interface

`ProviderAdapter` exposes only connection status, initial backfill, incremental
fetch, bounded reconciliation, and normalization to `EvidenceEnvelope` values.
The runtime `validate_adapter_output` boundary reserializes and strictly revalidates
each returned model, rejects unvalidated Pydantic construction or mutation, rechecks
the trusted subject/source binding and lineage root, rescans every serialized field
with the context's credential guard, and replaces any adapter-supplied `known_at`
with the server clock sealed into that trusted context at the receive boundary.
`ProviderBatch`, `BackfillResult`, and `ReconciliationResult` are also strict,
immutable contracts. Implementations receive their explicit execution context from
the caller; network clients and credential stores are outside this module and must
be injected by later provider-specific tasks.
