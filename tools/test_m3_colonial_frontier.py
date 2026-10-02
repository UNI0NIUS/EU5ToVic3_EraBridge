import unittest
from collections import Counter
from PIL import Image
from m3_colonial_frontier import classify, plan, reallocate_original
from build_location_workstation import source_centers, wrapped_distances, wrapped_mean


class FrontierTests(unittest.TestCase):
    def setUp(self):
        self.countries={'FRA':{'source_id':'1','source_culture':'french'},
                        'U01':{'source_id':None,'generated_uncolonized':True,'culture':'french'},
                        'U02':{'source_id':None,'generated_uncolonized':True,'culture':'siberian'}}
        self.charter=[{'id':'42','source_country':'1','target_location_id':'7'}]
        self.locations={'site':{'id':7,'name':'site','owner':0}}
    def classify(self,counts,owner=0):
        self.locations['site']['owner']=owner
        return classify(self.charter,self.locations,self.countries,{'site':counts})
    def row(self,province='p',location='site',owner='0'):
        return {'target_province':province,'target_state':'S','target_owner':'U01','source_location':location,
                'source_owner':owner,'source_culture':'french','source_religion':'catholic','centipersons':'100'}
    def test_majority_requires_active_charter(self):
        self.assertEqual(classify([],self.locations,self.countries,{'site':{'french':100}}),[])
        self.assertEqual(self.classify({'french':51,'native':49})[0]['classification'],'settler_majority_active_charter')
    def test_half_is_not_majority(self):
        self.assertEqual(self.classify({'french':50,'native':50})[0]['classification'],'native_or_tied_majority_retain_native')
    def test_formal_owner_wins(self):
        self.assertEqual(self.classify({'french':100},owner=8)[0]['classification'],'source_already_owned')
    def test_only_confirmed_settlement_country_is_transferred(self):
        p=plan({'S':{'p':'U01','terrain':'U01','native':'U02'}},self.countries,self.classify({'french':80,'native':20}),[self.row()])
        self.assertEqual(p['country_aliases'],{'U01':'FRA'})
        self.assertEqual({r['province'] for r in p['changes']},{'p','terrain'})
    def test_mixed_native_locations_are_not_annexed(self):
        p=plan({'S':{'p':'U01','q':'U01'}},self.countries,self.classify({'french':100}),[self.row(),self.row('q','elsewhere')])
        self.assertFalse(p['changes']);self.assertTrue(p['unresolved'])
    def test_competing_charters_require_review(self):
        c=self.classify({'french':100});c.append(dict(c[0],target_owner='OTH'))
        p=plan({'S':{'p':'U01'}},self.countries,c,[self.row()])
        self.assertFalse(p['changes']);self.assertTrue(p['unresolved'])
    def test_inhabited_island_cannot_use_empty_island_review(self):
        with self.assertRaises(ValueError):
            plan({'S':{'p':'U01'}},self.countries,[],[self.row()],{'islands':[{'state':'S','province':'p','from':'U01','to':'U02','target_culture':'siberian'}]})
    def test_native_recheck_rejects_foreign_population(self):
        with self.assertRaises(ValueError):
            plan({'S':{'p':'RUS','q':'U02'}},self.countries,[],[self.row(owner='1')],{'native_rechecks':[{'state':'S','province':'p','from':'RUS'}]},[('p','q')],{'french':'siberian'})
    def test_relocation_keeps_exact_original_integer_total(self):
        old={('S','U01','french','catholic'):7,('T','U02','native','animist'):3}
        row=self.row()
        out=reallocate_original(old,[row],{'S':{'p':'FRA'},'T':{'island':'U02'}},{'french':'french'},{'catholic':'catholic'},{},{'site':{'state':'T','province':'island'}})
        self.assertEqual(out,{('T','U02','french','catholic'):7,('T','U02','native','animist'):3})
    def test_centroid_unwraps_map_seam(self):
        im=Image.new('RGB',(16,4),(0,0,0))
        for x in [0,1,14,15]:im.putpixel((x,2),(255,0,0))
        for x in [7,8]:im.putpixel((x,1),(0,255,0))
        points=source_centers(im,{'island':0xff0000,'inland':0x00ff00})
        self.assertEqual(points['island'],[7.75,1.0])
        self.assertEqual(points['inland'],[3.75,.5])
    def test_neighbor_search_and_projection_unwrap_seam(self):
        self.assertEqual(wrapped_distances([[8191,2],[4000,2]],[1,2],8192).argmin(),0)
        self.assertEqual(list(wrapped_mean([[8191,2],[1,2]],8192)),[0,2])


if __name__=='__main__':unittest.main()
