"""Independent represented-prose/schema/partition coverage for R1 findings."""
import unittest, copy, re, json, hashlib
from pathlib import Path
from functools import partial
from dataclasses import replace
from fixture_support import *
from definition_oracle import observe, inventory as raw_inventory, Denied
from definition_schema import RELATIONS, DIMENSIONS, profile_relations, entry_tuple
inventory = partial(raw_inventory, output_types=OUTPUT, roles=ROLES, catalog=CATALOG)

def render(g, values):
    return ''.join((t['literal'] if 'literal' in t else values[t['slot']['alias']] for t in g['tokens'])).encode()

def neutral(name):
    return case(next((g for g in CATALOG['profiles'] if g['profile'] == name)), True)

class Corrections(unittest.TestCase):

    def test_transcribed_exit_zero_is_not_nonzero_unknown_or_boolean_claim(self):
        g = CATALOG['profiles'][27]
        (body, ctx, _, vals) = case(g, True)
        self.assertEqual(observe(CATALOG, ROLES, body, ctx)['entries'][0]['exit_attribution']['value'], 0)
        for value in ['1', '130', '1000000', 'unknown', 'True', '-1', '00', '0.0', '']:
            changed = dict(vals, v16=value)
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, render(g, changed), ctx)

    def test_source_suite_zero_counts_reject_and_three_source_phase_roles_visible(self):
        g = CATALOG['profiles'][27]
        (body, ctx, _, vals) = case(g, True)
        for alias in ['v7', 'v9', 'v11']:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, render(g, dict(vals, **{alias: '0'})), ctx)
        role = ROLES['profiles'][27]
        self.assertEqual({x['terminal_alias'] for x in role['phases']}, {'v7', 'v9', 'v11'})
        self.assertTrue(all((x['revision_binding'] == 'SOURCE_T' for x in role['phases'])))

    def test_fixed_authority_section_algorithm_and_contract_identifier_literals(self):
        for (name, old, new) in [('PLAIN_LITERAL_01', b'DB section 3', b'DB section 999'), ('PLAIN_LITERAL_01', b'DB section 11', b'DB section 888'), ('PLAIN_LITERAL_17', b'SHA-256', b'SHA-1'), ('PLAIN_LITERAL_18', b'SHA-256', b'SHA-1'), ('PLAIN_LITERAL_07', b'KL-014/015/016', b'KL-014/999/016')]:
            (body, ctx, _, _) = neutral(name)
            self.assertIn(old, body)
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, body.replace(old, new), ctx)

    def test_harness_equal_ratio_still_must_match_its_terminal(self):
        for (index, aliases) in [(7, ['v25', 'v26']), (8, ['v21', 'v22'])]:
            g = CATALOG['profiles'][index]
            (_, ctx, _, v) = case(g, True)
            for count in ['1', '999']:
                with self.assertRaises(Denied):
                    observe(CATALOG, ROLES, render(g, dict(v, **{a: count for a in aliases})), ctx)

    def test_all33_prose_independently_defines_each_phase_ratio_zero_and_constant_role(self):
        observed_phases = 0
        for g in CATALOG['profiles']:
            (body, ctx, _, vals) = case(g)
            raw = body.decode()
            at = {}
            offset = 0
            for t in g['tokens']:
                value = t['literal'] if 'literal' in t else vals[t['slot']['alias']]
                if 'slot' in t:
                    at[offset] = t['slot']
                offset += len(value)
            role = next((r for r in ROLES['profiles'] if r['profile'] == g['profile']))
            phases = {x['terminal_alias'] for x in role['phases']}
            found = set()
            for pattern in ['(?<![A-Za-z0-9_])(\\d+) passed(?=[, .\\n]|$)', '(\\d+) (?:harness|unit|database) tests passed']:
                for m in re.finditer(pattern, raw):
                    self.assertIn(m.start(1), at)
                    slot = at[m.start(1)]
                    self.assertEqual(slot['type'], 'POSITIVE_COUNT_CLAIM')
                    self.assertIn(slot['alias'], phases)
                    found.add(slot['alias'])
            self.assertEqual(found, phases)
            observed_phases += len(found)
            for m in re.finditer('(?i)(?:exit(?:ed)?[: ]+)(\\d+)', raw):
                self.assertIn(m.start(1), at)
                self.assertEqual(at[m.start(1)]['type'], 'EXPLICIT_ZERO_EXIT_CLAIM')
            for pattern in ['SHA-(\\d+)', 'DB section (\\d+)']:
                for m in re.finditer(pattern, raw):
                    self.assertNotIn(m.start(1), at)
            for m in re.finditer('tasks=(\\d+) active=(\\d+)', raw):
                self.assertIn({'kind': 'active_not_more_than_tasks', 'tasks': at[m.start(1)]['alias'], 'active': at[m.start(2)]['alias']}, g['claim_relations'])
            for m in re.finditer('(\\d+)/(\\d+) PASS result', raw):
                terminal = list(re.finditer('Harness suite: (\\d+) passed', raw[:m.start()]))[-1]
                wanted = {at[terminal.start(1)]['alias'], at[m.start(1)]['alias'], at[m.start(2)]['alias']}
                self.assertTrue(any((rel['kind'].startswith('same_') and set(rel['equals']) >= wanted for rel in g['claim_relations'])))
        self.assertEqual(observed_phases, 76)

    def test_all_present_relation_schemas_closed_and_unknown_properties_types_denied(self):
        for g in CATALOG['profiles']:
            profile_relations(g)
            for (n, relation) in enumerate(g['claim_relations']):
                for mutation in ['extra', 'missing', 'bool', 'wrongrole']:
                    bad = copy.deepcopy(g)
                    rel = bad['claim_relations'][n]
                    if mutation == 'extra':
                        rel['unrecognized'] = True
                    elif mutation == 'missing':
                        rel.pop(next((k for k in rel if k != 'kind')))
                    elif mutation == 'bool':
                        rel[next((k for k in rel if k != 'kind'))] = True
                    else:
                        rel[next((k for k in rel if k != 'kind'))] = 'missing_alias'
                    with self.assertRaises(Denied):
                        profile_relations(bad)

    def test_cross_document_dimensions_relations_vocab_roles_and_execution_are_consistent(self):
        self.assertEqual(GRAMMAR['noncertification'], [v if k != 'acceptance_eligible' else 'acceptance_eligible=false' for (k, v) in DIMENSIONS.items()])
        self.assertEqual(OUTPUT['mandatory_dimensions'], {k: [v] for (k, v) in DIMENSIONS.items()})
        self.assertEqual(GRAMMAR['relations']['closed_vocabulary'], RELATIONS)
        from definition_oracle import PATTERNS, CAPS
        self.assertEqual(set(GRAMMAR['slot_types']), set(PATTERNS))
        self.assertEqual(set(CAPS), set(PATTERNS))
        self.assertEqual({rel['kind'] for g in CATALOG['profiles'] for rel in g['claim_relations']}, set(RELATIONS))
        for (g, role) in zip(CATALOG['profiles'], ROLES['profiles']):
            self.assertEqual(g['profile'], role['profile'])
            self.assertEqual(len(g['tokens']), len(role['token_roles']))
            self.assertEqual([x['ordinal'] for x in role['check_claims']], list(range(g['record_check_shape']['ordered_report_ref_check_count'])))
            self.assertTrue(all((q['purpose'] in OUTPUT['purpose_enums'] and all((v in OUTPUT['limitation_enums'] for v in q['limitations'])) for q in role['check_claims'])))
            (body, ctx, _, _) = case(g, True)
            r = observe(CATALOG, ROLES, body, ctx)
            for e in r['entries']:
                for (k, v) in DIMENSIONS.items():
                    self.assertIs(type(e[k]), type(v))
                    self.assertEqual(e[k], v)

    def ordinary(self):
        (body, ctx, _, _) = neutral('PLAIN_LITERAL_02')
        r = observe(CATALOG, ROLES, body, ctx)
        return (r, tuple(r['covered_tuples']), ((body, ctx),))

    def denied_output(self, fn):
        (r, mandatory, observations) = self.ordinary()
        bad = copy.deepcopy(r)
        fn(bad)
        with self.assertRaises(Denied):
            inventory(observations, len(bad['entries']), mandatory, True, candidate_outputs=[bad])

    def test_ordinary_omitted_substituted_extra_duplicate_false_zero_entries_reject(self):
        for fn in [lambda r: r.update(entries=[], documentary_unverified_count=0), lambda r: r['entries'].pop(), lambda r: r['entries'][0].update(entry=('fake',) * 7), lambda r: r['entries'].append(copy.deepcopy(r['entries'][0])), lambda r: r.update(documentary_unverified_count=0)]:
            self.denied_output(fn)

    def test_each_dimension_certification_enum_and_boolean_type_alteration_rejects(self):
        for (key, value) in DIMENSIONS.items():
            for bad in ['VERIFIED', True, 0, None, 'UNKNOWN']:
                if type(bad) is type(value) and bad == value:
                    continue
                self.denied_output(lambda r, k=key, v=bad: r['entries'][0].update({k: v}))

    def test_unknown_keys_missing_limits_wrong_purpose_and_revision_fields_reject(self):
        for fn in [lambda r: r.update(unrecognized_approval=True), lambda r: r['entries'][0].update(extra=True), lambda r: r['entries'][0].pop('historical_execution'), lambda r: r['entries'][0]['limitations'].pop(), lambda r: r['entries'][0]['limitations'].append('NEW_PERMISSION'), lambda r: r['entries'][0].update(purpose='FINAL_REVISION_EXIT_ATTRIBUTION'), lambda r: r['entries'][0].update(revision_claims={'unrecognized': 'a' * 40}), lambda r: r['entries'][0].update(exit_attribution={'value': 0})]:
            self.denied_output(fn)

    def test_fabricated_native_coverage_cannot_replace_documentary_entries(self):
        (r, mandatory, observations) = self.ordinary()
        bad = copy.deepcopy(r)
        bad.update(entries=[], documentary_unverified_count=0, native_ordinals=list(range(len(mandatory))))
        with self.assertRaises(Denied):
            inventory(observations, 0, mandatory, True, candidate_outputs=[bad])
        r['native_ordinals'] = [True]
        with self.assertRaises(Denied):
            inventory(observations, len(r['entries']), mandatory, True, candidate_outputs=[r])

    def test_native_partition_positive_and_required_native_omission_and_extra_deny(self):
        (body, ctx, _, _) = neutral('PLAIN_LITERAL_02')
        states = list(ctx.parent_states)
        states[0] = 'OBSERVED_EXACT_ZERO'
        ctx = replace(ctx, parent_states=tuple(states))
        r = observe(CATALOG, ROLES, body, ctx)
        mandatory = tuple(r['covered_tuples'])
        native = (mandatory[0],)
        self.assertEqual(inventory(((body, ctx),), len(r['entries']), mandatory, True, (), native, candidate_outputs=[r])['documentary_unverified_count'], len(mandatory) - 1)
        for native_set in [(), mandatory, native + (native[0],)]:
            with self.assertRaises(Denied):
                inventory(((body, ctx),), len(r['entries']), mandatory, True, (), native_set, candidate_outputs=[r])

    def test_known_exit_output_integer_zero_producer_and_unknown_keys_are_exact(self):
        (body, ctx, _, _) = neutral('PLAIN_LITERAL_28')
        r = observe(CATALOG, ROLES, body, ctx)
        mandatory = tuple(r['covered_tuples'])
        for (field, value) in [('value', 1), ('value', False), ('producer', 'a' * 40), ('kind', 'VERIFIED_EXIT'), ('execution_certified', True), ('unknown', True)]:
            bad = copy.deepcopy(r)
            bad['entries'][0]['exit_attribution'][field] = value
            with self.assertRaises(Denied):
                inventory(((body, ctx),), len(bad['entries']), mandatory, True, candidate_outputs=[bad])

    def test_lossless_packaging_keeps_exact_source_pin_decoded_values_and_plain_caps(self):
        m = read('BINDING_PACKAGE.json')
        # Portable delivery binds the exact original source pin plus canonical decoded identity.
        self.assertEqual(m['source']['sha256'], 'e102d0931a34567cdd44b8910927750e364c9e85f4ebf6c78177332daddb9b47')
        canonical = json.dumps(BINDINGS, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), m['decoded_canonical_sha256'])
        self.assertEqual(len(BINDINGS['rows']), 39)
        self.assertTrue(all(((ROOT / x['path']).stat().st_size <= 262144 for x in m['ordered_rows'])))
        self.assertGreater(m['source']['bytes'], 262144)
        self.assertEqual(m['plain_artifact_cap'], 262144)
        self.assertEqual(m['reader_other_blob_cap'], 1048576)

    def test_inert_host_and_port_have_distinct_finite_roles(self):
        g = CATALOG['profiles'][16]
        (_, ctx, _, v) = case(g, True)
        for (alias, value) in [('v48', '127.256.0.1'), ('v48', '1.2'), ('v49', '65536'), ('v49', '0')]:
            with self.assertRaises(Denied):
                observe(CATALOG, ROLES, render(g, dict(v, **{alias: value})), ctx)
if __name__ == '__main__':
    unittest.main(verbosity=2)
