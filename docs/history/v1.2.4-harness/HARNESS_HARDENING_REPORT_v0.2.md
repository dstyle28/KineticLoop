# KineticLoop Harness Contract Hardening v0.2 — Change Report

## Scope
This update incorporates the latest Harness audit after repository bootstrap. Frozen Protocol and DB semantics were not reopened.

## Closed / fixed
- C1 Git/bootstrap: treated as externally resolved by the user; this package no longer blocks on bootstrap but does not independently verify the user's local Git state.
- C2 canonical identity: added current document/requirement indexes, restored missing machine artifacts, namespaced task identities, and explicit historical KL-062–066 reuse mapping.
- C3 result/merge ambiguity: task result must be committed in PR; added tested/reviewed/merge revision semantics and SHA-bound review contract.
- C4 task-vs-requirement PASS ambiguity: backlog/packets now separate `requirements_covered` from `checks_required_for_this_task`.
- I1 gate self-dependency: shadow/remote-AI/source-scope builder tasks are not blocked by the gate they create; optional providers are conditional dependencies.
- I2 M3 implementation gap: added KL-019 minimal PublishManifest/CommitBundle/StartSession real-DB slice; KL-026 now depends on it.
- I3 resource isolation: added resource keys, write paths, and unique DB/Compose requirement for concurrent DB tasks.
- I4 review validity: added GENERAL review for all tasks plus specialist triggers; review PASS is head-SHA-bound and stales on changes.
- I5 placeholder DoD: tasks with placeholder completion are marked `MUST_REFINE_BEFORE_READY`; KL-052/KL-049/KL-070 explicitly blocked pending refinement.
- I6 traceability: added current composite requirement set and task→requirement/check/resource/review traceability file.
- I7 frozen protection: added protected `FROZEN_BASELINE.json` independent of mutable package manifests; KL-001 owns validator integration.

## Resulting task inventory
- total task records: 68
- active tasks: 66
- superseded: 2
- newly added task: KL-019 minimal protocol execution slice

## Important remaining boundary
This package hardens the development contract; it does not claim that the user's local repository has already implemented `uv run kl check-harness`, CI, PostgreSQL DC/WF tests, or application code. KL-001 is the first task that should materialize the validator into the actual repo/toolchain.

## Spot-check cleanup
Superseded Plan v0.3/v0.4, Harness Backlog v0.1 and Workflow v0.1 were moved under `docs/history/v1.2.3-harness/`; current backlog context paths now point at Plan v0.5.
