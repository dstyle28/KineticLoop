"""Draft HG036 KL047 definition; apply only after actual HG035 normal merge."""
import copy
import json
from pathlib import Path

ROOT = Path.cwd()
EVIDENCE = ROOT / 'docs/exec-plans/evidence/HG-036'
task = copy.deepcopy(next(t for t in json.loads((ROOT / 'KineticLoop_Harness_Backlog_v0.2.json').read_text())['tasks'] if t['id'] == 'KL-047'))
task.update({
    'title': 'Fixed predeclared Fitness evaluation foundation and mechanical scorer',
    'packet_refinement': 'ENFORCEABLE', 'write_paths_status': 'ENFORCEABLE',
    'resource_keys': ['fitness_eval_contract'],
    'write_paths': [
        'src/kineticloop/evaluation/__init__.py',
        'src/kineticloop/evaluation/manifest.py',
        'src/kineticloop/evaluation/scorer.py',
        'src/kineticloop/evaluation/report.py',
        'tests/evaluation/test_manifest.py',
        'tests/evaluation/test_scorer.py',
        'tests/evaluation/test_report.py',
        'tests/evaluation/synthetic_cases.json',
        'tests/evaluation/predeclared_manifest.json',
        'docs/contracts/fitness_evaluation.md',
    ],
    'context_files': [
        '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md',
        '03_KineticLoop_Technical_Spec_v1.2.2_DEV_READY.md',
        '05_KineticLoop_Protocol_v1.2_FROZEN.md',
        '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
        '09_KineticLoop_Acceptance_and_Release_Gates_v1.2.2.md',
        'docs/contracts/shadow_test_semantics.md',
        'docs/contracts/artifact_registry.md',
    ],
    'entry_conditions': [
        'Actual KL-005 and KL-018 PASS results, required fresh reviews and MERGED integration records verified against the protected base.',
        'This offline gate builder helps BUILD G-REMOTE-AI; neither G-REMOTE-AI closure nor M7 real-data shadow entry is a prerequisite for this infrastructure task.',
        'All fixtures and observations are synthetic and local; no credentials, provider data, model invocation, database or external network is available to the scorer.',
        'KL-047 has no result or implementation at the protected base; every task check and product/gate/release obligation starts NOT_RUN.',
    ],
    'deliverables': [
        'Immutable source-bound synthetic case dataset and predeclared manifest with disjoint train/tune/test splits, freeze times, available-data rules and leakage checks.',
        'Pure deterministic mechanical scorer with immutable metric/config/scorer identity and exhaustive mandatory case/output correspondence.',
        'Immutable canonical report with per-case captured input/output hashes, exact release/artifact bundle provenance and explicit synthetic non-executable limitations.',
        'Contract preserving unresolved genuine Fitness quality decisions and all original G-REMOTE-AI, M7, S48 and release obligations independently of infrastructure task PASS.',
    ],
    'definition_of_done': 'Every named offline task check passes on tested_commit with committed evidence; mechanical synthetic scoring is reproducible and fail-closed, all mandatory negative cases run, and no Fitness quality, model evaluation, G-REMOTE-AI closure, M7 exit, product requirement or release PASS is claimed. Genuine quality corpus/rubric/sample-size/weights/threshold decisions and later measured release evaluation remain explicit unresolved obligations; infrastructure completion alone cannot satisfy the original project evaluation/release scope.',
    'evidence_paths': ['docs/exec-plans/evidence/KL-047/**'],
})
checks = [
 ('eval_manifest_identity_and_freeze_pu', 'uv run pytest -q tests/evaluation/test_manifest.py::test_manifest_identity_and_freeze', 'Content-bound case/dataset/split IDs, canonical immutable manifest and exact source hashes survive roundtrip; changed case, scorer or metric/threshold digest and postfreeze mutation reject under old identity.'),
 ('eval_split_and_knowledge_boundary_pu', 'uv run pytest -q tests/evaluation/test_manifest.py::test_split_and_knowledge_boundary', 'Train/tune/test membership is exhaustive and disjoint by case and underlying input identity; available-at/known-at after cutoff, future outcome labels, tuning reuse, missing freeze metadata and overlapping/leaking splits reject.'),
 ('eval_source_derived_cases_pu', 'uv run pytest -q tests/evaluation/test_scorer.py::test_source_derived_cases', 'Each mandatory synthetic mechanical case cites exact repository source path/hash/clause; well-formed non-executable output, refusal, malformed output, timeout, tool failure, budget exhaustion, forbidden execution target and knowledge-cutoff violation have source-derived expected outcomes. No expert recommendation or causal-effect labels are invented.'),
 ('eval_complete_observations_pu', 'uv run pytest -q tests/evaluation/test_scorer.py::test_complete_observations', 'Missing/duplicate/extra outputs, omitted mandatory case categories, unexecuted or missing observations, wrong input/output hashes and stale exact release/artifact bundle binding fail closed; model/prompt/engine/policy/config/scorer changes cannot retain the old evaluation identity.'),
 ('eval_deterministic_report_pu', 'uv run pytest -q tests/evaluation/test_report.py::test_deterministic_report', 'Equivalent ordered evidence yields byte-identical canonical reports and hashes without wall-clock or network dependence; caller input/output mutation cannot alter frozen manifest or report. Counts/denominators and each observation/hash/provenance are retained; no weighted Fitness quality aggregate is invented.'),
 ('eval_no_release_or_execution_claim_pu', 'uv run pytest -q tests/evaluation/test_report.py::test_no_release_or_execution_claim', 'Empty, synthetic-only, unexecuted and mechanically successful fixtures never yield release PASSED or quality PASS. Reports always expose synthetic provenance, NOT_EXECUTABLE, absent live targets and NOT_RUN product/gate/release statuses; no S48 writer/registry/authorization/provider/network side effect exists.'),
 ('eval_offline_suite_passes', 'uv run pytest -q tests/evaluation', 'Explicit discovery runs all new evaluation tests with no skipped/xfail/xpass cases; all six named selectors above are collected and executed. This explicit directory command is required because existing pytest testpaths and kl test-unit do not discover tests/evaluation.'),
 ('eval_existing_contract_regressions', 'uv run pytest -q tests/unit/contracts/test_shadow.py tests/unit/contracts/test_artifact_registry.py tests/unit/primitives/test_canonical.py tests/harness/acceptance/test_registry.py', 'Existing strict shadow, immutable artifact, canonical hashing and acceptance registry checks pass unchanged; generated product obligations remain NOT_RUN.'),
 ('harness_validation_passes', 'uv run kl check-harness', 'Current authorities, frozen baseline, exact task scope and result/evidence separation validate.'),
 ('lint_passes', 'uv run kl lint', 'Repository lint passes including evaluation package/tests.'),
 ('typecheck_passes', 'uv run kl typecheck', 'Repository typecheck passes including evaluation package/tests.'),
]
task['check_contracts'] = [dict(check_id=i, command=c, pass_oracle=o) for i,c,o in checks]
task['checks_required_for_this_task'] = [i for i,_,_ in checks]
(EVIDENCE / 'KL047_definition_draft.json').write_text(json.dumps(task, indent=2) + '\n')
