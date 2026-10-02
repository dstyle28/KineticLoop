"""Read-only actual existing pure legacy/full pipelines; diagnose protected-base defect."""
import importlib.util
import json
import subprocess
from uuid import uuid4

from kineticloop.workflow.deterministic_planning import (
    FULL_VERSION, Fact, compute_demand, compute_fitness, compute_nutrition, resolve_full, validate_full,
)
from kineticloop.workflow.planning import PlanningDenied, digest


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('tests/unit/workflow/test_deterministic_planning.py', 'legacy')
full = load('tests/unit/workflow/test_full_action_preparation.py', 'full')
results = []
for profile, builder in [('legacy', legacy), ('full', full)]:
    for admission, association in [('ADMITTED', 'CONFIRMED'), ('ELIGIBLE', 'CONFIRMED'),
                                   ('ADMITTED', 'MATCHED'), ('ELIGIBLE', 'MATCHED')]:
        base, config, facts, now = builder.source_case()
        facts = (Fact.model_validate_json(json.dumps({**facts[0].payload(),
                                                      'admission': admission,
                                                      'association': association})),)
        try:
            if profile == 'legacy':
                f, d, n, resolution = legacy.chain(base, config, facts, now)
                value = legacy.validate(f, d, n, resolution, config, now)
                status = resolution.event_association_status
            else:
                config.update(contract=FULL_VERSION, required_actions=['TRAINING', 'NUTRITION'])
                f = compute_fitness(base, str(uuid4()), {'minutes': 30, 'equipment': []}, None)
                d = compute_demand(f, str(uuid4()), config)
                n = compute_nutrition(f, d, str(uuid4()), config)
                source_id = str(uuid4())
                resolutions = tuple(resolve_full(
                    f, d, n, str(uuid4()), config, facts, action_type=action,
                    manifest_hash=digest('manifest'), source_id=source_id, source_hash=digest('sealed'),
                    members=tuple(config['required_members']), expires_at=config['valid_until'],
                ) for action in ('TRAINING', 'NUTRITION'))
                value = validate_full(f, d, n, resolutions, config, now)
                status = ','.join(row.event_association_status for row in resolutions)
            results.append(dict(profile=profile, s13=admission, s12=association, accepted=True,
                                derived_s36=status, rolling_minutes=value['rolling_minutes']))
        except PlanningDenied as error:
            results.append(dict(profile=profile, s13=admission, s12=association,
                                accepted=False, error=str(error)))
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
assert head == '26906bd7f4444914c228e98377f2b164fee0dd5d', 'preflight binds protected base only'
assert len(results) == 8 and sum(row['accepted'] for row in results) == 2
print(json.dumps(dict(protected_base=head, probe='existing pure pipelines; no lifecycle or target writes',
                     rows=results), indent=2))
