"""Cross-save regressions exposed by the 1337 rebuild."""
import unittest
from m3_world import assign_country_tags
from opening_wars import render,PREFIX,PLAYS,HISTORY,validate_seed_removals,initial_war_goals
from border_war_goals import candidates
from pdx_text import root

class FreshSaveTests(unittest.TestCase):
 def test_country_namespace_spills_without_using_native_or_reviewed_tags(self):
  source={str(i):{'tag':'SRC'+str(i)} for i in range(1800)}
  native={'E00':{},'ECU':{},'ENG':{}}
  matches={'1799':{'source_tag':'SRC1799','target_tag':'ENG'}}
  result=assign_country_tags(source,set(source),native,matches,{})
  self.assertEqual(len(result),len(set(result.values())))
  self.assertTrue(all(len(t)==3 for t in result.values()))
  self.assertEqual(result['1799'],'ENG')
  self.assertFalse(set(result.values())&{'E00','ECU'})
  self.assertEqual(result,assign_country_tags(source,set(reversed(list(source))),native,matches,{}))
 def test_civil_war_keeps_native_mutual_annexation(self):
  row={'id':'0','attacker':'AAA','target':'BBB','leader_target':'BBB','attackers':['AAA'],'defenders':['BBB'],'goal':'annex_country','native_play':'dp_revolution','civil_war_bridge':True,'play_type':PREFIX+'0'}
  native={'dp_revolution':root('war_goal = annex_country mirror_war_goal = yes possible = { is_revolutionary = yes } selectable_in_lens = { always = no }')}
  scripts=render([row],native);output=scripts[PLAYS]
  self.assertIn('mirror_war_goal = yes',output)
  self.assertIn('possible = { always = yes }',output)
  self.assertNotIn('is_revolutionary',output)
  self.assertNotIn('remove_war_goal',scripts[HISTORY])
  self.assertEqual(initial_war_goals(row,native['dp_revolution']),{'initiator':'annex_country','target':'annex_country'})
  with self.assertRaisesRegex(ValueError,'Absent/repeated'):
   validate_seed_removals(row,'remove_war_goal = { who = target type = humiliation }',native['dp_revolution'])
  candidates([row],{}, {},{}, {},[],30)
  self.assertNotIn('candidates',row)

class EmptyTerrainTests(unittest.TestCase):
 def test_attachment_uses_residents_in_same_state(self):
  from types import SimpleNamespace
  from empty_native_attachments import attach
  w=SimpleNamespace(mapping={'a':['ref'],'b':['local'],'c':[]},province_state={'a':'S1','b':'S2','c':'S2'},owners={'S1':{'a':'AAA'},'S2':{'b':'BBB','c':'CCC'}},countries={'AAA':{'culture':'x'},'BBB':{'culture':'y'},'CCC':{'culture':'y','generated_uncolonized':True}},distance=lambda a,b:1)
  decisions=attach(w,{'provinces':{'c':{'root':'c'}}},{'c':{'source_locations':['ref']}},{'ref':{'x':100},'local':{'y':100}},{})
  self.assertEqual(w.owners['S2']['c'],'BBB')
  self.assertNotIn('CCC',w.countries)
  self.assertEqual(decisions[0]['state_owner_corrections'][0]['population_transferred'],0)
 def test_template_exception_skips_populated_state_and_blocks_unreviewed_empty(self):
  from types import SimpleNamespace
  from fresh_empty_state_templates import apply_ownership
  w=SimpleNamespace(mapping={'a':['source']},province_state={'a':'S'},owners={'S':{'a':'AAA'}},countries={},country_defs={})
  self.assertEqual(apply_ownership(w,{'source':{'c':100}},{},{'empty_state_templates':{'S':'NRU'}}),{})
  self.assertEqual(w.owners['S']['a'],'AAA')
  with self.assertRaises(ValueError):apply_ownership(w,{}, {},{'empty_state_templates':{}})
 def test_template_population_rejects_source_overlap_and_split_state(self):
  from fresh_empty_state_templates import template_groups
  from pathlib import Path
  with self.assertRaisesRegex(ValueError,'overlaps'):template_groups(Path('.'),{'S':'AAA'},{('S','AAA','c','r'):1},{'S':{'a':'AAA'}})
  with self.assertRaisesRegex(ValueError,'split'):template_groups(Path('.'),{'S':'AAA'},{},{'S':{'a':'AAA','b':'BBB'}})

class SupervisedReviewTests(unittest.TestCase):
 def test_rounding_keeps_positive_state_parts_without_creating_people(self):
  from population_state_rounding import preserve_populated_parts
  from m4_demographics import round_groups
  exact={('A','AAA','x','r'):20,('B','BBB','x','r'):33,('C','CCC','x','r'):250}
  before=round_groups(exact);after,changes=preserve_populated_parts(exact,before)
  self.assertEqual(sum(before.values()),sum(after.values()))
  self.assertTrue(all(n>=1 for n in after.values()))
  self.assertTrue(changes)
 def test_acre_joins_adjacent_same_culture_country(self):
  from types import SimpleNamespace
  from fresh_empty_state_templates import apply_ownership
  w=SimpleNamespace(mapping={'a':[],'b':['inhabited']},province_state={'a':'ACRE','b':'NEXT'},owners={'ACRE':{'a':'OLD'},'NEXT':{'b':'NAT'}},countries={'OLD':{'generated_uncolonized':True,'culture':'other'},'NAT':{'generated_uncolonized':True,'culture':'amazonian'}},country_defs={'AMZ':root('cultures = { amazonian }')})
  chosen=apply_ownership(w,{'inhabited':{'a':100}},{},{'empty_state_templates':{'ACRE':'AMZ'},'empty_state_owner_modes':{'ACRE':'join_adjacent_same_template_culture'}},[('a','b')])
  self.assertEqual(chosen,{'ACRE':'NAT'});self.assertEqual(w.owners['ACRE']['a'],'NAT');self.assertNotIn('AMZ',w.countries)
 def test_comment_template_is_explicitly_distinguished_from_active_population(self):
  import tempfile
  from pathlib import Path
  from fresh_empty_state_templates import island_template_people
  with tempfile.TemporaryDirectory() as tmp:
   game=Path(tmp);(game/'pops.txt').write_text('POPS = { s:S = { region_state:JAP = { create_pop = { size = 5000000 } }\n # region_state:MCR = {\n # create_pop = { size = 26 }\n # }\n } }',encoding='utf-8')
   result=island_template_people(game,{'island_population_templates':{'x1':{'population_reference_file':'pops.txt','state':'S','commented_template_owner':'MCR'}}})
   self.assertEqual(result['x1']['persons'],26);self.assertFalse(result['x1']['reference_active_in_vanilla'])

if __name__=='__main__':unittest.main()
