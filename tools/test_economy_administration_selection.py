"""Government PM capacity must not be ranked as saleable goods output."""
import unittest
from economy_model import Target
from pdx_text import root


class AdministrationSelectionTests(unittest.TestCase):
    def target(self):
        t=Target.__new__(Target)
        t.buildings={'building_government_administration':{'production_method_groups':root('organization ownership')}}
        t.groups={'organization':{'production_methods':root('simple cabinets archives')},
                  'ownership':{'production_methods':root('hereditary professional')}}
        t.pms={
            'simple':{'country_modifiers':root('workforce_scaled = { country_bureaucracy_add = 10 }')},
            'cabinets':{'country_modifiers':root('workforce_scaled = { country_bureaucracy_add = 50 }'),'unlocking_technologies':root('centralization')},
            'archives':{'country_modifiers':root('workforce_scaled = { country_bureaucracy_add = 65 }'),'unlocking_technologies':root('central_archives')},
            'hereditary':{'unlocking_laws':root('law_hereditary_bureaucrats')},
            'professional':{'disallowing_laws':root('law_hereditary_bureaucrats')},
        }
        return t

    def test_does_not_stick_to_simple_reference_after_unlock(self):
        t=self.target()
        result=t.select('building_government_administration',{'centralization'},['simple','hereditary'],{'law_hereditary_bureaucrats'})
        self.assertEqual(result,['cabinets','hereditary'])

    def test_technology_and_law_gates_still_apply(self):
        t=self.target()
        self.assertEqual(t.select('building_government_administration',set(),['archives'],set()),['simple','professional'])
        self.assertEqual(t.select('building_government_administration',{'centralization','central_archives'},['simple'],set()),['archives','professional'])


if __name__=='__main__':unittest.main()
