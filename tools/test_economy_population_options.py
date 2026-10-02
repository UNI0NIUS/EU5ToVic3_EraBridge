import json
from pathlib import Path
from unittest import TestCase, main
from package_m5_population_options import apply_mode


class PopulationOptionsTests(TestCase):
    def setUp(self):
        self.policy=json.loads((Path(__file__).resolve().parents[1]/'config/personal/economy_population_options.json').read_text())
        self.groups={('A','ITA','a','r'):1000,('B','NRU','b','r'):1000}
        self.employment=[{'state':s,'country':t,'population':n,'formal_job_capacity':260,'new_subsistence_job_capacity':0} for (s,t,c,r),n in self.groups.items()]

    def test_preserve_retains_each_group_even_when_capacity_is_low(self):
        after,_=apply_mode('preserve',self.groups,self.employment,{}, {},self.policy)
        self.assertEqual(after,self.groups)

    def test_optimization_applies_equally_to_source_and_template_countries(self):
        after,_=apply_mode('reserve_15',self.groups,self.employment,{}, {},self.policy)
        self.assertEqual(set(after.values()),{897})

    def test_switch_roundtrip_uses_original_baseline(self):
        optimized,_=apply_mode('reserve_15',self.groups,self.employment,{}, {},self.policy)
        restored,_=apply_mode('preserve',self.groups,self.employment,{}, {},self.policy)
        repeated,_=apply_mode('reserve_15',restored,self.employment,{}, {},self.policy)
        self.assertEqual(optimized,repeated)
        self.assertEqual(restored,self.groups)

    def test_missing_world_part_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Incomplete worldwide'):
            apply_mode('reserve_15',self.groups,self.employment[:1],{}, {},self.policy)

    def test_duplicate_part_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate employment'):
            apply_mode('preserve',self.groups,self.employment*2,{}, {},self.policy)

    def test_unknown_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown population mode'):
            apply_mode('delete_all',self.groups,self.employment,{}, {},self.policy)


if __name__=='__main__':main()
