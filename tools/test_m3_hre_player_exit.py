import unittest
from decimal import Decimal as D
from types import SimpleNamespace
from pdx_text import root
from m3_hre_player_exit import exit_probability, plan_player_exit, patch_on_actions, patch_invite


class PlayerExitTests(unittest.TestCase):
    def test_dominant_source_player_leaves_even_if_elector(self):
        chance, _ = exit_probability(D(80),D(10),D(200),D(400),D(100),True,True)
        self.assertEqual(chance,100)

    def test_small_elector_is_not_driven_out(self):
        chance,_=exit_probability(D(1),D(10),D(1),D(100),D(0),True,False)
        self.assertEqual(chance,5)

    def test_invalid_population_does_not_invent_a_motive(self):
        self.assertEqual(exit_probability(D(10),D(0),D(10),D(20),D(0),False,False)[0],0)

    def test_emperor_and_subject_do_not_receive_exit_offer(self):
        w=SimpleNamespace(audit={'player':{'id':1}},tags={'1':'AAA'})
        bloc={'source_type':'hre','members':['AAA'],'leader':'AAA'}
        self.assertEqual(plan_player_exit(w,[bloc],[])['reason'],'source_player_is_emperor')
        bloc['leader']='BBB'
        self.assertEqual(plan_player_exit(w,[bloc],[{'target_subject':'AAA','target_overlord':'BBB'}])['reason'],'source_player_is_subject')

    def test_player_detection_uses_source_id_not_italy_tag(self):
        w=SimpleNamespace(audit={'player':{'id':42}},tags={'42':'XYZ'},
             source={'42':{'population_persons':'80'},'1':{'population_persons':'10'}},
             countries={'XYZ':{'source_government':'republic','country_type':'recognized'},
                        'BOH':{'source_government':'monarchy','country_type':'recognized'}})
        w.tags['1']='BOH'
        b={'source_type':'hre','name':'EU5_BLOC_0','members':['XYZ','BOH'],'leader':'BOH','constitution':{'electors':[]}}
        p=plan_player_exit(w,[b],[])
        self.assertEqual(p['target'],'XYZ'); self.assertEqual(p['ai_leave_percent'],100)

    def test_hook_preserves_native_effects_and_existing_callbacks(self):
        source='on_game_started_after_lobby = { effect = { existing = yes } on_actions = { existing_hook } } on_diplomatic_action = { effect = { post_notification = diplomatic_action_notification } } other = { effect = { keep = yes } }'
        old=root(source).fields(); new=root(patch_on_actions(source)).fields()
        for key in ('on_game_started_after_lobby','on_diplomatic_action'):
            self.assertEqual(old[key].fields()['effect'].text(),new[key].fields()['effect'].text())
        self.assertIn('existing_hook',new['on_game_started_after_lobby'].fields()['on_actions'].text())
        self.assertEqual(old['other'].text(),new['other'].text())

    def test_ai_desire_only_applies_with_permit_against_current_bloc(self):
        text='invite_to_power_bloc = { ai = { accept_score = { value = 10 } } accept_effect = { leave_alone = yes } }'
        p=root(patch_invite(text)).fields()['invite_to_power_bloc'].fields()
        score=p['ai'].fields()['accept_score'].text()
        self.assertIn('has_variable = eu5_hre_exit_permit',score)
        self.assertIn('is_in_same_power_bloc = scope:actor',score)
        self.assertIn('value = 10',score)
        self.assertEqual(p['accept_effect'].fields(),{'leave_alone':'yes'})


if __name__ == '__main__': unittest.main()
