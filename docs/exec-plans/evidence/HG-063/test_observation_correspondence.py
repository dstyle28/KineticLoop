"""R2 review reproductions with authoritative fixture inputs unchanged."""
import copy,unittest
from dataclasses import replace
from functools import partial
from fixture_support import *
from definition_oracle import observe,inventory as raw_inventory,Denied,typed,CAPS
inventory=partial(raw_inventory,catalog=CATALOG,roles=ROLES,output_types=OUTPUT)
def source(name):return case(next(g for g in CATALOG['profiles'] if g['profile']==name),True)
class Correspondence(unittest.TestCase):
 def run_case(self,name,mutation,native_ordinal=None):
  body,ctx,_,_=source(name)
  if native_ordinal is not None:
   states=list(ctx.parent_states);states[native_ordinal]='OBSERVED_EXACT_ZERO';ctx=replace(ctx,parent_states=tuple(states))
  original=observe(CATALOG,ROLES,body,ctx);mandatory=tuple(original['covered_tuples']);native=tuple(mandatory[n] for n in original['native_ordinals']);gap=tuple(e['entry'] for e in original['entries'] if e['delivery_lineage'] is not None)
  good=inventory(((body,ctx),),len(original['entries']),mandatory,True,gap,native,candidate_outputs=[original]);self.assertEqual(good['observations'],[original])
  bad=copy.deepcopy(original);mutation(bad)
  self.assertNotEqual(bad,original)
  with self.assertRaisesRegex(Denied,'output-does-not-correspond-to-original-observation'):inventory(((body,ctx),),len(bad['entries']),mandatory,True,gap,native,candidate_outputs=[bad])
 def test_D5_coordinated_covered_and_entry_identity_permutation_rejects(self):
  def change(r):
   r['covered_tuples'][0],r['covered_tuples'][1]=r['covered_tuples'][1],r['covered_tuples'][0]
   r['entries'][0]['entry'],r['entries'][1]['entry']=r['entries'][1]['entry'],r['entries'][0]['entry']
  self.run_case('PLAIN_LITERAL_28',change)
 def test_D4_composite_and_ordinary_command_coordinated_swap_rejects(self):
  def change(r):
   n=next(i for i,e in enumerate(r['entries']) if e['purpose']=='EXPLICIT_NON_EXECUTION_COMPOSITE')
   r['covered_tuples'][0],r['covered_tuples'][n]=r['covered_tuples'][n],r['covered_tuples'][0]
   r['entries'][0]['entry'],r['entries'][n]['entry']=r['entries'][n]['entry'],r['entries'][0]['entry']
  self.run_case('PLAIN_LITERAL_24',change)
 def test_mixed_native_documentary_coordinated_ordinal_swap_rejects(self):
  def change(r):
   r['covered_tuples'][0],r['covered_tuples'][1]=r['covered_tuples'][1],r['covered_tuples'][0];r['native_ordinals']=[1]
  self.run_case('PLAIN_LITERAL_02',change,native_ordinal=0)
 def test_full_output_entry_and_tuple_reorder_preserving_sets_still_rejects(self):
  def change(r):r['covered_tuples'].reverse();r['entries'].reverse()
  self.run_case('PLAIN_LITERAL_28',change)
 def test_welltyped_SOURCE_T_substitution_in_every_entry_rejects(self):
  def change(r):
   for e in r['entries']:e['revision_claims']['SOURCE_T']='1'*40
  self.run_case('PLAIN_LITERAL_28',change)
 def test_welltyped_distinct_REPORT_T_substitution_rejects(self):
  g=next(g for g in CATALOG['profiles'] if any('slot' in t and t['slot']['binding']=='REPORT_T' for t in g['tokens']))
  def change(r):
   for e in r['entries']:e['revision_claims']['REPORT_T']='1'*40
  self.run_case(g['profile'],change)
 def test_welltyped_producer_full_prefix_and_exit_substitution_rejects(self):
  def change(r):
   for e in r['entries']:
    e['revision_claims']['PRODUCER_Z']='1'*40;e['revision_claims']['PRODUCER_Z_PREFIX']='1'*7;e['exit_attribution']['producer']='1'*40
  self.run_case('PLAIN_LITERAL_20',change)
 def test_welltyped_positive_component_count_substitution_rejects(self):
  def change(r):
   for c in r['component_claims']:
    if 'passed' in c:c['passed']=999999
  self.run_case('PLAIN_LITERAL_24',change)
 def test_welltyped_original_delivery_and_tree_substitution_rejects(self):
  def change(r):
   for e in r['entries']:e['delivery_lineage']['original_delivery']='1'*40;e['delivery_lineage']['tested_tree']='2'*40
  self.run_case('PLAIN_LITERAL_01',change)
 def test_welltyped_actual_parent_metadata_substitution_rejects(self):
  def change(r):
   for e in r['entries']:e['delivery_lineage']['delivery_parents']=('1'*40,)
  self.run_case('PLAIN_LITERAL_01',change)
 def test_other_known_profile_cannot_replace_unique_parsed_profile(self):
  def change(r):
   n=len(r['covered_tuples']);r['profile']=next(g['profile'] for g in CATALOG['profiles'] if g['profile']!=r['profile'] and g['record_check_shape']['ordered_report_ref_check_count']==n)
  self.run_case('PLAIN_LITERAL_02',change)
 def test_outputs_alone_flags_dataclasses_and_wrong_original_input_shape_do_not_supply_binding(self):
  body,ctx,_,_=source('PLAIN_LITERAL_28');r=observe(CATALOG,ROLES,body,ctx);mandatory=tuple(r['covered_tuples'])
  for requests in [[r],(r,),({'verified':True,'result':r},),((body,{'trusted':True}),),((ctx,body),)]:
   with self.assertRaises(Denied):inventory(requests,len(r['entries']),mandatory,True,candidate_outputs=[r])
  # The source input has not been taken from result, hashes or a success token.
  self.assertEqual(inventory(((body,ctx),),len(r['entries']),mandatory,True)['observations'],[r])
 def test_exact_one_directory_slash_and_no_path_trailing_empty_components(self):
  for kind,good,bad in [('INERT_REPO_DIRECTORY_CLAIM','docs/example/',['docs/example//','docs//example/','docs/example','docs/example/./','docs/example/../']),('INERT_REPO_PATH_CLAIM','docs/example.txt',['docs/example.txt/','docs/example.txt//','docs//example.txt','docs/./example.txt','docs/../example.txt'])]:
   slot={'type':kind,'max_bytes':CAPS[kind]};self.assertTrue(typed(slot,good))
   for value in bad:self.assertFalse(typed(slot,value))
  g=CATALOG['profiles'][16];_,ctx,_,v=case(g,True)
  for value in ['docs/example//','docs/example///']:
   vv=dict(v,v59=value);body=''.join(t['literal'] if 'literal' in t else vv[t['slot']['alias']] for t in g['tokens']).encode()
   with self.assertRaises(Denied):observe(CATALOG,ROLES,body,ctx)
 def test_navigation_relation_label_matches_exact_current_catalog(self):
  matrix=read('DECISION_MATRIX.json');self.assertIn('exact_current_catalog_relation_counterexamples_denied',matrix['positive_cases']);self.assertFalse(any('all36_' in v for v in matrix['positive_cases']))
 def test_exact_output_correspondence_retains_builtin_types_and_rejects_cycles(self):
  from definition_oracle import exact_output_correspondence
  for value in [False,0.0,'0',None]:
   with self.assertRaises(Denied):exact_output_correspondence({'n':0},{'n':value})
  original={'v':[1]};cyclic=[];cyclic.append(cyclic)
  with self.assertRaises(Denied):exact_output_correspondence(original,{'v':cyclic})
 def test_exact_output_correspondence_existing_byte_and_depth_exhaustion_denies(self):
  from definition_oracle import exact_output_correspondence
  value={'text':'x'*524289}
  with self.assertRaises(Denied):exact_output_correspondence(value,value)
  deep=0
  for _ in range(65):deep=[deep]
  with self.assertRaises(Denied):exact_output_correspondence(deep,deep)
if __name__=='__main__':unittest.main(verbosity=2)
