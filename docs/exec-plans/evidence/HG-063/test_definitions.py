import unittest, copy, hashlib
from dataclasses import replace
from definition_oracle import *
from fixture_support import *
from functools import partial
inventory = partial(inventory, output_types=OUTPUT, roles=ROLES, catalog=CATALOG)

class Definitions(unittest.TestCase):

    def deny(self, body, ctx, catalog=CATALOG):
        with self.assertRaises(Denied):
            observe(catalog, ROLES, body, ctx)

    def test_all39_original_bindings_account_explicit_false_lineage(self):
        self.assertEqual(len(BINDINGS['rows']), 39)
        gaps = [x for x in BINDINGS['rows'] if x.get('lineage_gap')]
        self.assertEqual(len(gaps), 1)
        a = gaps[0]['lineage_gap']
        self.assertEqual(a['observed_ancestry_exit'], 1)
        self.assertIs(a['tested_delivery_ancestor'], False)
        self.assertTrue(gaps[0]['pins'])
        self.assertTrue(gaps[0]['indexed_authorities'])
        self.assertTrue(gaps[0]['original_review_duties'])
        self.assertTrue(gaps[0]['missing_review_absence'])
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D1_MISSING_ORIGINAL_GENERAL'))
        (body, ctx, _, _) = case(g)
        r = observe(CATALOG, ROLES, body, ctx)
        self.assertGreater(r['lineage_gap_count'], 0)
        self.assertEqual(r['lineage_gap_count'], len(ctx.checks))
        for e in r['entries']:
            self.assertIn(LINEAGE_LIMIT, e['limitations'])
            self.assertIn('MISSING_ORIGINAL_REVIEW', e['limitations'])
            self.assertIs(e['delivery_lineage']['tested_delivery_ancestor'], False)
            self.assertIs(e['acceptance_eligible'], False)
            self.assertEqual(e['historical_review_acceptance'], 'NOT_CERTIFIED')
        self.deny(body, replace(ctx, lineage_gap=None))

    def test_native_controls_keep_exact_index_command_bytes_exit_and_zero_documentary_count(self):
        controls = [r for r in ROWS['rows'] if r['disposition'] == 'KEEP_NATIVE_CAPTURE_PATH']
        self.assertEqual(len(controls), 6)
        for row in controls:
            observation = row['exit_observations'][0]
            check = observation['check']
            declared = row['checks'][0]
            self.assertEqual(check['command'], declared['command'])
            self.assertEqual(check['evidence_ref'], row['ref'])
            self.assertIs(type(check['exit_code']), int)
            self.assertEqual(check['exit_code'], 0)
            self.assertEqual(check['stdout_sha256'], row['report_identity']['sha256'])
            self.assertEqual(check['stdout_bytes'], row['report_identity']['bytes'])
            self.assertTrue(all(observation['binding_checks'].values()))
            self.assertEqual(row['documentary_entry_count'], 0)

    def test_complete_inventory_cannot_skip_an_invalid_mandatory_entry(self):
        g = CATALOG['profiles'][0]
        (body, ctx, _, _) = case(g)
        self.deny(body, replace(ctx, guards=tuple((x for x in GUARDS if x != 'independent_guards_complete'))))

    def test_counts_shared_report_separate_claim_tuples_and_duplicate_reject(self):
        g = next((g for g in CATALOG['profiles'] if g['record_check_shape']['ordered_report_ref_check_count'] > 2 and (not g['decision'])))
        (body, ctx, _, _) = case(g)
        r = observe(CATALOG, ROLES, body, ctx)
        self.assertGreater(len(r['entries']), 2)
        self.assertEqual(inventory(((body, ctx),), len(ctx.checks), tuple(r['covered_tuples']), True, candidate_outputs=[r])['documentary_unverified_count'], len(ctx.checks))
        with self.assertRaises(Denied):
            inventory(((body, ctx),), len(ctx.checks) * 2, tuple(r['covered_tuples']), True, candidate_outputs=[r, r])
        for count in [True, -1, len(ctx.checks) + 1, 0, None]:
            with self.assertRaises(Denied):
                inventory(((body, ctx),), count, tuple(r['covered_tuples']), True, candidate_outputs=[r])
        self.assertEqual(inventory((), 0, (), True, candidate_outputs=[])['documentary_unverified_count'], 0)
        with self.assertRaises(Denied):
            inventory(((body, ctx),), len(ctx.checks), tuple(r['covered_tuples']) + (('missing-required-tuple',),), True, candidate_outputs=[r])
        with self.assertRaises(Denied):
            inventory(((body, ctx),), len(ctx.checks), tuple(r['covered_tuples']), False, candidate_outputs=[r])

    def test_native_success_remains_native_and_is_not_missing_exit(self):
        g = CATALOG['profiles'][1]
        (body, ctx, _, _) = case(g)
        states = list(ctx.parent_states)
        states[0] = 'OBSERVED_EXACT_ZERO'
        r = observe(CATALOG, ROLES, body, replace(ctx, parent_states=tuple(states)))
        self.assertIn(0, r['native_ordinals'])
        self.assertEqual(r['documentary_unverified_count'], len(ctx.checks) - 1)

    def test_raw_dictionary_is_not_authenticated_fixture_context(self):
        (body, ctx, _, _) = case(CATALOG['profiles'][0])
        self.deny(body, dict(ctx.__dict__))

    def test_missing_original_review_has_exact_absence_duty_and_never_certifies_review(self):
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D1_MISSING_ORIGINAL_GENERAL'))
        (body, ctx, _, _) = case(g, True)
        r = observe(CATALOG, ROLES, body, ctx)
        self.assertTrue(all(('MISSING_ORIGINAL_REVIEW' in e['limitations'] for e in r['entries'])))
        self.assertFalse(r['review_acceptance_certified'])
        for change in [{'absence_proof': False}, {'review_state': 'PRESENT_BOUND_GENERAL'}, {'original_general_required': False}]:
            self.deny(body, replace(ctx, **change))

    def test_known_posttest_zero_has_full_separate_producer_revision(self):
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D3_POST_TEST_DIAGNOSTIC_PRODUCER'))
        (body, ctx, _, _) = case(g)
        r = observe(CATALOG, ROLES, body, ctx)
        e = r['entries'][0]
        self.assertNotEqual(e['exit_attribution']['producer'], ctx.T)
        self.assertEqual(e['exit_attribution']['value'], 0)
        self.assertFalse(e['exit_attribution']['execution_certified'])
        self.assertEqual(e['historical_execution'], 'UNVERIFIED_RECORD_REVISION_EXECUTION')
        bindings = dict(ctx.bindings, PRODUCER_Z=ctx.T)
        self.deny(body, replace(ctx, bindings=bindings))

    def test_composite_cannot_relabel_incomplete_parent_or_executable_check(self):
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D4_COMPOSITE_WITH_INCOMPLETE_COMPONENT'))
        (body, ctx, _, _) = case(g)
        self.deny(body, replace(ctx, composite_declared_non_execution=False))
        states = list(ctx.parent_states)
        n = states.index('EXPLICIT_NON_EXECUTION_COMPOSITE')
        states[n] = 'INCOMPLETE'
        self.deny(body, replace(ctx, parent_states=tuple(states)))

    def test_content_reuse_cannot_alias_source_revision_to_record_T(self):
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D5_CONTENT_REVISION_REUSE'))
        (body, ctx, _, _) = case(g)
        self.deny(body, replace(ctx, bindings=dict(ctx.bindings, SOURCE_T=ctx.T)))

    def test_duplicate_whole_form_and_unknown_slot_reject(self):
        g = CATALOG['profiles'][1]
        (body, ctx, _, _) = case(g)
        bad = copy.deepcopy(CATALOG)
        bad['profiles'].append(copy.deepcopy(g))
        self.deny(body, ctx, bad)
        bad = copy.deepcopy(CATALOG)
        target = next((x for x in bad['profiles'] if x['profile'] == g['profile']))
        token = next((x for x in target['tokens'] if 'slot' in x))
        token['slot']['type'] = 'OPAQUE_PROSE'
        self.deny(body, ctx, bad)

    def test_body_bounds_and_canonical_path(self):
        (body, ctx, _, _) = case(CATALOG['profiles'][1])
        self.deny(b'x' * 262145, ctx)
        self.deny(body, replace(ctx, report_ref='../report.log'))
        self.deny(body, replace(ctx, report_ref='/private/tmp/report.log'))
        self.deny(body, replace(ctx, bindings={'unknown': 'a' * 40}))

    def test_each_numeric_type_rejects_invalid_and_boolean_text(self):
        for (kind, value) in [('POSITIVE_COUNT_CLAIM', '0'), ('COUNTER_CLAIM', '1000001'), ('PERCENT_CLAIM', '101'), ('DURATION_CLAIM', 'NaN'), ('DURATION_CLAIM', '1e3'), ('VERSION_CLAIM', '1.1000001'), ('CLOCK_SUBMINUTE_CLAIM', '60'), ('EXPLICIT_ZERO_EXIT_CLAIM', '1'), ('DATE_CLAIM', '2026-02-30'), ('COUNTER_CLAIM', 'True')]:
            self.assertFalse(typed({'type': kind, 'max_bytes': CAPS[kind]}, value))

