import unittest
from m3_flag_art import contextual_design,compile_design,economic_features


class ArtTests(unittest.TestCase):
    def design(self,capital,culture='ligurian',colonial=False):
        return contextual_design('fixed:0',[30,110,65],{'source_culture':culture,'source_capital':capital}, {},colonial,'12_indonesia')

    def test_country_and_place_names_do_not_select_handmade_cases(self):
        self.assertEqual(self.design('saipan'),self.design('funchal'))
        self.assertEqual(self.design('funchal'),self.design('arbitrary_other_save_capital'))

    def test_economy_uses_source_employment_not_geographic_stereotype(self):
        cs={'X':{'source_id':'9','capital':'COAST'},'Y':{'source_id':'10','capital':'LAND'}}
        source={'locations':{'a':{'owner':'9','raw_material':'sugar','rgo_workers':5},
                             'b':{'owner':'10','raw_material':'lumber','rgo_workers':0}}}
        f=economic_features(cs,source,{'COAST'})
        self.assertTrue(f['X']['small_coastal_country']);self.assertEqual(f['X']['dominant_resource'],'sugar')
        self.assertIsNone(f['Y']['dominant_resource']);self.assertFalse(f['Y']['small_coastal_country'])

    def test_maritime_rule_generalizes_to_an_unseen_republic(self):
        c={'source_culture':'invented_settler_culture','flag_features':{'small_coastal_country':True}}
        d=contextual_design('new-save',[40,90,130],c,{'government':'republic'},False,'arbitrary_region')
        self.assertIn('ce_lymphad',compile_design(d));self.assertIn('ce_waves',compile_design(d))
        self.assertEqual(d['government'],'republic')

    def test_cultural_emblems_do_not_depend_on_religious_shortcut(self):
        a=self.design('yanhe','tujia_culture');b=self.design('canajoharie','kanienkehaka_culture')
        self.assertIn('ce_tujia_white_tiger',compile_design(a))
        self.assertIn('ce_wampum_mohawk',compile_design(b))
        self.assertNotIn('shield',compile_design(b))
        motif=next(l for l in b['layers'] if 'wampum' in l['emblem'])
        self.assertNotEqual(motif['color'],motif['color2'])
        self.assertIn('color3 =',compile_design(b))

    def test_colonial_foreground_respects_canton(self):
        for i in range(100):
            d=contextual_design(str(i),[30,110,65],{'source_culture':'ligurian'}, {},True,'12_indonesia')
            for l in d['layers']:
                x,y=l['position'];sx,sy=l['scale']
                self.assertGreaterEqual(x-sx/2,0);self.assertLessEqual(x+sx/2,1)
                self.assertGreaterEqual(y-sy/2,0);self.assertLessEqual(y+sy/2,1)
                if not l.get('background'):self.assertTrue(x-sx/2>=.4 or y-sy/2>=.4)

if __name__=='__main__':unittest.main()
