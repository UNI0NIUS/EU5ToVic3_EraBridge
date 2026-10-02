"""Meaningful rule regressions; no dependency on private saves/game installation."""
import unittest
from build_political_rules_report import evaluate, institutions, normalized_catalog, evidence
from political_rulebook import DEFAULTS, rulebook, TECH_BRIDGES


def fixture_catalog():
    result={}
    for group,law in DEFAULTS.items():
        if law:result['law_'+law]={'group':'lawgroup_'+group}
    for rule in rulebook():result[rule['law']]={'group':rule['group']}
    for v in result.values():
        v.update(script='',institution=None,technologies=[],disallowing_laws=[],unlocking_laws=[])
    return result


class PoliticalRulesTest(unittest.TestCase):
    def run_case(self, policies=(), reforms=(), advances=(), privileges=(), axes=(), metrics=None, government='monarchy', **kwargs):
        c={'government':government,'laws':[(str(n),[('object',p)]) for n,p in enumerate(policies)],'reforms':list(reforms)}
        f={'advances':list(advances),'institutions':[],'privileges':[(None,[('object',p)]) for p in privileges], 'societal_values':list(axes)}
        return evaluate(c,f,metrics or {},fixture_catalog(),rulebook(),**kwargs)

    def law(self,r,g):return r['laws']['lawgroup_'+g]['law']

    def test_republic_can_be_autocratic(self):
        r=self.run_case(['absolute_presidential_power_policy','dynastic_rule_policy'],government='republic')
        self.assertEqual(self.law(r,'governance_principles'),'law_presidential_republic')
        self.assertEqual(self.law(r,'distribution_of_power'),'law_autocracy')

    def test_research_does_not_enact_constitution_or_abolition(self):
        r=self.run_case(reforms=['universal_serfdom'],advances=['the_constitution','abolished_serfdom','military_revolution_advance'])
        self.assertEqual(self.law(r,'land_reform'),'law_serfdom')
        self.assertEqual(self.law(r,'army_model'),'law_peasant_levies')
        self.assertEqual(self.law(r,'distribution_of_power'),'law_autocracy')

    def test_censorship_beats_free_press(self):
        r=self.run_case(['free_press','strict_censorship'])
        self.assertEqual(self.law(r,'free_speech'),'law_censorship')
        self.assertTrue(r['warnings'])

    def test_dynastic_bureaucrats_survive_centralization(self):
        r=self.run_case(['dynastic_administration_policy','centralized_bureaucracy_policy'])
        self.assertEqual(self.law(r,'bureaucracy'),'law_hereditary_bureaucrats')

    def test_colonial_law_needs_actual_activity(self):
        self.assertEqual(self.law(self.run_case(['settled_colonies']),'colonization'),'law_no_colonial_affairs')
        r=self.run_case(['settled_colonies'],colonial_overlord=True)
        self.assertEqual(self.law(r,'colonization'),'law_colonial_resettlement')
        r=self.run_case(government='republic',colonial_subject=True)
        self.assertEqual(self.law(r,'governance_principles'),'law_colonial_administration')

    def test_enactment_transition_not_simultaneous_law(self):
        catalog=fixture_catalog();catalog['law_legacy_slavery']['unlocking_laws']=['law_slave_trade']
        r=evaluate({'laws':[],'government':'monarchy'},{},{'slave_population':100},catalog,rulebook())
        self.assertEqual(self.law(r,'slavery'),'law_legacy_slavery')

    def test_abolition_with_slaves_preserves_warning(self):
        r=self.run_case(['slavery_outlawed'],metrics={'slave_population':100})
        self.assertEqual(self.law(r,'slavery'),'law_slavery_banned')
        self.assertTrue(any('人口' in w for w in r['warnings']))

    def test_law_conflict_resolves_without_erasing_stronger_rule(self):
        catalog=fixture_catalog();catalog['law_public_schools']['disallowing_laws']=['law_state_religion']
        c={'government':'theocracy','laws':[('education',[('object','secular_education')])]}
        r=evaluate(c,{}, {},catalog,rulebook())
        self.assertEqual(self.law(r,'church_and_state'),'law_state_religion')
        self.assertEqual(self.law(r,'education_system'),'law_no_schools')
        self.assertTrue(r['conflict_resolutions'])

    def test_inactive_services_are_zero_not_free_levels(self):
        r=self.run_case(advances=['medical_school_advance','sanitation_advance'])
        catalog=fixture_catalog();tech={k:{'script':''} for k in TECH_BRIDGES}
        inst=institutions(r,catalog,tech,{'institution_health_system':{},'institution_schools':{}})
        self.assertEqual(inst['institution_health_system']['planned_level'],0)
        self.assertEqual(inst['institution_schools']['planned_level'],0)

    def test_cap_is_sum_clamped_not_sum_plus_one(self):
        r=self.run_case(['secular_education','centralized_bureaucracy_policy'],reforms=['the_education_act'],metrics={'literacy_percent':80})
        catalog=fixture_catalog();catalog['law_public_schools']['institution']='institution_schools'
        tech={k:{'script':''} for k in TECH_BRIDGES}
        tech['centralization']['script']='modifier = { country_institution_schools_max_investment_add = 2 }'
        inst=institutions(r,catalog,tech,{'institution_schools':{}})['institution_schools']
        self.assertEqual(inst['desired_level'],3)
        self.assertEqual(inst['planned_level'],2)
        self.assertIsNone(inst['deployable_level'])

    def test_missing_axis_is_not_extreme(self):
        t,axes=evidence({'government':'monarchy'},{'societal_values':[['serfdom_vs_free_subjects','-999']]},{})
        self.assertNotIn('fact:serf_society',t);self.assertNotIn('serfdom_vs_free_subjects',axes)

    def test_variant_inherits_constraints(self):
        raw={
            'parent':dict(script='institution = institution_schools', institution='institution_schools',technologies=['a'],disallowing_laws=['x']),
            'child':dict(script='parent = parent',institution=None,technologies=[],disallowing_laws=[])}
        c=normalized_catalog(raw)['child']
        self.assertEqual(c['institution'],'institution_schools')
        self.assertEqual(c['technologies'],['a']);self.assertEqual(c['disallowing_laws'],['x'])

    def test_rule_determinism(self):
        a=self.run_case(['free_press','limited_censorship']);b=self.run_case(['limited_censorship','free_press'])
        self.assertEqual(a['laws'],b['laws'])


if __name__=='__main__':unittest.main()
