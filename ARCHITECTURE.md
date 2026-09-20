# ARCHITECTURE.md — Agent Map

This file is a navigation map, not a replacement for frozen specifications.

## Domains
- Evidence/admission/canonical facts: Protocol §3, DB S09–S22.
- Decision publication/context: Protocol §4, DB S21–S26.
- Planning workflow/call ledger: Protocol §6, DB S27–S37.
- Prescription/authorization/execution: Protocol §5, DB S38–S45.
- Replay/release evidence: Protocol §7, DB S46–S48.
- Global SafetyRegistry: frozen DB S49–S51 / frozen protocol registry coordination.
- Provider integrations: `12_KineticLoop_Integration_Spec_v0.1.md`.

## Runtime direction
External providers/user input → Evidence → Admission/association → Canonical facts → Factset/projections → DecisionManifest → bounded AI proposals → Validation/Authorization → Execution.

No reverse edge may create facts or authority from a proposal.

## Development topology
`docs/exec-plans/active` contains task packets. Tasks are implemented independently in worktrees and merged through the harness merge gate. `docs/exec-plans/completed` is durable task memory.