class LineageDefinitions(unittest.TestCase):

    def gap_case(self):
        return case(next((g for g in CATALOG['profiles'] if g['decision'] == 'D1_MISSING_ORIGINAL_GENERAL')), True)

    def test_gap_all_additional_conjunctions_required(self):
        (body, ctx, _, _) = self.gap_case()
        for guard in GAP_GUARDS:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, guards=tuple((x for x in GAP_GUARDS if x != guard))))
        for guards in [GUARDS, (), GAP_GUARDS + ('unknown',)]:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, guards=guards))

    def test_gap_missing_raw_unknown_or_source_substitution_rejects(self):
        (body, ctx, _, _) = self.gap_case()
        gap = ctx.lineage_gap
        for value in [None, dict(gap.__dict__), {'source_head': 'f' * 40}, True]:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, lineage_gap=value))
        for field in ['B', 'T', 'M', 'C']:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, lineage_gap=replace(gap, **{field: 'f' * 40})))
        with self.assertRaises(Denied):
            observe(CATALOG, ROLES, body, replace(ctx, original_delivery='f' * 40))

    def test_gap_requires_exact_failed_ancestry_not_equivalence_or_unknown(self):
        (body, ctx, _, _) = self.gap_case()
        gap = ctx.lineage_gap
        for value in [0, True, False, 2, 128, None, '1', -1]:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, lineage_gap=replace(gap, observed_ancestry_exit=value)))
        with self.assertRaises(Denied):
            observe(CATALOG, ROLES, body, replace(ctx, original_delivery=ctx.T, lineage_gap=replace(gap, M=ctx.T)))

    def test_gap_named_objects_and_parent_tree_metadata_are_finite(self):
        (body, ctx, _, _) = self.gap_case()
        gap = ctx.lineage_gap
        for field in ['tested_tree', 'delivery_tree']:
            for value in ['', 'x' * 40, 'a' * 39, True]:
                with self.assertRaises(Denied):
                    observe(CATALOG, ROLES, body, replace(ctx, lineage_gap=replace(gap, **{field: value})))
        for field in ['tested_parents', 'delivery_parents']:
            for value in [[], ('x' * 40,), ('a' * 40, 'a' * 40), tuple((format(i, '040x') for i in range(65))), True]:
                with self.assertRaises(Denied):
                    observe(CATALOG, ROLES, body, replace(ctx, lineage_gap=replace(gap, **{field: value})))

    def test_gap_cannot_waive_native_exact_zero_lineage(self):
        (body, ctx, _, _) = self.gap_case()
        states = list(ctx.parent_states)
        states[0] = 'OBSERVED_EXACT_ZERO'
        with self.assertRaises(Denied):
            observe(CATALOG, ROLES, body, replace(ctx, parent_states=tuple(states)))

    def test_gap_category_is_owner_neutral_and_not_missing_review_only(self):
        g = next((g for g in CATALOG['profiles'] if not g['decision']))
        (body, ctx, _, _) = case(g, True)
        gap = LineageObservation(ctx.B, ctx.T, '8' * 40, ctx.C, '6' * 40, '7' * 40, ('5' * 40,), ('4' * 40,), 1)
        r = observe(CATALOG, ROLES, body, replace(ctx, guards=GAP_GUARDS, original_delivery=gap.M, lineage_gap=gap))
        self.assertEqual(r['lineage_gap_count'], len(ctx.checks))
        self.assertTrue(all(('MISSING_ORIGINAL_REVIEW' not in e['limitations'] for e in r['entries'])))

    def test_gap_exact_visible_tuple_counts_and_zero_false_counts_reject(self):
        (body, ctx, _, _) = self.gap_case()
        r = observe(CATALOG, ROLES, body, ctx)
        mandatory = tuple(r['covered_tuples'])
        n = len(r['entries'])
        self.assertEqual(inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[r])['lineage_gap_count'], n)
        for value in [0, True, None, n + 1, -1]:
            bad = copy.deepcopy(r)
            bad['lineage_gap_count'] = value
            with self.assertRaises(Denied):
                inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[bad])
        for (field, value) in [('tested_delivery_ancestor', True), ('observed_ancestry_exit', 0), ('equivalence_certified', True), ('T', 'f' * 40)]:
            bad = copy.deepcopy(r)
            bad['entries'][0]['delivery_lineage'][field] = value
            with self.assertRaises(Denied):
                inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[bad])
        bad = copy.deepcopy(r)
        bad['entries'][0]['limitations'].remove(LINEAGE_LIMIT)
        with self.assertRaises(Denied):
            inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[bad])
        bad = copy.deepcopy(r)
        bad['entries'][0]['delivery_lineage'] = None
        with self.assertRaises(Denied):
            inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[bad])
        bad = copy.deepcopy(r)
        bad['lineage_gap_count'] = 0
        for e in bad['entries']:
            e['limitations'].remove(LINEAGE_LIMIT)
            e['delivery_lineage'] = None
        with self.assertRaises(Denied):
            inventory(((body, ctx),), n, mandatory, True, mandatory, candidate_outputs=[bad])
        with self.assertRaises(Denied):
            inventory(((body, ctx),), n, mandatory, True, (), candidate_outputs=[r])
        for altered in [mandatory[1:], mandatory + (('missing',),)]:
            with self.assertRaises(Denied):
                inventory(((body, ctx),), n, altered, True, mandatory, candidate_outputs=[r])

    def test_complete_39_ref_fixture_inventory_exposes_all_gap_tuples(self):
        results = []
        observation_inputs = []
        for g in CATALOG['profiles']:
            (body, ctx, _, _) = case(g)
            observation_inputs.append((body, ctx))
            results.append(observe(CATALOG, ROLES, body, ctx))
        for row in [x for x in ROWS['rows'] if x['disposition'] == 'KEEP_NATIVE_CAPTURE_PATH']:
            tuples = [(row['owner'], x['check_id'], row['original_B'], row['record_T'], x['command'], row['ref'], ROWS['authority_revision']) for x in row['checks']]
            results.append({'profile': 'NATIVE_CAPTURE_PATH', 'component_claims': [], 'native_ordinals': list(range(len(tuples))), 'review_acceptance_certified': False, 'entries': [], 'covered_tuples': tuples, 'documentary_unverified_count': 0, 'lineage_gap_count': 0, 'acceptance_eligible': False})
        mandatory = tuple((x for r in results for x in r['covered_tuples']))
        n = sum((len(r['entries']) for r in results))
        gap_tuples = tuple((e['entry'] for x in results if x['lineage_gap_count'] for e in x['entries']))
        native_tuples = tuple((t for x in results if x['profile'] == 'NATIVE_CAPTURE_PATH' for t in x['covered_tuples']))
        r = inventory(tuple(observation_inputs), n, mandatory, True, gap_tuples, native_tuples, candidate_outputs=results)
        self.assertEqual(r['lineage_gap_count'], sum((len(x['entries']) for x in results if x['lineage_gap_count'])))
        self.assertGreater(r['lineage_gap_count'], 0)
        self.assertIs(r['acceptance_eligible'], False)
