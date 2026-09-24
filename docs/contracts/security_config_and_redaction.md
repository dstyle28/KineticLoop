# Security configuration and diagnostic redaction contract

## Scope

This contract supplies a reusable configuration/diagnostic boundary. It does not
implement a provider adapter, credential vendor, Evidence Admission, command surface,
role binding, approval, or authorization policy.

## Secret/config separation

`PublicProviderConfig` contains only provider metadata and the names of required
credentials. A caller must select and pass an explicit `SecretSource`; the loader never
reads ambient environment variables. Missing and blank required values fail closed.
Loaded values are held as `SecretValue`, whose default string/repr is redacted and
which has no generic JSON or mapping serialization interface. The deliberate
`reveal()` call is restricted to the in-process consumer that needs the credential.

The committed Hevy and HealthKit bridge values are synthetic sentinels, not working
credentials. No real provider secret or health/training record belongs in source,
fixtures, test input, evidence logs, or default diagnostics.

## Default-deny diagnostics

`Redactor` recursively creates a diagnostic copy of mappings, structured-log argument
sequences, URLs, exceptions, and subprocess failures. It removes registered raw and
percent-encoded values, URL userinfo, recursively nested URL/query credentials,
sensitive query values, and values below sensitive keys while preserving safe context
such as provider/host, retry count, and failure class. It never mutates the input.

`DatabaseConnection.url` is an explicit in-process connection surface. Default
string/repr/JSON and `kl db-reset` plain/JSON output use a redacted diagnostic mapping;
they keep project, database, host, and port useful without emitting usernames,
passwords, URL userinfo, or sensitive query values. Lifecycle subprocess failures are
redacted before they cross the CLI error boundary. Database reset operations,
worktree/Compose namespace derivation, and verifier behavior are unchanged.
Argument parsing always operates on the original input; redaction applies only to
parser error presentation and cannot turn encoded text into an executable option or
value.

## Canonical evidence and authority

Redaction is presentation-only. It does not rewrite canonical Evidence or
EvidenceRevision payloads, recompute their bytes or hashes, admit evidence, transform
provider transport into canonical truth, or classify a redacted value as evidence.
`RedactedDiagnostic` contains only display text and has no command, role, capability,
approval, Evidence Admission, or authorization field or effect. Summarizing or
redacting provider text cannot elevate its trust or authority (INV-15), and this
boundary neither reads nor changes replay-visible evidence (INV-16).

## Synthetic fixture provenance

Every file under `tests/fixtures/synthetic/security/` must carry stable `fixture_id`
and `provenance_id` values, `synthetic: true`, the fixed
`NON_PRODUCTION_TEST_SUBJECT` marker, and a provider environment of `SYNTHETIC_TEST`.
Only the documented sentinel credential and health-field names/values in
`kineticloop.security.synthetic` are accepted. Missing provenance, production
identities/environments, unknown fields, and non-sentinel values fail closed.
