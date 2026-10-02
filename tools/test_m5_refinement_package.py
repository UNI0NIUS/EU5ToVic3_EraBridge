import unittest
from pdx_text import root
from build_m2_prototype import strings
from package_m5_culture_refinement import (strip_imported_literacy,
    strip_imported_hook, non_homeland_states, homeland_pairs)


class RefinementPackageTests(unittest.TestCase):
    def test_existing_literacy_is_removed_without_wealth_or_template_mutation(self):
        text='POPULATION = { c:ITA = { effect_starting_pop_wealth_low = yes eu5_m4_literacy_ITA = yes effect_starting_pop_literacy_high = yes } }'
        cleaned=strip_imported_literacy(text)
        self.assertEqual(root(cleaned).fields()['POPULATION'].fields()['c:ITA'].fields(),
            {'effect_starting_pop_wealth_low':'yes','effect_starting_pop_literacy_high':'yes'})

    def test_hre_and_other_start_hooks_survive_and_duplicates_fail_closed(self):
        text='on_game_started = { on_actions = { hre_init eu5_m4_literacy_after_setup other_init } effect = { foo = yes } } on_monthly_pulse = { effect = { bar = yes } }'
        result=root(strip_imported_hook(text)).fields()
        self.assertEqual(strings(result['on_game_started'].fields()['on_actions']),['hre_init','other_init'])
        self.assertEqual(result['on_game_started'].fields()['effect'].fields(),{'foo':'yes'})
        self.assertEqual(result['on_monthly_pulse'].fields()['effect'].fields(),{'bar':'yes'})
        with self.assertRaises(ValueError):strip_imported_hook(text.replace('other_init','eu5_m4_literacy_after_setup'))

    def test_homeland_change_cannot_hide_ownership_change(self):
        text='STATES = { s:STATE_A = { create_state = { country = c:AAA owned_provinces = { x000001 } } add_homeland = cu:old } }'
        revised=text.replace('cu:old','cu:new')
        self.assertEqual(non_homeland_states(text),non_homeland_states(revised))
        self.assertEqual(homeland_pairs(revised),{('STATE_A','new')})
        self.assertNotEqual(non_homeland_states(text),non_homeland_states(revised.replace('c:AAA','c:BBB')))


if __name__=='__main__':unittest.main()
