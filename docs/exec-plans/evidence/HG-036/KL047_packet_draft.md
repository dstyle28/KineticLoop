# KL-047 — Fixed predeclared Fitness evaluation foundation and mechanical scorer

**Task identity:** `harness-backlog-v0.2/KL-047`
**Thread:** `THREAD-KL-047`
**Milestone:** `M7`
**Mode:** one fresh thread + one worktree + one PR
**Status:** NOT_STARTED
**Packet refinement:** ENFORCEABLE

## Goal

Implement only the fixed synthetic offline infrastructure foundation and source-derived mechanical scorer. Preserve genuine Fitness quality and all original evaluation/release obligations as unresolved; infrastructure task PASS does not close them.

## Dependencies

KL-005, KL-018

### Conditional dependencies
- none

## Entry conditions
- Actual KL-005 and KL-018 PASS results, required fresh reviews and MERGED integration records verified against the protected base.
- This offline gate builder helps BUILD G-REMOTE-AI; neither G-REMOTE-AI closure nor M7 real-data shadow entry is a prerequisite for this infrastructure task.
- All fixtures and observations are synthetic and local; no credentials, provider data, model invocation, database or external network is available to the scorer.
- KL-047 has no result or implementation at the protected base; every task check and product/gate/release obligation starts NOT_RUN.

## Read first

Read root AGENTS.md, CURRENT_DOCUMENT_INDEX.json, this packet and actual merged prerequisite results/reviews/integrations first. Open only relevant source sections: plan G-REMOTE-AI/M7, Technical Spec section 11 and shadow path, Protocol 7.2–7.5, frozen S48, current release gates and the existing strict contract sources. Historical task IDs without namespace are not authority.

- 06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md
- 03_KineticLoop_Technical_Spec_v1.2.2_DEV_READY.md
- 05_KineticLoop_Protocol_v1.2_FROZEN.md
- 04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md
- 09_KineticLoop_Acceptance_and_Release_Gates_v1.2.2.md
- docs/contracts/shadow_test_semantics.md
- docs/contracts/artifact_registry.md

## Frozen impact map
- Invariants: INV-16
- Transactions: none
- Logical tables: S48

S48 is a read-only constraint reference; no S48 writer, database change, registration, production release selection or activation is authorized.

## Requirements covered (does NOT mean PASS)
- none

## Checks required for this task PR
- eval_manifest_identity_and_freeze_pu
- eval_split_and_knowledge_boundary_pu
- eval_source_derived_cases_pu
- eval_complete_observations_pu
- eval_deterministic_report_pu
- eval_no_release_or_execution_claim_pu
- eval_offline_suite_passes
- eval_existing_contract_regressions
- harness_validation_passes
- lint_passes
- typecheck_passes

## Machine-readable check contract

