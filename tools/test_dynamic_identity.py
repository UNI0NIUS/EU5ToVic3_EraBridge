import unittest
from pdx_text import root
from m5_dynamic_identity import guard_body, referenced_law_groups, generic_art
from verify_dynamic_identity import evaluate,choose


class DynamicIdentityTests(unittest.TestCase):
    def setUp(self):
        self.defs={'monarchy':{'group':'lawgroup_governance_principles'},'autocracy':{'group':'lawgroup_distribution_of_power'},
                   'trade':{'group':'lawgroup_trade_policy'},'atheism':{'group':'lawgroup_church_and_state'}}
        self.scripts={'coa_fascist_trigger':root('always = no'),'coa_nihilist_trigger':root('always = no'),
                      'coa_def_secessionist_or_revolutionary_trigger':root('OR = { is_revolutionary = yes is_secessionist = yes }')}
        self.guard=root(guard_body({'monarchy','autocracy','trade'},self.defs,False,'ideology_moderate'))

    def test_opening_and_unrelated_law(self):
        self.assertTrue(evaluate(self.guard,{'laws':{'monarchy','autocracy','different_trade'}},self.scripts))

    def test_changed_regime_and_restoration(self):
        self.assertFalse(evaluate(self.guard,{'laws':{'republic','autocracy'}},self.scripts))
        self.assertTrue(evaluate(self.guard,{'laws':{'monarchy','autocracy'}},self.scripts))

    def test_independence_and_revolution_release_opening_override(self):
        g=root(guard_body({'monarchy','autocracy'},self.defs,True,'ideology_moderate'))
        self.assertFalse(evaluate(g,{'laws':{'monarchy','autocracy'},'subject':False},self.scripts))
        self.assertFalse(evaluate(self.guard,{'laws':{'monarchy','autocracy'},'is_revolutionary':True},self.scripts))

    def test_native_law_dependencies_are_transitive_and_cycle_safe(self):
        scripts={'outer':root('inner = yes'),'inner':root('has_law = law_type:atheism outer = yes')}
        groups=referenced_law_groups([root('trigger = { outer = yes }')],scripts,self.defs)
        self.assertIn('lawgroup_church_and_state',groups)
        self.assertNotIn('lawgroup_trade_policy',groups)

    def test_variant_uses_immutable_source_panel_clear_of_canton(self):
        body=generic_art('SOURCE',[30,80,120],'communist','confucian')
        self.assertIn('parent = "SOURCE"',body)
        self.assertIn('scale = { 1 1 } offset = { 0 0 }',body)
        self.assertIn('ce_hammer_and_sickle.dds',body)

    def test_flag_survives_independence_but_not_regime_change(self):
        g=root(guard_body({'monarchy','autocracy'},self.defs,True,'ideology_moderate',preserve_flag=True))
        for subject in (True,False):
            self.assertTrue(evaluate(g,{'laws':{'monarchy','autocracy'},'subject':subject},self.scripts))
        self.assertFalse(evaluate(g,{'laws':{'republic','autocracy'},'subject':False},self.scripts))

    def test_unknown_native_predicate_is_not_reported_as_verified(self):
        flags=root('flag_definition = { coa = DEFAULT priority = 1 } flag_definition = { coa = SPECIAL priority = 5 trigger = { unknown = yes } }')
        self.assertIsNone(choose(flags,{'laws':set()},{},'flag_definition'))


if __name__=='__main__':unittest.main()
