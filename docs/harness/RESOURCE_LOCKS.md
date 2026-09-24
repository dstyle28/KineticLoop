# Harness Resource Locks and Environment Isolation

Worktrees isolate files, not external resources. The orchestrator must serialize tasks whose `resource_keys` overlap in exclusive mode.

Initial resource keys:

- `harness_core`
- `migration_chain`
- `command_contracts`
- `registry_coordination`
- `user_coordination`
- `authorization_core`
- `planning_ledger`
- `provider_contracts`
- `release_evidence`
- `requirement_registry`
- `security_data_boundary`

Every database-writing worktree uses a unique namespace, e.g. database `kineticloop_<task>_<shortsha>` and Compose project `kineticloop-<task>-<shortsha>`, unless the task explicitly declares a shared serialized environment.
