import unittest
import tempfile
from pathlib import Path
from pdx_text import root
from extract_war_source import decode_locations,participant
from opening_wars import select_state,render,HISTORY,PREFIX,PLAYS,GOALS,initial_war_goals,validate_seed_removals
from extract_m3_politics import fields
from border_war_goals import candidates,allocation_script


class WarTests(unittest.TestCase):
    def test_membership_accepts_observers_but_rejects_extra_combatants(self):
        from opening_wars import valid_play
        row={'attacker':'AAA','leader_target':'BBB','attackers':['AAA','CCC'],
             'defenders':['BBB'],'goal':'conquer_state'}
        predicate=next(v for k,v in root(valid_play(row)).entries() if k=='NOT')
        def matches(obj, country, members):
            def check(key,value):
                if key=='OR':return any(check(k,v) for k,v in value.entries())
                if key=='NOT':return not matches(value,country,members)
                if key=='any_scope_play_involved':return any(matches(value,c,members) for c in members)
                if key=='this':return country[0]==value.removeprefix('c:')
                if key=='is_diplomatic_play_ally_of':return country[1]=='attacker'
                if key=='is_diplomatic_play_enemy_of':return country[1]=='defender'
                raise AssertionError(key)
            return all(check(k,v) for k,v in obj.entries())
        # This object is the rejected-extra-members predicate inside NOT.
        members=[('AAA','attacker'),('CCC','attacker'),('BBB','defender')]
        self.assertFalse(matches(predicate,None,members+[('ER2','neutral')]))
        self.assertTrue(matches(predicate,None,members+[('ER2','attacker')]))
        self.assertTrue(matches(predicate,None,members+[('ER2','defender')]))

    def test_named_aggression_is_explicit_approximation_not_unknown_fallback(self):
        from extract_war_source import extract
        from m3_world import digest
        from converter_source_wars import war_route
        member=lambda country,side:f'{{ country={country} status=Active all_history={{ {{ request={{ side={side} }} joined={{ date=1786.1.1 }} }} }} }}'
        text='locations={ locations={} } provinces={ database={} } war_manager={ database={ 1={ all={ '+member('1','Attacker')+member('2','Defender')+' } original_attacker=1 original_attacker_target=2 start_date=1786.1.1 war_name={ name=AGRESSION_WAR_NAME } } } }'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'save.eu5';p.write_text(text,encoding='utf8')
            war=extract(p,Path(td)/'wars.json',digest(p))['wars'][0]
            self.assertEqual(war['goals'][0]['kind'],'aggression');self.assertEqual(war_route(war),'humiliation_approximation')
            self.assertEqual(war['goals'][0]['location_ids'],[])
            p.write_text(text.replace('AGRESSION_WAR_NAME','UNKNOWN_WAR_NAME'),encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Unsupported number'):extract(p,Path(td)/'wars.json',digest(p))
    def test_mirrored_play_rule_applies_without_save_specific_civil_war_flag(self):
        row={'id':'custom','attacker':'AAA','target':'BBB','leader_target':'BBB','attackers':['AAA'],
             'defenders':['BBB'],'goal':'annex_country','native_play':'dp_custom','play_type':PREFIX+'custom'}
        native={'dp_custom':root('war_goal = annex_country mirror_war_goal = yes')}
        history=render([row],native)[HISTORY]
        self.assertNotIn('remove_war_goal',history)
        self.assertIn('set_war = yes',history)

    def test_seed_removals_reject_wrong_side_and_duplicate_with_valid_syntax(self):
        row={'id':'custom','goal':'conquer_state'}
        native=root('war_goal = conquer_state')
        valid='remove_war_goal = { who = target type = humiliation }'
        validate_seed_removals(row,valid,native)
        for invalid in (valid+valid,'remove_war_goal = { who = initiator type = humiliation }'):
            with self.assertRaisesRegex(ValueError,'Absent/repeated'):
                validate_seed_removals(row,invalid,native)

    def test_border_candidates_and_defender_cultural_exception(self):
        row={'id':'9','goal':'humiliation','attacker':'AAA','target':'BBB','leader_target':'BBB','attackers':['AAA','ALLY'],'defenders':['BBB']}
        owned={'SHARED':{'a':'AAA','b':'BBB','n':'NEUTRAL'},'DISCONNECTED':{'c':'AAA','d':'BBB'},'CORE':{'e':'AAA'},'REMOTE':{'f':'BBB'}}
        candidates([row],owned,{'CORE':{'b_culture'},'REMOTE':{'a_culture'}},{'AAA':{'a_culture'},'BBB':{'b_culture'}},{},[('a','b'),('a','n')],30)
        actual={(c['side'],c['state'],c['holder'],c['target']) for c in row['candidates']}
        self.assertEqual(actual,{('attacker','SHARED','AAA','BBB'),('defender','SHARED','BBB','AAA'),('defender','CORE','BBB','AAA')})
        self.assertNotIn('ALLY',{c['holder'] for c in row['candidates']})
        script=allocation_script(row)
        self.assertIn('var:eu5_w_9_attacker_remaining >= var:eu5_w_9_0_price',script)
        self.assertIn('var:eu5_w_9_primary = 0',script)
        self.assertIn('primary_demand = no',script)

    def test_packed_locations(self):
        valid={str(i) for i in range(12)}
        self.assertEqual(decode_locations(root('3 0 5 2'),valid),['3','5','6','7'])
        self.assertEqual(decode_locations('5',valid),['5'])
        for text in ['1 3 4','1 -1','10 3','1 2 3 0']:
            with self.assertRaises(ValueError):decode_locations(root(text),valid)

    def test_participant_status(self):
        declined=participant(root('country = 2 status = Declined all_history = { { request = { side = Attacker } } }'))
        self.assertEqual(declined['status'],'Declined');self.assertIsNone(declined['joined_date'])
        text='country = 1 status = Active all_history = { { request = { side = Defender } joined = { date = 1779.1.1 } } }'
        self.assertEqual(participant(root(text))['side'],'Defender')
        with self.assertRaises(ValueError):participant(root(text.replace('Active','Unknown')))
        with self.assertRaises(ValueError):participant(root(text.replace('joined =','left =')))
        self.assertEqual(participant(root(text.replace('Active','Left')))['status'],'Left')

    def test_one_state_enemy_only_and_ties(self):
        weights={('A','ENEMY'):10,('B','ENEMY'):10,('C','NEUTRAL'):1000}
        self.assertEqual(select_state(weights,{'ENEMY'},{'B'}),('B','ENEMY'))
        self.assertEqual(select_state(weights,{'ENEMY'}),('A','ENEMY'))
        with self.assertRaises(ValueError):select_state(weights,{'OTHER'})

    def test_history_contains_staged_war_and_guard(self):
        row={'id':'1','attacker':'AAA','target':'BBB','leader_target':'BBB','attackers':['AAA','CCC'],
             'defenders':['BBB'],'goal':'conquer_state','state':'STATE_X','owner':'BBB','play_type':PREFIX+'1'}
        native={'dp_conquer_state':root('war_goal = conquer_state possible = { always = yes }')}
        script=render([row],native)
        h=fields(fields(root(script[HISTORY]))['DIPLOMATIC_PLAYS'])['c:AAA']
        ops=list(h.entries()); self.assertEqual(ops[0][0],'create_diplomatic_play')
        self.assertEqual(fields(ops[0][1])['war'],'no')
        self.assertIn('set_war = yes',script[HISTORY]);self.assertIn('end_play = yes',script[HISTORY])
        self.assertIn('has_play_goal = conquer_state',script[HISTORY])
        self.assertNotIn('annex_country',script[HISTORY]);self.assertEqual(script,render([row],native))
        self.assertEqual(fields(fields(root(script[PLAYS]))[PREFIX+'1'])['war_goal'],'conquer_state')

    def test_overlord_is_not_territorial_beneficiary_or_owner(self):
        row={'id':'2','attacker':'AAA','target':'SUB','leader_target':'OVR','attackers':['AAA'],
             'defenders':['SUB','OVR'],'goal':'conquer_state','state':'STATE_X','owner':'SUB','play_type':PREFIX+'2'}
        text=render([row],{'dp_conquer_state':root('war_goal = conquer_state')})[HISTORY]
        self.assertIn('target_country = c:OVR',text)
        self.assertIn('holder = c:AAA type = conquer_state target_country = c:SUB target_state = s:STATE_X.region_state:SUB',text)
        self.assertLess(text.index('set_war = yes'),text.index('remove_war_goal'))

    def test_secession_has_no_fabricated_dependency_or_attacker_annexation(self):
        row={'id':'3','attacker':'AAA','target':'BBB','leader_target':'BBB','attackers':['AAA'],
             'defenders':['BBB'],'goal':'secession','play_type':PREFIX+'3'}
        native={'dp_secession':root('war_goal = secession')}
        scripts=render([row],native,root('kind = revoke_all_claims settings = { validate_revoke_claims require_target_be_part_of_war }'))
        self.assertNotIn('create_diplomatic_pact',scripts[HISTORY])
        self.assertNotIn('holder = c:AAA type = annex_country',scripts[HISTORY])
        self.assertIn('holder = c:BBB type = annex_country target_country = c:AAA',scripts[HISTORY])
        self.assertIn('holder = c:AAA type = eu5_recognize_secession target_country = c:BBB',scripts[HISTORY])
        self.assertIn('require_target_be_part_of_war',scripts[GOALS])
        self.assertNotIn('validate_revoke_claims',scripts[GOALS])


if __name__=='__main__':unittest.main()