```json
{
  "check_contracts": [
    {
      "check_id": "eval_manifest_identity_and_freeze_pu",
      "command": "uv run pytest -q tests/evaluation/test_manifest.py::test_manifest_identity_and_freeze",
      "pass_oracle": "Content-bound case/dataset/split IDs, canonical immutable manifest and exact source hashes survive roundtrip; changed case, scorer or metric/threshold digest and postfreeze mutation reject under old identity."
    },
    {
      "check_id": "eval_split_and_knowledge_boundary_pu",
      "command": "uv run pytest -q tests/evaluation/test_manifest.py::test_split_and_knowledge_boundary",
      "pass_oracle": "Train/tune/test membership is exhaustive and disjoint by case and underlying input identity; available-at/known-at after cutoff, future outcome labels, tuning reuse, missing freeze metadata and overlapping/leaking splits reject."
    },
    {
      "check_id": "eval_source_derived_cases_pu",
      "command": "uv run pytest -q tests/evaluation/test_scorer.py::test_source_derived_cases",
      "pass_oracle": "Each mandatory synthetic mechanical case cites exact repository source path/hash/clause; well-formed non-executable output, refusal, malformed output, timeout, tool failure, budget exhaustion, forbidden execution target and knowledge-cutoff violation have source-derived expected outcomes. No expert recommendation or causal-effect labels are invented."
    },
    {
      "check_id": "eval_complete_observations_pu",
      "command": "uv run pytest -q tests/evaluation/test_scorer.py::test_complete_observations",
      "pass_oracle": "Missing/duplicate/extra outputs, omitted mandatory case categories, unexecuted or missing observations, wrong input/output hashes and stale exact release/artifact bundle binding fail closed; model/prompt/engine/policy/config/scorer changes cannot retain the old evaluation identity."
    },
    {
      "check_id": "eval_deterministic_report_pu",
      "command": "uv run pytest -q tests/evaluation/test_report.py::test_deterministic_report",
      "pass_oracle": "Equivalent ordered evidence yields byte-identical canonical reports and hashes without wall-clock or network dependence; caller input/output mutation cannot alter frozen manifest or report. Counts/denominators and each observation/hash/provenance are retained; no weighted Fitness quality aggregate is invented."
    },
    {
      "check_id": "eval_no_release_or_execution_claim_pu",
      "command": "uv run pytest -q tests/evaluation/test_report.py::test_no_release_or_execution_claim",
      "pass_oracle": "Empty, synthetic-only, unexecuted and mechanically successful fixtures never yield release PASSED or quality PASS. Reports always expose synthetic provenance, NOT_EXECUTABLE, absent live targets and NOT_RUN product/gate/release statuses; no S48 writer/registry/authorization/provider/network side effect exists."
    },
    {
      "check_id": "eval_offline_suite_passes",
      "command": "uv run pytest -q tests/evaluation",
      "pass_oracle": "Explicit discovery runs all new evaluation tests with no skipped/xfail/xpass cases; all six named selectors above are collected and executed. This explicit directory command is required because existing pytest testpaths and kl test-unit do not discover tests/evaluation."
    },
    {
      "check_id": "eval_existing_contract_regressions",
      "command": "uv run pytest -q tests/unit/contracts/test_shadow.py tests/unit/contracts/test_artifact_registry.py tests/unit/primitives/test_canonical.py tests/harness/acceptance/test_registry.py",
      "pass_oracle": "Existing strict shadow, immutable artifact, canonical hashing and acceptance registry checks pass unchanged; generated product obligations remain NOT_RUN."
    },
    {
      "check_id": "harness_validation_passes",
      "command": "uv run kl check-harness",
      "pass_oracle": "Current authorities, frozen baseline, exact task scope and result/evidence separation validate."
    },
    {
      "check_id": "lint_passes",
      "command": "uv run kl lint",
      "pass_oracle": "Repository lint passes including evaluation package/tests."
    },
    {
      "check_id": "typecheck_passes",
      "command": "uv run kl typecheck",
      "pass_oracle": "Repository typecheck passes including evaluation package/tests."
    }
  ],
  "evidence_paths": [
    "docs/exec-plans/evidence/KL-047/**"
  ]
}
```

Execute every exact command on tested_commit. All checks begin NOT_RUN; no skip/xfail/xpass or zero collected tests meets a PASS oracle. Record committed output and counts. The full explicit evaluation suite must run in addition to every named selector. Existing default test discovery cannot substitute for it.

## Resource / write isolation

Resource keys:
- fitness_eval_contract

Expected write paths:
- src/kineticloop/evaluation/__init__.py
- src/kineticloop/evaluation/manifest.py
- src/kineticloop/evaluation/scorer.py
- src/kineticloop/evaluation/report.py
- tests/evaluation/test_manifest.py
- tests/evaluation/test_scorer.py
- tests/evaluation/test_report.py
- tests/evaluation/synthetic_cases.json
- tests/evaluation/predeclared_manifest.json
- docs/contracts/fitness_evaluation.md

Environment requirements:
- none

Parallel write policy: **PARALLEL_IF_DEPENDENCIES_MET**. Reject overlapping resource keys/write paths before scheduling. Pure local functions own fitness_eval_contract only; no DB/Compose resources exist. Preserve all existing files outside this exact list, including shared package markers. Normal task result/evidence/review bookkeeping is permitted only under KL-047's own contract paths. No product/requirement registry status may be changed.

