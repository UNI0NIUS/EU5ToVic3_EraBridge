import unittest
from terrain_connectivity import complete, source_seeds, require_export_ready


def seed(owner,kind='source_owned'):
    return {'owner':owner,'kind':kind}


class ConnectivityTests(unittest.TestCase):
    def test_entire_empty_state_is_filled_across_state_border(self):
        p=complete({'a':'S1','b':'S2','c':'S2'},[('a','b'),('b','c')],{'a':seed('source:1')})
        self.assertTrue(p['export_ready']);self.assertEqual(p['provinces']['c']['owner'],'source:1')
        self.assertEqual(p['provinces']['c']['distance'],2)
    def test_old_inferred_or_vanilla_owner_is_not_a_seed(self):
        for kind in ['unmapped_vanilla','land_inferred','wasteland']:
            with self.assertRaises(ValueError):complete({'a':'S'},[],{'a':seed('RUS',kind)})
    def test_no_anchor_is_reported_and_blocks_export(self):
        p=complete({'a':'S','b':'S'},[('a','b')],{})
        self.assertEqual(p['summary']['unresolved_provinces'],2)
        with self.assertRaises(ValueError):require_export_ready(p)
    def test_island_is_not_assigned_across_sea(self):
        p=complete({'mainland':'S','island':'S'},[],{'mainland':seed('source:1')})
        self.assertNotIn('island',p['provinces']);self.assertFalse(p['export_ready'])
    def test_reviewed_island_is_a_valid_explicit_anchor(self):
        p=complete({'island':'S'},[],{'island':seed('source:1','reviewed')})
        self.assertTrue(p['export_ready'])
    def test_native_components_merge_after_terrain_across_state_border(self):
        p=complete({'a':'S1','b':'S1','c':'S2'},[('a','b'),('b','c')],
                   {'a':seed('native:c','source_native_population'),'c':seed('native:c','source_native_population')},{'native:c':'c'})
        self.assertEqual(len(p['native_components']),1)
        self.assertEqual(p['native_components'][0]['states'],['S1','S2'])
    def test_same_culture_separate_islands_remain_separate_countries(self):
        p=complete({'a':'S','b':'S'},[],{'a':seed('native:c','source_native_population'),'b':seed('native:c','source_native_population')},{'native:c':'c'})
        self.assertEqual(len(p['native_components']),2)
    def test_foreign_country_is_a_barrier(self):
        p=complete({'a':'S','b':'S','c':'S'},[('a','b'),('b','c')],{'a':seed('source:1'),'b':seed('source:2')})
        self.assertEqual(p['provinces']['c']['owner'],'source:2')
    def test_tied_frontier_is_visible_and_deterministic(self):
        p=complete({'a':'S','b':'S','c':'S'},[('a','b'),('b','c')],{'c':seed('source:2'),'a':seed('source:1')})
        self.assertEqual(p['provinces']['b']['equidistant_owners'],['source:1','source:2'])
        self.assertEqual(p['provinces']['b']['root'],'a')
    def test_no_seed_leaks_across_unconnected_continents(self):
        p=complete({'a':'A','b':'B','c':'B'},[('b','c')],{'a':seed('source:1')})
        self.assertEqual(p['summary']['unresolved_components'],1)
        self.assertEqual(set(p['unresolved_components'][0]['provinces']),{'b','c'})
    def test_seed_identity_changes_with_save_not_target_template(self):
        loc={'place':{'owner':0,'population_persons':'10'}}
        s,n,_=source_seeds({'p':'S'},{'p':['place']},loc,set(),{'place':{'c':1000}})
        self.assertEqual(s['p']['owner'],'native:c')
        loc['place']['owner']=42
        s,n,_=source_seeds({'p':'S'},{'p':['place']},loc,set(),{'place':{'c':1000}})
        self.assertEqual(s['p']['owner'],'source:42')
    def test_nonownable_white_does_not_invent_native_population(self):
        s,n,q=source_seeds({'p':'S'},{'p':['mountain']},{'mountain':{'owner':0,'population_persons':'0'}},{'mountain'}, {})
        self.assertFalse(s);self.assertFalse(n)
    def test_reviewed_geography_weights_affect_native_majority(self):
        places={n:{'owner':0,'population_persons':'10'} for n in ['first','second']}
        seeds,_,_=source_seeds({'p':'S','q':'S'},{'p':['first','second'],'q':['first']},places,set(),
                               {'first':{'a':1000},'second':{'b':200}},location_weights={'first':{'p':1,'q':9}})
        self.assertEqual(seeds['p']['source_culture'],'b')
    def test_tag_pool_exceeds_one_prefix_and_remains_deterministic(self):
        from native_country_tags import allocate
        names=[f'native:c{i}' for i in range(1700)];reserved={'U00','AAA','E01'}
        a=allocate(names,reserved);b=allocate(reversed(names),reserved)
        self.assertEqual(a,b);self.assertEqual(len(set(a.values())),1700)
        self.assertFalse(set(a.values())&reserved)
        self.assertTrue(all(len(t)==3 and t[0].isalpha() and t.isalnum() for t in a.values()))
        self.assertGreater(len({t[0] for t in a.values()}),1)


if __name__=='__main__':unittest.main()