for profile in CATALOG['profiles']:

    def syntax(self, g=profile):
        (body, ctx, row, _) = case(g)
        self.assertEqual(hashlib.sha256(body).hexdigest(), row['report_identity']['sha256'])
        actual = next((x for x in BINDINGS['rows'] if x['row'] == row['row']))
        r = observe(CATALOG, ROLES, body, ctx)
        self.assertEqual(r['profile'], g['profile'])
        self.assertFalse(r['acceptance_eligible'])

    def neutral(self, g=profile):
        (body, ctx, _, _) = case(g, True)
        r = observe(CATALOG, ROLES, body, ctx)
        self.assertEqual(r['profile'], g['profile'])
        self.assertTrue(all((e['acceptance_eligible'] is False for e in r['entries'])))

    def malformed(self, g=profile):
        (body, ctx, _, _) = case(g)
        for mutated in [b'unknown\n' + body, body + b'extra\n', body.replace(b'\n', b'\r\n', 1), b'\xff' + body, b'\x00' + body, b'\xef\xbb\xbf' + body]:
            self.deny(mutated, ctx)

    def guards(self, g=profile):
        (body, ctx, _, _) = case(g)
        for guard in GUARDS:
            self.deny(body, replace(ctx, guards=tuple((x for x in GUARDS if x != guard))))

    def caller(self, g=profile):
        (body, ctx, _, _) = case(g)
        for purpose in ['SELECTED_CHECK', 'PREREQUISITE', 'REVIEW', 'FULL_RRO', 'EXECUTION', 'SOURCE_INSPECTION', 'DECODER', 'STORAGE', 'HISTORY', 'M3', 'REQUIREMENT', 'INSTALLATION', 'ADMISSION', 'APP', 'RELEASE']:
            self.deny(body, replace(ctx, caller=purpose))
        self.deny(body, replace(ctx, selected_owner=True))
        self.deny(body, replace(ctx, fresh_self_archival=True))
        for cache in ['execution', 'source', 'decoder', 'storage', 'RRO', 'selected']:
            self.deny(body, replace(ctx, cache_role=cache))

    def contradictions(self, g=profile):
        (body, ctx, _, _) = case(g)
        for state in ['NONZERO', 'FAILED', 'ERROR', 'SKIPPED', 'INTERRUPTED', 'UNSTARTED', 'INCOMPLETE', 'UNKNOWN_EXIT_WITH_PARTIAL_OUTPUT']:
            states = list(ctx.parent_states)
            states[0] = state
            self.deny(body, replace(ctx, parent_states=tuple(states)))
    for (label, fn) in [('exact_original_byte_shape_and_known_binding_disposition', syntax), ('owner_command_root_revision_neutral', neutral), ('malformed_whole_report', malformed), ('all_independent_guards', guards), ('caller_and_cache_isolation', caller), ('native_parent_contradictions', contradictions)]:
        setattr(Definitions, 'test_' + profile['profile'].lower() + '_' + label, fn)