## Deliverables
- Immutable source-bound synthetic case dataset and predeclared manifest with disjoint train/tune/test splits, freeze times, available-data rules and leakage checks.
- Pure deterministic mechanical scorer with immutable metric/config/scorer identity and exhaustive mandatory case/output correspondence.
- Immutable canonical report with per-case captured input/output hashes, exact release/artifact bundle provenance and explicit synthetic non-executable limitations.
- Contract preserving unresolved genuine Fitness quality decisions and all original G-REMOTE-AI, M7, S48 and release obligations independently of infrastructure task PASS.

## Definition of Done
Every named offline task check passes on tested_commit with committed evidence; mechanical synthetic scoring is reproducible and fail-closed, all mandatory negative cases run, and no Fitness quality, model evaluation, G-REMOTE-AI closure, M7 exit, product requirement or release PASS is claimed. Genuine quality corpus/rubric/sample-size/weights/threshold decisions and later measured release evaluation remain explicit unresolved obligations; infrastructure completion alone cannot satisfy the original project evaluation/release scope.

## Review requirements
- GENERAL
- PROTOCOL

Fresh independent review binds the implementation/result SHA; only the task's own REVIEW_RECORD_ONLY suffix may follow without rereview.

## Offline contract and source-derived oracles

This task supplies an offline infrastructure foundation for the original fixed evaluation set/scorer goal. It cannot honestly complete genuine Fitness recommendation quality evaluation with the currently available sources. Task PASS covers only the mechanically testable foundation below; the original project quality and release obligations remain open and are not redefined by this packet.

Use existing `canonical_json` / `canonical_sha256` without changing them. Define strict immutable manifest, case, observation and report values in the new evaluation package. Reject unknown/missing/duplicate fields and non-canonical identifiers/hashes. `src/kineticloop/evaluation/__init__.py` is the sole permitted new package marker; no shared marker or provider-fixture schema change is authorized. The established src package build includes this new package. Tests use direct `kineticloop.evaluation` imports and the exact `uv run pytest -q tests/evaluation` command; no pytest testpaths, CLI, dependency or CI edit is needed or authorized.

The fixed synthetic dataset has content-bound case IDs over canonical input, expected mechanical outcome, source references and provenance. Dataset and split identities bind the exact complete ordered membership and case hashes. Every case records synthetic origin, source path + SHA256 + section/clause, immutable captured input and hash, declared cutoff and available/known times. It must never contain real provider/user/model observations or encode planned values as actual execution. No typed production FitnessProposal contract exists yet: do not create one here. Technical Spec section 11 provides proposal categories and immutability only, without reference recommendations or expert quality labels. An opaque synthetic proposal payload may be hash-bound without asserting its clinical or training quality.

Predeclare train/tune/test membership, dataset/split freeze times, metric configuration, scorer version/content digest and available-data/leakage rules before observing outputs. Train/tune sets may be explicitly empty for this mechanical foundation, with no training/tuning performed; test must be nonempty and include every mandatory category. Reject overlapping underlying input identities even if case IDs differ. Protocol 7.3 excludes individual knowledge and outcome labels unavailable at cutoff, and tuned-on-test reuse cannot be represented as independent validation. Reports also retain Protocol 7.3's limitation that a current model's broad training knowledge cannot be reconstructed as past model knowledge; synthetic current-algorithm derivations must be identified as counterfactual, never as historically known facts. A declared synthetic freeze timestamp is test metadata, not proof of historical custody; postfreeze mutation under the same identity must reject. Changed dataset/splits/scorer/config/thresholds require new content identities, and changed thresholds or model cannot retain the old release identity (S48).

Mandatory synthetic categories and oracle sources:

- Complete well-formed non-executable artifact: strict `ShadowEvaluationArtifact` and `docs/contracts/shadow_test_semantics.md`; null S38/S42/S45/live-success targets.
- Refusal, malformed output and timeout: plan G-REMOTE-AI; record the actual synthetic observed outcome and preserve absent proposal/output for refusal/timeout rather than manufacture a successful recommendation.
- Tool failure and budget exhaustion: plan M7 fixture requirements; capture failure evidence without a success or execution claim.
- Forbidden live target or execution capability: Technical Spec shadow path, strict shadow contract and Protocol 7.4; reject rather than issue authorization.
- Knowledge-cutoff violation: Protocol 7.2–7.3; exclude data learned after cutoff and retain available-data/leakage evidence.

