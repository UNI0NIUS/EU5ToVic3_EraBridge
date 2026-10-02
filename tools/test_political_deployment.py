"""Deployment regressions: remove template leakage, preserve dependencies/ownership."""
import unittest
from types import SimpleNamespace
from deploy_political_rules import (strip_politics, technology_roots, institution_plan,
                                   deployment_laws, replace_methods, validate_laws)
from pdx_text import root


class DeploymentTests(unittest.TestCase):
    def test_remove_old_template_and_institution_without_touching_ruler_scope(self):
        s = ('effect_starting_politics_traditional = yes\nadd_technology_researched = democracy\n'
             'activate_law = law_type:law_monarchy\n'
             'set_institution_investment_level = { institution = schools level = 5 }\n'
             'ig:ig_landowners ?= { add_ruling_interest_group = yes }\n')
        self.assertEqual(strip_politics(s).strip(), 'ig:ig_landowners ?= { add_ruling_interest_group = yes }')

    def test_conditional_politics_fails_closed(self):
        with self.assertRaises(ValueError):
            strip_politics('if = { limit = { always = yes } activate_law = law_type:law_monarchy }')

    def technology(self, proposals):
        techs = {'rationalism': {'category': 'society'}, 'democracy': {'category': 'society', 'unlocking_technologies': root('rationalism')},
                 'mass_communication': {'category': 'society', 'unlocking_technologies': root('democracy')}, 'steel': {'category': 'production'}}
        target = SimpleNamespace(techs=techs)
        return technology_roots({'democracy','rationalism','steel'}, {'capability_technology_proposals': proposals},
                                {'advances': [], 'institutions': []}, set(), {}, target, [], [], set())

    def test_unconditional_democracy_removed_without_evidence(self):
        techs, _ = self.technology({})
        self.assertEqual(techs, {'steel'})

    def test_democracy_retained_as_real_prerequisite_with_audit(self):
        techs, audit = self.technology({'mass_communication': ['advance:newspapers']})
        self.assertIn('democracy', techs)
        self.assertEqual(audit['democracy_roots'], ['mass_communication'])
        self.assertIn('democracy', audit['prerequisites'])

    def test_institution_caps_have_no_invented_base_level(self):
        defs = {'school_law': {'institution': 'schools'}}
        target = SimpleNamespace(techs={'rationalism': {'modifier': root('country_schools_max_investment_add = 1')}})
        levels, caps = institution_plan({'institutions': {'schools': {'planned_level': 5}}}, {'school_law'}, {'rationalism'}, defs, target)
        self.assertEqual(levels, {'schools': 1})
        self.assertEqual(caps, levels)

    def test_decentralized_enabling_law_does_not_silently_start_institution(self):
        defs = {'law_no_police': {'group': 'lawgroup_policing'}, 'law_local_police': {'group': 'lawgroup_policing', 'institution': 'police'}}
        selected, overrides = deployment_laws({'target_country_type': 'decentralized', 'laws': {'lawgroup_policing': {'law': 'law_local_police'}}}, defs)
        self.assertEqual(selected['lawgroup_policing'], 'law_no_police')
        self.assertEqual(len(overrides), 1)

    def test_incompatible_laws_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_laws({'economy': 'traditional', 'tax': 'graduated'},
                          {'traditional': {'group': 'economy', 'disallowing_laws': root('graduated')}, 'graduated': {'group': 'tax'}})

    def test_pm_repair_preserves_ownership(self):
        body = 'add_ownership = { country = c:OTHER levels = 7 }\nactivate_production_methods = { serf }'
        row = {'body': body, 'pms': ['serf'], 'state': 'A', 'owner': 'B', 'building': 'farm', 'levels': 7}
        replace_methods(SimpleNamespace(changes=[]), row, ['free'])
        self.assertIn('add_ownership = { country = c:OTHER levels = 7 }', row['body'])
        self.assertEqual(row['levels'], 7)
        self.assertEqual(row['pms'], ['free'])


if __name__ == '__main__': unittest.main()
