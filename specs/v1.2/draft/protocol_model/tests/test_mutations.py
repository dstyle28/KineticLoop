"""Negative controls: intentionally broken guards must fail existing tests."""
import unittest
from unittest.mock import patch

from kineticloop_model.model import ProtocolModel, seeded_model
from tests import test_acceptance


def skipping(code):
    class MissingGuard(ProtocolModel):
        def check(self, condition, actual_code):
            if actual_code != code:
                super().check(condition, actual_code)
    return MissingGuard


class MissingValidityClosure(ProtocolModel):
    def validity_closure(self, mid, validation, requested_until):
        end = min(requested_until, self.db.now + self.policy['authorization_ttl'])
        return end, {'requested_only': end}


class CherryPickingResolver(ProtocolModel):
    def resolve(self, *args, **kwargs):
        result = super().resolve(*args, **kwargs)
        result['contradicting'] = []
        return result


class UnknownBecomesZero(ProtocolModel):
    def resolve(self, *args, **kwargs):
        result = super().resolve(*args, **kwargs)
        if result['upper'] is None:
            result.update(minimum=0, upper=0)
        return result


MUTANTS = [
    ('missing_user_epoch_guard', skipping('EPOCH_MISMATCH'), 'AcceptanceTests', 'test_D05'),
    ('missing_fencing_guard', skipping('FENCE_MISMATCH'), 'AcceptanceTests', 'test_W05'),
    ('unsealed_factset_readable', skipping('FACTSET_UNSEALED'), 'BoundaryTests', 'test_P01_unsealed_not_canonical'),
    ('missing_global_revocation_guard', skipping('ARTIFACT_REVOKED'), 'BoundaryTests', 'test_P04_artifact_revocation_stops_issue_and_execution'),
    ('authorization_outlives_dependencies', MissingValidityClosure, 'BoundaryTests', 'test_P06_ttl_closure_each_component'),
    ('refund_possible_dispatch', skipping('MAY_HAVE_DISPATCHED'), 'AcceptanceTests', 'test_W01'),
    ('resolver_ignores_contradictions', CherryPickingResolver, 'AcceptanceTests', 'test_E06'),
    ('unknown_exposure_zeroed', UnknownBecomesZero, 'AcceptanceTests', 'test_E05'),
]


def evaluate_mutants():
    results = []
    for name, model_class, test_class, test_method in MUTANTS:
        def seed(*args, **kwargs):
            return seeded_model(model_class=model_class, **kwargs)
        with patch.object(test_acceptance, 'seeded_model', seed):
            case = getattr(test_acceptance, test_class)(test_method)
            result = unittest.TestResult()
            case.run(result)
        detected = bool(result.failures or result.errors)
        results.append({'mutant': name, 'detected': detected, 'test': test_class + '.' + test_method,
                        'failure_kind': 'assertion' if result.failures else 'invariant_or_error' if result.errors else 'SURVIVED'})
    return results


class MutationTests(unittest.TestCase):
    def test_seeded_faults_are_detected(self):
        for result in evaluate_mutants():
            with self.subTest(mutant=result['mutant']):
                self.assertTrue(result['detected'], result)
