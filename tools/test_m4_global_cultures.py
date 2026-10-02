import unittest
from pathlib import Path
from unittest.mock import patch
from m4_culture_budget import enforce, METRICS, check_and_catalog
from m4_cultures import resident_language
from m4_migrant_cultures import cohort_states
from pdx_text import root
from m3_world import fields
from build_m2_prototype import objects

class GlobalCultureTests(unittest.TestCase):
    def test_reviewed_language_groups_count_but_religion_heritage_does_not(self):
        limits={'max_'+k:10 for k in METRICS}
        limits['max_resident_heritage_groups']=0
        groups={'eu5_reviewed_language_group_example':{'type':'language'},
                'eu5_religious_group_example':{'type':'heritage'}}
        def run(language_limit):
            with patch('m4_culture_budget.definitions',side_effect=[{}, {}, groups, {}]), \
                 patch('m4_culture_budget.load_localization',return_value={}):
                return check_and_catalog(Path('.'),Path('.'),{'custom_cultures':[],'mod_directory':'.'},
                    {'culture_budget':{**limits,'max_resident_language_groups':language_limit}},
                    {},{},{'cultures':[]},lambda *args:None)
        self.assertEqual(run(1)['counts']['resident_language_groups'],1)
        with self.assertRaisesRegex(ValueError,'resident_language_groups'):
            run(0)

    def test_each_budget_dimension_fails_closed(self):
        limits={'max_'+k:10 for k in METRICS};counts={k:10 for k in METRICS}
        enforce(limits,counts)
        for k in METRICS:
            with self.subTest(metric=k),self.assertRaisesRegex(ValueError,'exceeded'):
                enforce(limits,{**counts,k:11})

    def test_missing_budget_not_silently_disabled(self):
        with self.assertRaisesRegex(ValueError,'Incomplete'):
            enforce({},dict.fromkeys(METRICS,0))

    def test_heterogeneous_aggregate_does_not_use_seed_language(self):
        traits={};groups={}
        language,group=resident_language({'aggregate_language':True,'aggregate_seed':'example','source_language':'seed_language'}, {},{},traits,groups)
        self.assertEqual(language,'eu5_aggregate_language_example')
        self.assertEqual(group,'eu5_aggregate_language_group_example')
        self.assertNotIn('seed_language',str(traits))

    def test_macro_regions_keep_origin_scopes_and_fail_on_overlap(self):
        regions={k:fields(o) for k,o in objects(root('a = { states = { STATE_A } } b = { states = { STATE_B } }'))}
        config={'regions':{'settler':['a','b'],'diaspora':['a']},'macro_regions':{'wide':{'regions':['a','b']}}}
        self.assertEqual(cohort_states(config,regions),{'settler':{'STATE_A':'wide','STATE_B':'wide'},'diaspora':{'STATE_A':'wide'}})
        config['macro_regions']['duplicate']={'regions':['a']}
        with self.assertRaisesRegex(ValueError,'Overlapping'):cohort_states(config,regions)

if __name__=='__main__':unittest.main()
