import unittest

from package_m5_military_technology import (army_signature, convert_armies, nontech,
                                          replace_technology, replacement)
from pdx_text import root


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.units = {
            'combat_unit_type_irregular_infantry': {'group':'infantry'},
            'cannon': {'group':'artillery','upgrades':root('mobile advanced'),'unlocking_technologies':root('artillery')},
            'mobile': {'group':'artillery','upgrades':root('advanced'),'unlocking_technologies':root('napoleonic_warfare')},
            'advanced': {'group':'artillery','unlocking_technologies':root('advanced')},
        }

    def test_preserve_nontech_and_replace_template(self):
        old=root('''
activate_law = law_type:law_monarchy
effect_starting_technology_tier_3 = yes
add_era_researched = era_1
add_technology_researched = old
set_institution_investment_level = { institution = institution_schools level = 2 }
''')
        new=root(replace_technology(old, {'artillery','standing_army'}))
        self.assertEqual(nontech(old),nontech(new))
        self.assertEqual([v for k,v in new.entries() if k=='add_technology_researched'],['artillery','standing_army'])
        self.assertNotIn('effect_starting_technology',new.text())

    def test_no_upgrade_and_closest_legal_predecessor(self):
        self.assertEqual(replacement('cannon',{'artillery','napoleonic_warfare'},self.units),'cannon')
        self.assertEqual(replacement('advanced',{'artillery','napoleonic_warfare'},self.units),'mobile')
        self.assertEqual(replacement('mobile',{'artillery'},self.units),'cannon')
        self.assertEqual(replacement('mobile',set(),self.units),'combat_unit_type_irregular_infantry')

    def test_quantity_location_navy_fallback_and_idempotence(self):
        text='''MILITARY_FORMATIONS = {
c:AAA = {
create_military_formation = { type = army hq_region = sr:test name = "Army One"
 combat_unit = { type = unit_type:mobile count = 73 state_region = s:test }
}
create_military_formation = { type = fleet name = "Fleet" create_ship = { type = ship_type:frigate } }
}
c:ZZZ = { create_military_formation = { type = army combat_unit = { type = unit_type:mobile count = 4 state_region = s:other } } }
}'''
        after,changes=convert_armies(text,{'AAA':{'artillery'}},self.units)
        self.assertEqual(army_signature(text,True),army_signature(after,True))
        self.assertEqual(len(changes),1)
        self.assertEqual(changes[0]['count'],73)
        self.assertEqual(changes[0]['after'],'cannon')
        self.assertIn('type = unit_type:mobile count = 4',after)
        self.assertEqual(convert_armies(after,{'AAA':{'artillery'}},self.units),(after,[]))


if __name__ == '__main__': unittest.main()
