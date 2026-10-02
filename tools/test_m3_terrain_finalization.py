import unittest
from m3_terrain_finalization import plan


class TerrainRules(unittest.TestCase):
    def test_final_anchor_replaces_stale_vanilla_owner(self):
        p=plan({'S':{'a':'RUS','b':'U01'}},[{'rule':'wasteland','state':'S','province':'a','neighbor':'b'}],{},[('a','b')])
        self.assertEqual(p['changes'],[{'state':'S','province':'a','from':'RUS','to':'U01'}])
    def test_reviewed_source_country_wins_over_tribal_neighbor(self):
        p=plan({'S':{'a':'RUS','b':'U01'}},[{'rule':'wasteland','state':'S','province':'a','neighbor':'b'}],{},[],{'a':{'FRA':9}})
        self.assertEqual(p['changes'][0]['to'],'FRA')
    def test_direct_source_and_unknown_island_are_unchanged(self):
        self.assertFalse(plan({'S':{'a':'RUS','b':'FRA'}},[],{},[])['changes'])
    def test_terrain_can_merge_same_culture_tribes_only(self):
        countries={t:{'culture':c,'generated_uncolonized':n} for t,c,n in [('U1','c',True),('U2','c',True),('FRA','c',False),('U3','d',True)]}
        p=plan({'S':{'a':'U1','b':'U2','c':'FRA','d':'U3'}},[],countries,[('a','b'),('b','c'),('a','d')],country_population={'U2':10})
        self.assertEqual(p['country_aliases'],{'U1':'U2'})
    def test_disconnected_same_culture_is_not_merged(self):
        c={t:{'culture':'c','generated_uncolonized':True} for t in ('U1','U2')}
        self.assertFalse(plan({'S':{'a':'U1','b':'U2'}},[],c,[])['country_aliases'])
    def test_nearest_centroid_cannot_jump_across_owned_land(self):
        p=plan({'S':{'a':'RUS','b':'U01','c':'FRA'}},[{'rule':'wasteland','state':'S','province':'a','neighbor':'b'}],{},[('a','c'),('c','b')])
        self.assertEqual(p['changes'][0]['to'],'FRA')
    def test_no_land_evidence_is_explicitly_unresolved(self):
        p=plan({'S':{'a':'RUS','b':'U01'}},[{'rule':'wasteland','state':'S','province':'a','neighbor':'b'}],{},[])
        self.assertFalse(p['changes']);self.assertEqual(p['unresolved'][0]['province'],'a')
    def test_tribal_name_is_ethnicity_without_region_or_suffix(self):
        from types import SimpleNamespace
        from build_m3_world import Exporter
        e=Exporter.__new__(Exporter)
        e.w=SimpleNamespace(countries={'U01':{'generated_uncolonized':True,'culture':'siberian','source_culture':'siberian','capital':'STATE_KOLYMA'}})
        e.localization={'english':{},'simp_chinese':{}}
        e.target_labels={'english':{'siberian':'Siberian'},'simp_chinese':{'siberian':'西伯利亚'}}
        e.localize=lambda key,lang:key
        e.names()
        self.assertEqual(e.localization['english'],{'U01':'Siberian','U01_ADJ':'Siberian'})
        self.assertEqual(e.localization['simp_chinese']['U01'],'西伯利亚')

if __name__=='__main__':unittest.main()
