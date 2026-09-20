import unittest
from kineticloop_model.interleavings import run_all


class InterleavingTests(unittest.TestCase):
    def test_all_bounded_interleavings(self):
        results = run_all()
        self.assertEqual(9, len(results))
        for result in results:
            with self.subTest(scenario=result['scenario']):
                self.assertGreater(result['complete_schedules'], 1)
                self.assertEqual(0, result['deadlocks'])
                self.assertEqual([], result['violations'])
                self.assertGreater(len(result['outcomes']), 1)