class RelationMutations(unittest.TestCase):

    def test_every_enumerated_relation_denies_a_bounded_counterexample(self):
        tested = 0
        for g in CATALOG['profiles']:
            (body, ctx, _, values) = case(g)
            for rel in g['claim_relations']:
                altered = dict(values)
                kind = rel['kind']
                if kind.startswith('same_'):
                    alias = rel['equals'][0]
                    altered[alias] = str(int(altered[alias]) + 1)
                elif kind == 'progress_sum':
                    alias = rel['parts'][0]
                    altered[alias] += '.'
                elif kind == 'progress_percent':
                    alias = rel['percentages'][0]
                    altered[alias] = str((int(altered[alias]) + 1) % 101)
                elif kind == 'collection_total':
                    alias = rel['collected']
                    altered[alias] = str(int(altered[alias]) + 1)
                elif kind == 'elapsed_clock':
                    alias = rel['seconds']
                    altered[alias] = str(Decimal(altered[alias]) + 1)
                elif kind == 'active_not_more_than_tasks':
                    alias = rel['active']
                    altered[alias] = str(int(altered[rel['tasks']]) + 1)
                elif kind == 'decreased_count':
                    alias = rel['before']
                    altered[alias] = altered[rel['after']]
                elif kind == 'not_record_T':
                    alias = rel['aliases'][0]
                    altered[alias] = ctx.T
                elif kind == 'positive_claim':
                    alias = rel['aliases'][0]
                    altered[alias] = '0'
                else:
                    self.fail('Uncovered relation ' + kind)
                mutated = ''.join((t['literal'] if 'literal' in t else altered[t['slot']['alias']] for t in g['tokens'])).encode()
                with self.assertRaises(Denied, msg=g['profile'] + ':' + kind):
                    observe(CATALOG, ROLES, mutated, ctx)
                tested += 1
        self.assertEqual(tested, sum((len(g['claim_relations']) for g in CATALOG['profiles'])))

    def test_composite_original_description_cannot_be_replaced_by_executable_command(self):
        g = next((g for g in CATALOG['profiles'] if g['decision'] == 'D4_COMPOSITE_WITH_INCOMPLETE_COMPONENT'))
        (body, ctx, _, _) = case(g)
        checks = list(ctx.checks)
        n = ctx.parent_states.index('EXPLICIT_NON_EXECUTION_COMPOSITE')
        checks[n] = (checks[n][0], 'python3 executable.py')
        with self.assertRaises(Denied):
            observe(CATALOG, ROLES, body, replace(ctx, checks=tuple(checks)))
        result = observe(CATALOG, ROLES, body, ctx)
        component = next((x for x in result['component_claims'] if x['state'] == 'INCOMPLETE'))
        self.assertEqual(component['revision'], 'UNSPECIFIED_IN_ORIGINAL_REPORT')
        self.assertGreater(component['stopped'], 0)

    def test_definition_JSON_duplicate_nonfinite_and_depth_exhaustion_reject(self):
        from definition_data import strict_json
        for value in [b'{"a":1,"a":2}', b'{"a":NaN}', b'[' * 65 + b'0' + b']' * 65, b'\xff']:
            with self.assertRaises(Denied):
                strict_json(value)

    def test_native_grammar_work_exhaustion_remains_denial(self):
        b = Budget()
        with self.assertRaises(Denied):
            b.use(1048577)
        b = Budget()
        b.nodes = 262144
        with self.assertRaises(Denied):
            b.use()

    def test_context_boolean_integer_aliases_reject(self):
        (body, ctx, _, _) = case(CATALOG['profiles'][1])
        for field in ['original_general_required', 'absence_proof', 'selected_owner', 'fresh_self_archival', 'composite_declared_non_execution']:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body, replace(ctx, **{field: 1}))
if __name__ == '__main__':
    unittest.main(verbosity=2)
