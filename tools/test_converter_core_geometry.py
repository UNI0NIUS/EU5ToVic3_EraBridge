import unittest,tempfile
from pathlib import Path
from converter_core_geometry import coverage,project
from converter_source_claims import reproject,REVISION
from build_m3_world import block
from pdx_text import root


class CoreBoundaryTests(unittest.TestCase):
    def test_claim_boundary_and_whole_state_denominator(self):
        ps={str(i):'STATE_A' for i in range(100)}
        self.assertFalse(coverage(map(str,range(29)),ps)[0]['claim'])
        self.assertTrue(coverage(map(str,range(30)),ps)[0]['claim'])
        ps={str(i):'STATE_ALASKA' for i in range(1028)}
        self.assertFalse(coverage(['0'],ps)[0]['claim'])

    def test_mapping_sliver_does_not_claim_a_whole_province(self):
        cores={'one':['a','a'],'both':['a','b'],'none':['z']}
        geo={'p':['a','b','c','d'],'q':['a','b','b'],'r':['z']}
        selected,_=project(cores,geo,{'p':'A','q':'A'})
        self.assertEqual(set(selected['one']),{'q'})
        self.assertEqual(set(selected['both']),{'p','q'})
        self.assertEqual(selected['none'],{})

    def test_release_is_small_even_without_a_state_claim_and_reprojects_edits(self):
        with tempfile.TemporaryDirectory() as d:
            mod=Path(d)
            p=mod/'common/history/states/00_eu5_world.txt';p.parent.mkdir(parents=True)
            p.write_text(block('STATES',block('s:OLD','create_state = { country = c:AAA owned_provinces = { p2 p3 p4 p5 } }\nadd_claim = c:DDD\nadd_claim = c:EEE\nadd_homeland = cu:test')+
                               block('s:NEW','create_state = { country = c:AAA owned_provinces = { p1 p6 } }')),encoding='utf-8-sig')
            p=mod/'common/country_definitions/zzzz_eu5_core_countries.txt';p.parent.mkdir(parents=True)
            p.write_text('DDD = { capital = OLD cultures = { test } }')
            old=dict(revision=REVISION,countries=[dict(source_id='1',tag='DDD',dormant=True,states=['OLD'],release_provinces=['p1'])],dormant_countries={'DDD':{'capital':'OLD'}},protected_claims=[['OLD','EEE']])
            result=reproject(mod,old)
            self.assertEqual(result['countries'][0]['states'],['NEW'])
            self.assertEqual(result['dormant_countries']['DDD']['capital'],'NEW')
            text=(mod/'common/country_creation/00_releasable_countries.txt').read_text(encoding='utf-8-sig')
            self.assertIn('provinces = { p1 }',text)
            self.assertNotIn('states =',text)
            states=dict(root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES'].entries())
            self.assertNotIn(('add_claim','c:DDD'),list(states['s:OLD'].entries()))
            self.assertIn(('add_claim','c:EEE'),list(states['s:OLD'].entries()))
            self.assertIn(('add_homeland','cu:test'),list(states['s:OLD'].entries()))
            self.assertIn(('add_claim','c:DDD'),list(states['s:NEW'].entries()))
            self.assertEqual(old['countries'][0]['states'],['OLD'])


if __name__=='__main__':unittest.main()
