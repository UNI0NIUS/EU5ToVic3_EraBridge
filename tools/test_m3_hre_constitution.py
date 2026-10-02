import unittest

from pdx_text import root
from extract_m3_politics import international_organizations
from m3_hre_constitution import plan_constitution, country_record_condition


class ConstitutionTests(unittest.TestCase):
    def test_historical_journal_gate_survives_exit_and_does_not_leak_roles(self):
        condition = country_record_condition(['NET','E2U','NET'])
        f = root(condition).fields()
        gates = [v.fields() for k,v in f['OR'].entries()]
        self.assertEqual(gates,[{'exists':'c:E2U','c:E2U':'THIS'}, {'exists':'c:NET','c:NET':'THIS'}])
        self.assertNotIn('power_bloc',condition)
        self.assertEqual(root(country_record_condition([])).fields(),{'always':'no'})

    def test_source_laws_are_not_inferred_from_ai_proposals(self):
        raw = root('''database = { 0 = { type = hre all_members = { 1 }
          implemented_laws = { imperial_voting_law = { object = emperor_dynastic_preference_policy date = 1770.1.1 } }
          parliament = { parliament_type = hre_bi_camerial_imperial_diet }
          circles_active = yes imperial_circles = { 5 6 }
          variables = { io_law_target = erbkaisertum_policy }
        } }''')
        c = international_organizations(raw)[0]['constitution']
        self.assertEqual(c['laws'], {'imperial_voting_law': 'emperor_dynastic_preference_policy'})
        self.assertEqual(c['imperial_circles'], ['5', '6'])
        self.assertTrue(c['circles_active'])

    def test_colonies_do_not_receive_seats_and_missing_elector_is_not_reassigned(self):
        org = {'id':'0', 'members':['1','2','3'], 'special_statuses':{
            'elector':['2','3'], 'archbishop_elector':['2'], 'free_city':['3']},
            'constitution':{'laws':{'power_of_the_emperor_law':'kaisertum_policy'}}}
        bloc = {'members':['BOH','E2U','COL']}
        c = plan_constitution(org, bloc, {'1':'BOH','2':'E2U','99':'COL'}, 'personal_balance')
        self.assertEqual(c['electors'], ['E2U'])
        self.assertEqual(c['associated_members'], ['COL'])
        self.assertEqual(c['roles']['free_city']['without_target'], ['3'])
        self.assertEqual(c['unreviewed_policies'], {'power_of_the_emperor_law':'kaisertum_policy'})
        self.assertFalse(c['elections_implemented'])

    def test_overlapping_organization_exclusion_does_not_grant_a_seat(self):
        org = {'id':'0', 'members':['1','2'], 'special_statuses':{'elector':['2']}}
        c = plan_constitution(org, {'members':['AAA']}, {'1':'AAA','2':'BBB'}, 'source_only')
        self.assertEqual(c['roles']['elector']['outside_bloc'], ['2'])
        self.assertFalse(c['electors'])
        self.assertFalse(c['source_constitution_present'])
        self.assertFalse(c['additional_principles'])

    def test_invalid_mode_is_not_silently_a_balance_change(self):
        with self.assertRaisesRegex(ValueError, 'market mode'):
            plan_constitution({'id':'0'}, {}, {}, 'typo')


if __name__ == '__main__': unittest.main()
