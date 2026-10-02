from collections import Counter
import json
from pathlib import Path
from unittest import TestCase, main
from economy_arable_adjustment import choose_land, location_fraction


class ArableAdjustmentTests(TestCase):
    def setUp(self):
        self.policy=json.loads((Path(__file__).resolve().parents[1]/'config/personal/economy_arable_adjustment.json').read_text())

    def test_population_demand_cannot_raise_geographic_ceiling(self):
        self.assertEqual(choose_land(20,.3,Counter(ITA=6),{'ITA':(10**9,5000)})[0],26)
        self.assertEqual(choose_land(20,.3,Counter(ITA=6),{'ITA':(4000,5000)})[0],21)
        self.assertEqual(choose_land(20,.3,Counter(ITA=6),{'ITA':(0,5000)})[0],20)

    def test_no_land_created_from_zero_or_desert_development(self):
        self.assertEqual(choose_land(0,.5,Counter(ITA=1),{'ITA':(10**9,5000)})[0],0)
        g={'topography':'flatland','climate':'arid','vegetation':'desert'}
        self.assertEqual(location_fraction(g,{'development':100,'raw_material':'coal'},False,self.policy),0)
        self.assertEqual(location_fraction(g,{'development':100,'raw_material':'wheat'},False,self.policy),0)
        self.assertLess(location_fraction(g,{'development':100,'raw_material':'wheat'},True,self.policy),.05)

    def test_source_development_and_crop_evidence_matter(self):
        g={'topography':'flatland','climate':'continental','vegetation':'farmland'}
        rich=location_fraction(g,{'development':90,'raw_material':'wheat'},False,self.policy)
        poor=location_fraction(g,{'development':10,'raw_material':'wheat'},False,self.policy)
        industrial=location_fraction(g,{'development':90,'raw_material':'iron'},False,self.policy)
        self.assertGreater(rich,poor);self.assertGreater(rich,industrial)
        self.assertLessEqual(rich,.5)

    def test_split_state_never_uses_other_owners_vacancies(self):
        new,benefit=choose_land(20,.5,Counter(ITA=19,BOH=1),{'BOH':(50000,5000)})
        self.assertEqual(new,30);self.assertEqual(benefit['BOH'],5000)

    def test_repeat_calculation_from_original_is_idempotent(self):
        args=(20,.3,Counter(ITA=1),{'ITA':(50000,5000)})
        self.assertEqual(choose_land(*args),choose_land(*args))


if __name__=='__main__':main()
