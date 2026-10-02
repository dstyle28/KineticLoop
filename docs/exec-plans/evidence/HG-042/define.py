"""Prepare bounded, prospective packets; final evidence waits for KL027 merge."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT / 'docs/exec-plans/evidence/HG-042'
BACKLOG = 'KineticLoop_Harness_Backlog_v0.2.json'
TRACE = 'KineticLoop_Harness_Traceability_v0.3.json'
PLAN = '06_KineticLoop_Project_Plan_v0.6_HARNESS_HARDENED.md'
audit = json.loads((HERE / 'boundary-preflight.json').read_text())
shadow = (HERE / 'shadow-preflight.md').read_text()
boundary_checks = [
    {'check_id': c['check_id'], 'command': c['selector'], 'pass_oracle': c['oracle']}
    for c in audit['support_checks'][:2]
]
for item in audit['obligations']:
    if item['disposition'] != 'DEFERRED_LAYER':
        boundary_checks.append({
            'check_id': item['check_id'], 'command': item['selector'],
            'pass_oracle': item['owner'] + ': ' + item['pass_oracle'],
        })
for c in audit['support_checks'][2:]:
    boundary_checks.append({
        'check_id': c['check_id'], 'command': c['selector'],
        'pass_oracle': 'Every owned named selector executes with positive controls and full '
                       'oracles; no skipped/xfail/zero collection substitute; exact owned '
                       'namespace validates before lifecycle and cleanup leaves no resources.',
    })
shadow_checks = []
for match in re.finditer(r'^\d+\. (\w+) — (uv run pytest[^\n]+)\n   (.*?)(?=\n\n\d|\n\n8–12)', shadow, re.M | re.S):
    shadow_checks.append({'check_id': match[1], 'command': match[2], 'pass_oracle': match[3].strip()})
assert len(shadow_checks) == 7
standard = [
    ('harness_validation_passes', 'check-harness', 'HARNESS_CHECK_PASS; current authorities, exact packet, scope and revision bindings validate.'),
    ('unit_regressions_pass', 'test-unit', 'All unit regressions pass without newly skipped/xfail or suppressed failures.'),
    ('harness_regressions_pass', 'test-harness', 'All harness regressions pass including negative scope and deferred-layer guards.'),
    ('lint_passes', 'lint', 'Repository lint passes.'),
    ('typecheck_passes', 'typecheck', 'Repository typecheck passes.'),
]
for checks in (boundary_checks, shadow_checks):
    checks.extend({'check_id': cid, 'command': 'uv run kl ' + cmd, 'pass_oracle': oracle}
                  for cid, cmd, oracle in standard)

namespace = ('Fixed suite label {label}; Compose kineticloop-{task}-{label}-<SHA7>-<ROOT12> '
             'and DB kineticloop_{task}_{label}_<SHA7>_<ROOT12>; SHA7 is first7 lowercase hex '
             'of exact 40-hex runtime Git HEAD, ROOT12 is first12 SHA256(os.fsencode(Path(ROOT).resolve())). '
             'Validate exact task/label/HEAD/root/namespace before lifecycle construction, nested '
             'bootstrap, reset, start, connect or destroy. Reject malformed/foreign/default/postgres/'
             'ambient targets and peer-root substitutions before runner calls. All nested builders '
             'receive the exact selected lifecycle or explicit owned URL; they never run foreign '
             'pytest lifecycle fixtures. Every connection asserts current_database, migration '
             'head and bounded statement/lock/wall deadlines; cleanup checks exact Compose labels '
             'and inventories no remaining owned containers, volumes or networks.')
owners = ('Read-only reuse of actual merged CanonicalViewService, projection/build preparation, '
          'ProtocolExecutionService.publish/commit_full/start/continue_session/pause/resume, '
          'KL075 RecordSnapshot/AdvanceAttempt, KL076 F/D/N and KL079 full action resolutions/'
          'validation, registry RegisterArtifact/RevokeArtifact and restricted ApplyControl/'
          'Reauthorize owners. Only explicitly declared upstream admitted immutable inputs and '
          'isolated TEST registrations/policies/environments may be bootstrapped. Actual owners '
          'produce tested seals, manifests, snapshots, F/D/N, resolutions/certificates, bundles, '
          'issuances and sessions/bindings; no raw target seeds, reopened terminal intent, '
          'caller-selected completeness, target timestamp mutation or callback no-op may stand '
          'in for owner behavior. A missing owner or owner bug requires a separate bounded fix '
          'and leaves its exact obligation NOT_RUN; it does not authorize a fixture bypass.')
evidence = ('Every check records exact tested SHA, namespace, selector collection/execution '
            'counts, actual guard reached, trusted clock, complete source/output IDs and hashes, '
            'closure identities/certificate digest, frontier/epoch/revision/current heads, '
            'session lifecycle and immutable binding history, receipt/event/outbox joins and '
            'full before/after history snapshots proving exact zero-effect denial/rollback. '
            'Positive controls establish every otherwise-valid guard and lifecycle. Fresh '
            'command keys distinguish current permission from historical replay. Registry races '
            'observe pg_blocking_pids and actual S51→S01 acquisition with bounded barriers in '
            'both orders, never sleep-based assumptions. Exact equality is PU; actual fresh '
            'post-lock PostgreSQL time is DC. No historical test/log reuse as new PASS, skips, '
            'xfail, zero collection, SQL-text/hash-only or invented mini-model evidence.')
parallel = ('After all dependencies, including actual normal KL027 merge, are met, KL028 '
            'and KL029 may run isolated DB tests in parallel despite the generic coordination '
            'serialization rule: their owners are read-only shared source, their exact three '
            'implementation paths and exclusive suite resource keys are disjoint, and each '
            'DB/Compose namespace includes its own task/SHA7/resolved-root SHA12. No shared '
            'conftest/helper/source/migration/grant/lifecycle/CI changes. Same database, foreign '
            'fixture lifecycle, overlapping write/resource keys or an unmerged owner forbids '
            'parallel execution. Keep all applicable unchanged hosted PostgreSQL CI checks.')
layer_boundary = ('All 31 acceptance B-layer obligations are retained (8 PU + 14 DC + '
                  '8 E2E + 1 WF). Definite mechanical capacity is 19 obligations (6 PU + '
                  '13 DC); 12 layers are deferred, including B04 DC because merged full '
                  'TEST owners explicitly reject complete Reauthorize. Every status is '
                  'prospectively NOT_RUN. Eight E2E obligations B04/B05/B07/B08/B10/B14/'
                  'B16/B18 need actual API→workflow→DB→eligibility/rendering per technical '
                  'spec §22 (lines 321–324); no public API/rendering owner is implemented '
                  'or concretely assigned. Internal service demonstrations never satisfy '
                  'that product layer. B11/B12 PU need an actual pure commit-state evaluator '
                  'not presently implemented; hashes, SQL text, relabeled DC or invented '
                  'mini-models cannot satisfy PU. B14 WF needs actual independent STOP '
                  'lane KL039 and assigned worker/fault infrastructure; its DC support '
                  'check is not WF/E2E PASS. Do not create an M3→M4 cycle to close this '
                  'ledger. B04 complete issue plus existing Reauthorize registry-guard '
                  'support is a mandatory task check, but B04@DC stays NOT_RUN until a '
                  'separate bounded full TEST reauthorization owner is merged and its '
                  'complete frozen oracle runs with owner-produced new intent/attempt/'
                  'snapshot/validation and an existing real prescription. No legacy '
                  'policy downgrade or guard-only substitution. Task PASS requires all '
                  'named task checks PASS plus truthful disposition of all 31 layers, '
                  'not every B product requirement PASS.')
shadow_boundary = ('KL008 ShadowEvaluationArtifact construction is M2 G-SHADOW contract '
                   'evidence, not complete real-data shadow usability. Actual shadow '
                   'store/API belongs to downstream KL045; API/rendering and R04@E2E '
                   'remain NOT_RUN. S46/S47 in this suite are explicitly declared '
                   'external evaluation inputs, never claimed shadow-workflow outputs. '
                   'Strict wire/owner ingress, registration guard, DB privilege/scope '
                   'and actual T7 guard denials have distinct reach labels; an earlier '
                   'ingress rejection cannot prove a later transaction guard. TEST '
                   'positive outputs come from actual full owner trajectories. '
                   'Evaluation cannot read/enumerate or write live TEST history; '
                   'forbidden crossings preserve complete source/issuance/START/revision/'
                   'binding/receipt/event/outbox history. No production/live shadow '
                   'authorization or execution binding is introduced.')
no_goals = ('No migrations, grants, production source, shared helpers/conftest, lifecycle, '
            'Compose, CI or dependency-lock writes. No M4 worker/outbox or shadow API/store '
            'implementation. No frozen authority changes. Production auto-activation stays '
            'disabled; real-data shadow stays non-executable; planned values never fill '
            'actual execution. No M3/release/G-SHADOW usability closure claim. The current '
            'MILESTONE_CLOSURE.schema.json supports only M1/M2: M3 closure support is a '
            'separate focused governance gap, not part of either packet.')

data = json.loads((ROOT / BACKLOG).read_text())
tasks = {t['id']: t for t in data['tasks']}
for name, label, resource, checks in (
    ('KL-028', 'boundary', 'boundary_acceptance_suite', boundary_checks),
    ('KL-029', 'shadow', 'shadow_isolation_suite', shadow_checks),
):
    t = tasks[name]
    t['write_paths'] = [f'tests/db/test_{"boundary_acceptance" if name == "KL-028" else "shadow_isolation"}.py',
                        f'tests/unit/protocol/test_{"boundary_acceptance" if name == "KL-028" else "shadow_isolation"}.py',
                        f'docs/contracts/{"boundary_acceptance" if name == "KL-028" else "shadow_isolation"}.md']
    t['resource_keys'] = [resource]
    t['shared_hotspot'] = False
    t['parallel_write_policy'] = 'PARALLEL_IF_DEPENDENCIES_MET'
    t['packet_refinement'] = 'ENFORCEABLE'
    t['write_paths_status'] = 'ENFORCEABLE'
    t['check_contracts'] = checks
    t['checks_required_for_this_task'] = [c['check_id'] for c in checks]
    t['evidence_paths'] = [f'docs/exec-plans/evidence/{name}/**']
    t['required_test_layers'] = ['PU', 'DC', 'WF', 'E2E'] if name == 'KL-028' else ['PU', 'DC', 'E2E']
    t['environment_requirements'] = [namespace.format(label=label, task=name.lower().replace('-', ''))]
    t['entry_conditions'] = [
        'M2 mechanical closure PASS: docs/exec-plans/milestones/M2.json; G-SHADOW contract construction and G-REGISTRY boundaries precede affected contracts, not real-data shadow usability.',
        'All listed dependencies normally merged; actual KL027 source/result/reviews and full owner-produced TEST trajectory verified at protected base before final tests.',
        'Exact task-owned namespace and read-only merged owner/fixture inventory verified before lifecycle; no foreign legacy DB fixture runs.',
        'No result/review/integration exists for this unstarted task; every prospective check and product-layer disposition begins NOT_RUN.',
    ]
    t['context_files'] = [
        '05_KineticLoop_Protocol_v1.2_FROZEN.md', '04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md',
        '09_KineticLoop_Acceptance_and_Release_Gates_v1.2.2.md',
        'KineticLoop_Acceptance_Spec_v1.2.2.json', 'docs/exec-plans/milestones/M2.json',
        'docs/contracts/test_only_demo.md', 'docs/contracts/full_test_execution.md',
        'docs/contracts/protocol_execution.md', 'docs/contracts/protocol_interleavings.md',
        'docs/contracts/full_action_preparation.md', 'docs/contracts/repository_transactions.md',
        'docs/contracts/factsets.md', 'docs/contracts/artifact_registry.md',
        'docs/contracts/shadow_test_semantics.md', 'docs/contracts/subject_scope.md',
        'tests/db/test_test_only_demo.py', 'tests/db/test_full_test_execution.py',
        'tests/db/test_protocol_interleavings.py',
    ]
    if name == 'KL-029':
        t['review_requirements'] = ['DB_CONCURRENCY', 'GENERAL', 'PROTOCOL', 'SECURITY_DATA_BOUNDARY']
        t['invariant_ids'] = ['INV-02', 'INV-09', 'INV-10', 'INV-15', 'INV-16']
        t['table_ids'] = ['S38', 'S42', 'S45', 'S46', 'S47']
    t['deliverables'] = [
        'Exact tests-only positive/negative selectors over real merged owners with durable raw PU and isolated PostgreSQL DC evidence.',
        'Task-owned namespace/cleanup inventory and precise guard-reach, immutable history and zero-effect witnesses.',
        'Truthful complete B01-B18 layer ledger; unavailable layers NOT_RUN.' if name == 'KL-028' else
        'Strict wire, registered evaluation storage and TEST crossing evidence; real-data shadow usability remains NOT_RUN.',
    ]
    t['definition_of_done'] = ('Every named task check and exact oracle executes and passes against tested_commit with committed raw evidence, '
                              'positive controls and no skipped/xfail/zero-collection substitutes; declared tests-only scope, '
                              'actual merged owner boundaries, isolated namespaces and immutable history hold. ' +
                              ('All 31 B layer obligations have explicit truthful dispositions; unavailable layers and any guard-only '
                               'B04 DC remain NOT_RUN, never omitted or relabeled. ' if name == 'KL-028' else
                               'Forbidden evaluation/TEST crossings preserve complete live TEST history; guard reach is accurately labeled. ') +
                              'Task PASS does not require every B product PASS or establish product E2E, M3/release/shadow-usability closure.')
    bullets = lambda xs: '\n'.join('- ' + x for x in xs) if xs else '- none'
    packet = f'''# {name} — {t['title']}

**Task identity:** `{t['task_identity']}`{'  '}
**Thread:** `{t['thread_id']}`{'  '}
**Milestone:** `M3`{'  '}
**Mode:** one fresh thread + one worktree + one PR{'  '}
**Status:** NOT_STARTED{'  '}
**Packet refinement:** ENFORCEABLE

## Goal
Implement the bounded tests-only mechanical suite over merged owners and preserve truthful deferred product layers.

## Dependencies
{', '.join(t['depends_on'])}

### Conditional dependencies
- none

## Entry conditions
{bullets(t['entry_conditions'])}

## Read first
Read root AGENTS.md, current index, this packet and merged prerequisite results first; then only the named sections below as needed.
{bullets(t['context_files'])}

## Frozen impact map
- Invariants: {', '.join(t['invariant_ids'])}
- Transactions: {', '.join(t['transaction_boundaries'])}
- Logical tables: {', '.join(t['table_ids'])}

Named clauses: Protocol §§0.3a, 2.1a, 4.1a, 5.3/5.3a/5.4/5.5/5.6 and Replay §7.4; DB S15/S16/S38/S42/S45/S46/S47/S49/S50/S51, §§4.1/4.3/5 and R04; current acceptance §§2–3 and supplemental boundary Given/When/Then/layers. Expand only unresolved cross-references.

## Requirements covered (does NOT mean PASS)
{bullets(t['requirements_covered'])}

## Checks required for this task PR
{bullets(t['checks_required_for_this_task'])}

## Machine-readable check contract
```json
{json.dumps({'check_contracts': checks, 'evidence_paths': t['evidence_paths']}, indent=2)}
```

## Prospective check status
```json
{json.dumps({c['check_id']: 'NOT_RUN' for c in checks}, indent=2)}
```

## Resource / write isolation
Resource keys:
{bullets(t['resource_keys'])}

Expected write paths:
{bullets(t['write_paths'])}

Environment requirements:
{bullets(t['environment_requirements'])}

Parallel write policy: **PARALLEL_IF_DEPENDENCIES_MET**. Reject overlapping exclusive keys or write paths.
Shared hotspot: **false**

## Merged owner and bootstrap boundary
{owners}

## Evidence and concurrency oracles
{evidence}

## Isolated parallel test plan
{parallel}

## Deferred layer boundary
{layer_boundary if name == 'KL-028' else shadow_boundary}

## Deliverables
{bullets(t['deliverables'])}

## Definition of Done
{t['definition_of_done']}

## Review requirements
{bullets(t['review_requirements'])}

Reviews bind exact implementation/result SHA; only own REVIEW_RECORD_ONLY suffix is allowed. KL029 SECURITY_DATA_BOUNDARY covers confidentiality, non-enumeration and registered evaluation principal isolation.

## Non-goals
{no_goals}

## Verification
Run all exact named checks; record command/result/raw evidence against tested_commit. Do not infer a product layer PASS from task PASS. Freeze semantic changes require SPEC_CHANGE_REQUIRED.

## Completion
Commit docs/exec-plans/completed/{name}_RESULT.yaml under the result contract; preserve every unavailable obligation as NOT_RUN with its exact owner gap and follow-up.
'''
    if name == 'KL-028':
        packet += '\n## Boundary layer ledger\n```json\n' + json.dumps(audit['obligations'], indent=2) + '\n```\n'
    (ROOT / f'docs/exec-plans/active/{name}.md').write_text(packet)

(ROOT / BACKLOG).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
trace = json.loads((ROOT / TRACE).read_text())
import importlib.util
spec = importlib.util.spec_from_file_location('definition_validator', ROOT / 'tools/harness/validate_harness.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
trace['tasks'] = [validator.traceability_projection(tasks[t['id']])
                  if t['id'] in ('KL-028', 'KL-029') else t for t in trace['tasks']]
(ROOT / TRACE).write_text(json.dumps(trace, indent=2, ensure_ascii=False) + '\n')
resources = ROOT / 'docs/harness/RESOURCE_LOCKS.md'
if '`boundary_acceptance_suite`' not in resources.read_text():
    resources.write_text(resources.read_text() + '\n- `boundary_acceptance_suite`\n- `shadow_isolation_suite`\n\nHG042 grants only disjoint tests-only suites using separate task/SHA7/resolved-root SHA12 databases and Compose namespaces. Shared owners are read-only; no source, grant, migration, helper, lifecycle or CI writes.\n')
plan = ROOT / PLAN
heading = '\n## M3 boundary and shadow readiness — HG042\n'
old_plan = plan.read_text()
outside_suffix = old_plan.partition('<!-- HG042 plan end -->')[2]
plan.write_text(old_plan.split(heading)[0] + heading + '\n' + parallel + '\n\n' + layer_boundary + '\n\n' + shadow_boundary + '\n\n' + no_goals + '\n\n<!-- HG042 plan end -->\n' + outside_suffix)

# Exact definitions and whole packet digests, guarded against silent scope drift.
definition_hashes = {n: hashlib.sha256(json.dumps(tasks[n], ensure_ascii=False, sort_keys=True,
                                                separators=(',', ':')).encode()).hexdigest()
                     for n in ('KL-028', 'KL-029')}
packet_hashes = {n: hashlib.sha256((ROOT / f'docs/exec-plans/active/{n}.md').read_bytes()).hexdigest()
                 for n in ('KL-028', 'KL-029')}
(HERE / 'packet-pins.json').write_text(json.dumps({'definitions': definition_hashes, 'packets': packet_hashes}, indent=2) + '\n')
print(definition_hashes, packet_hashes)
