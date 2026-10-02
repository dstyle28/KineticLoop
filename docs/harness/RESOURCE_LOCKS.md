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
- `schema_topology`
- `canonical_fact_schema`
- `persistence_permissions`
- `persistence_schema`
- `python_dependency_lock`
- `transaction_interfaces`
- `fitness_eval_contract`

Every database-writing worktree uses a unique namespace, e.g. database `kineticloop_<task>_<shortsha>` and Compose project `kineticloop-<task>-<shortsha>`, unless the task explicitly declares a shared serialized environment.

`python_dependency_lock` serializes `pyproject.toml`/`uv.lock` writers.
`migration_chain` serializes Alembic-chain writers. A concrete path overlap is
allowed only when every overlapping task declares a shared exclusive resource key;
otherwise the Harness definition is invalid rather than merely unschedulable.

- `postgres_lifecycle`

`postgres_lifecycle` serializes the concrete lifecycle/Compose readiness writers; it does not grant transaction, migration or shared-database authority. KL074 must use task-owned coldstart namespaces and dedicated hosted VM regression Docker.

- `protocol_interleaving_suite`
- `test_only_demo_suite`

HG038 gives KL026 and KL027 tests-only suites independent task-owned databases. These resources grant no production owner writes. KL075/076/077 serialize transaction_interfaces and user_coordination; merged dependencies and exact write paths remain mandatory.

- `boundary_acceptance_suite`
- `shadow_isolation_suite`

HG042 grants only disjoint tests-only suites using separate task/SHA7/resolved-root SHA12 databases and Compose namespaces. Shared owners are read-only; no source, grant, migration, helper, lifecycle or CI writes.