The scorer tests observation completeness and identity correspondence, format/error/refusal/timeout handling, non-executability, cutoff adherence and input immutability only. Expected outcomes cite these source contracts. Metrics are per-case mechanical checks with explicit counts/denominators; metric/threshold config can contain exact source-derived boolean acceptance predicates but no invented quality thresholds, sample-size sufficiency, weighting scheme or recommendation-quality aggregate. Bind the frozen scorer bytes and metric/config digest; reject tampering even when a caller supplies a recomputed digest inconsistent with the predeclared release bundle.

Each observation binds case/dataset/split IDs, execution disposition, observed synthetic outcome, exact captured input/output content and hashes (including explicit null plus a reason when no output exists), observed timing/timeout evidence and the exact release ID and model/prompt/engine/policy artifact refs + versions + content hashes. Synthetic placeholder artifact identities must be explicitly local unregistered fixtures, never capabilities. Include rollout decision provenance explicitly identifying no rollout decision, not a fabricated authorization. A report retains all bindings, scorer/config/freeze metadata and evidence refs, yields deterministic canonical bytes/content hash, and never mutates caller inputs. No registry call or S48 write is in scope. `ReleaseEvaluationService.RecordRelease` remains S48's sole writer; this package cannot admit a production release.

Fail closed for altered cases, scorer/config/threshold digests, missing/duplicate/extra outputs, omitted mandatory categories, overlapping/leaking splits, stale release/artifact bundle refs, missing/unexecuted observations and postfreeze mutation. Empty/unexecuted observations may produce an explicitly incomplete diagnostic report or reject; they cannot produce a successful evaluation. Synthetic mechanical success always leaves model evaluation, Fitness quality, product requirements, G-REMOTE-AI, M7 and release admission NOT_RUN. Reports state synthetic provenance, NOT_EXECUTABLE, no live targets, no measured model result and no release PASSED. Never conflate refusal handling with recommendation-quality PASS or counterfactual outputs with observed training effects (Protocol 7.5).

## Preserved quality and release obligations

Before genuine Fitness quality/model evaluation, the project still needs a separately reviewed representative corpus and expert labels/reference judgments, quantitative quality rubric, sample-size justification, weighting/aggregation decisions, predeclared quality thresholds, corpus freeze/custody and independent splits. None is supplied by the present Technical Spec. Do not invent or defer these as already satisfied. This contract must preserve these precise open decisions and distinguish synthetic foundation completion from the original project evaluation obligation. No new task identity or downstream packet change is authorized here; later governance must assign any uncovered decision/implementation scope with an enforceable packet before scheduling it.

G-REMOTE-AI still requires the exact release/artifact identity, outbound allowlist/redaction, fixed subset with refusal/bad-output/timeout coverage and captured real run inputs/outputs before real context leaves the system. M7 still requires structured FitnessProposal, bounded tools, F→D→N dependencies, validation and reproducible real-data SHADOW_ONLY / NOT_EXECUTABLE evaluation. S48 still requires measured evaluation results, exact production artifact/report provenance, declared split IDs/freeze times/metric-threshold config and a new release when thresholds/model change. Protocol 7.5 causal/training-effect claims require a separate research/experiment design. Synthetic task tests satisfy none of these broader gate/quality/release conclusions. Hevy plus HealthKit remain mandatory launch scope; the retired spreadsheet task remains retired.

## Non-goals

No agents/**, typed FitnessProposal, model adapter/tool execution, actual remote model evaluation, persistence/migrations/coordination transactions, CLI/dependency/CI edits, S48 writes, shared requirement registry mutation, provider schema broadening, live authorization/execution or synthetic production capability registration. Do not implement KL-047 in the HG-036 governance thread. Preserve frozen authorities and completed-task results/evidence.

## Completion

Commit `docs/exec-plans/completed/KL-047_RESULT.yaml` before fresh GENERAL and PROTOCOL review. Record exact base/tested commits and each required command/evidence with task checks separate from product/gate/release status. All prospective KL-047 checks are NOT_RUN in HG-036. If implementation requires a frozen semantic change, return SPEC_CHANGE_REQUIRED without a workaround.
