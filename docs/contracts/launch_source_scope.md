# Launch source scope v1.0.0

`kineticloop.integrations.launch_registry.LAUNCH_SOURCE_SCOPE` publishes the
immutable trusted launch policy for `harness-backlog-v0.2/KL-050`. It reuses KL-055
`ProviderId` and `StreamId` directly. This registry is distinct from frozen
SafetyRegistry S49–S51. It has no database, network, credentials, environment
lookup, runtime connection state, or registration endpoint for provider payloads.

| Provider | Stream | Launch role |
| --- | --- | --- |
| MANUAL_CHAT | MANUAL_CHAT_REPORT | Required authenticated fallback |
| HEVY | HEVY_STRENGTH | Required integration |
| APPLE_HEALTHKIT | HEALTHKIT_HEALTH_ACTIVITY | Required integration |
| APPLE_HEALTHKIT | HEALTHKIT_NUTRITION | Optional, nonblocking |
| OURA | OURA_DAILY | Optional, nonblocking |
| MACROFACTOR_EXPORT | MACROFACTOR_EXPORT_IMPORT | Optional, nonblocking |
| DEXA_FILE | DEXA_FILE_IMPORT | Optional, nonblocking |

Both Hevy and Apple HealthKit are mandatory launch integrations under the current
Project Plan and KL-050 packet, refining the Integration Matrix's descriptive
`target` terminology into an explicit launch policy. HealthKit nutrition is a
separate optional stream of APPLE_HEALTHKIT, not a second provider. Spreadsheet
migration is retired and absent. Inclusion never enables a source or makes an
adapter LAUNCH_READY. Optional promotion needs approved versioned policy/ADR and
an explicit catalog/code change; a caller-selected version alone cannot promote it.

The exact closed catalog is published as frozen dataclasses with immutable nested
tuples and strict canonical types/enums. Unknown identities, duplicates, changed
launch roles, mutable metadata and unknown fields reject. Serialization orders
entries by provider/stream, sorts set-like metadata, and uses compact sorted-key
UTF-8 JSON. `digest` is `sha256:` plus SHA-256 of that serialization, including
schema and policy versions. Any semantic content or version change changes the
digest; input order does not. The digest identifies policy, not approval. Trusted
code may construct a separate validated policy value; it cannot mutate the
published value. There is no provider observation or runtime status input.

The evidence descriptions preserve these provider distinctions:

- Manual/chat retains authenticated report identity and user-reported provenance;
  corrections are revisions. Other evidence may remain usable but ambiguity stays
  unresolved. Authenticated content still requires the protocol command flow.
- Hevy describes structured strength actuals, exercise identity, cardio and
  optional weight evidence. Incremental update/delete polling uses provider event
  cursors, retaining workout/template identity, revision and mapping version.
  Absence degrades to manual actuals; wearable labels never fill sets/reps/load.
  Hevy Pro/API instability and actual adapter implementation remain downstream.
- HealthKit describes sleep, HR/HRV/RHR, activity/cardio and weight evidence.
  Observers signal changes; anchored queries retrieve additions/deletions using
  anchors per sample type/query scope. UUID, sourceRevision, device when available,
  bridge upload and deletion provenance distinguish upstream sources. No visible
  samples means unknown cause, never zero, full coverage or certain read denial.
  Exact iOS sample types remain a downstream contract decision. Absence requires
  history/subjective inputs and a planning policy that permits partial data.
- Oura uses per-stream date/cursor polling and reconciliation, retaining Oura
  lineage and provider-derived summary semantics. Missing Oura lowers recovery
  completeness; stale values cannot become current and baselines remain same-source.
- HealthKit nutrition does not imply complete daily intake or upstream app data.
  MacroFactor is immutable file import, with expenditure/weight trend retained as
  provider-derived estimates rather than a presumed live REST feed. DEXA keeps
  report hash and extraction page/span provenance; without it no body-composition
  conclusion is supplied. Import identities/hashes are not universal time clocks.

All sources describe missingness and degradation, not automatic planning decisions.
`CONNECTED` is transport/auth health; KL-055 `ProviderSourceStatus.coverage` remains
independent and can be PARTIAL/UNKNOWN. Registry membership grants neither complete
coverage nor adapter readiness. Missing evidence is never synthetic zero; yesterday's
observations never masquerade as current. Actual cross-source association, correction,
admission and deduplication remain downstream and preserve source lineage.

AI exposure is a separate permission from ingestion. Non-Oura entries describe only
admitted facts through consent and context field policy, not an exposure approval.
Raw metadata/free text is controlled and has no command authority. Oura raw **and
derived** data remain DENIED_PENDING_INT_06. Membership, connected status,
availability, a derived-only claim or a caller flag cannot enable exposure.
INT-06 must separately document the approved integration lane, consent scopes,
retention/deletion, third-party AI terms review and exact model field allowlist.
This publication supplies no compliance approval and no field allowlist.

Every entry has `command_authority=NONE`. It grants no canonical fact, admission,
readiness verdict, approval, authorization, execution, production activation or
command capability. Provider observations continue through KL-055's trusted
binding and EvidenceEnvelope into the T1 owner, then frozen Evidence Admission.

This gate-builder task does not require M9A completion. It does not implement
adapters, satisfy KL-051/KL-052 dependencies, prove INT-A obligations or E2E provider
loss behavior, pass release gates, or enable production auto-activation. Adapter
LAUNCH_READY remains subject to Integration §14's identity, correction, lateness,
permission, outage, provenance, deduplication, exposure, control-path and absence
gates. Product requirement statuses remain unchanged.
