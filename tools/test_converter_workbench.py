import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from collections import Counter
from converter_project import DEFAULTS,settings,apportion,assess,resolve_merges
from converter_export import scoped,rewrite_investors,merged_buildings,export_candidate
from converter_world import POPS,STATES,BUILDINGS
from pdx_text import root
from build_m2_prototype import objects

PARTS={'S|AAA':dict(state='S',country='AAA',provinces=['x000001']),
       'S|BBB':dict(state='S',country='BBB',provinces=['x000002']),
       'T|AAA':dict(state='T',country='AAA',provinces=['x000003']),
       'T|CCC':dict(state='T',country='CCC',provinces=['x000004'])}
EDGES=[('x000001','x000002'),('x000001','x000003'),('x000003','x000004')]

class RulesTests(unittest.TestCase):
    def test_independence_routing_uses_current_evidence(self):
        from converter_source_wars import war_route
        war=dict(id='new-campaign-id',goals=[dict(kind='independence')])
        with self.assertRaises(ValueError):war_route(war)
        self.assertEqual(war_route(dict(war,dependency=[['first','A'],['second','B']])), 'native_independence_with_suspended_dependency_bridge')
        self.assertEqual(war_route(dict(war,revolt='current-revolt')), 'native_secession_bridge')
        self.assertEqual(war_route(dict(goals=[dict(kind='take_capital')])), 'one_state_territorial_goal')
    def test_empty_template_preserves_current_source_borders(self):
        from converter_empty_templates import apply_ownership
        w=SimpleNamespace(mapping={'x1':[],'x2':[]},province_state={'x1':'S','x2':'S'},owners={'S':{'x1':'AAA','x2':'BBB'}},
                          countries={'AAA':dict(source_id='1'),'BBB':dict(source_id='2')},country_defs={})
        result=apply_ownership(w,{}, {},{'empty_state_templates':{'S':'NAT'},'empty_state_owner_modes':{'S':'join_adjacent_same_template_culture'}})
        self.assertEqual(w.owners['S'],{'x1':'AAA','x2':'BBB'});self.assertEqual(result['S']['owners'],{'AAA':1,'BBB':1})
    def test_template_people_distributed_without_new_country(self):
        from converter_empty_templates import template_groups
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);(td/'common/cultures').mkdir(parents=True);(td/'common/history/pops').mkdir(parents=True)
            (td/'common/cultures/a.txt').write_text('a = { religion = r }',encoding='utf8')
            (td/'common/history/pops/a.txt').write_text('POPS = { s:S = { region_state:NAT = { create_pop = { culture = a size = 101 } } } }',encoding='utf8')
            groups,_=template_groups(td,{'S':{'owners':{'AAA':1,'BBB':2}}},{},{'S':{'x1':'AAA','x2':'BBB','x3':'BBB'}})
            self.assertEqual(sum(groups.values()),101);self.assertEqual({k[1] for k in groups},{'AAA','BBB'})
    def test_generated_country_without_definition_still_checks_tag(self):
        from extract_m3_politics import validate_audit_document
        doc=root('metadata = { date = 1700.1.1 } locations = { locations = {} } countries = { tags = { 7 = AAA11 } database = { 7 = { type = location } } }').fields()
        audit=dict(errors=[],date='1700.1.1',locations=[],countries=[dict(id=7,definition='',tag='AAA11')])
        validate_audit_document(doc,audit)
        audit['countries'][0]['tag']='WRONG'
        with self.assertRaises(ValueError):validate_audit_document(doc,audit)
    def test_inclusive_arable_not_province_count(self):
        for land,risk in [(0,True),(3,True),(4,False)]:
            r=assess(dict(population=100,arable=land,province_count=100,job_capacity=25,food_supply=10,food_demand=10),DEFAULTS)
            self.assertEqual('arable' in r['risks'],risk)
    def test_unknown_is_not_zero(self):
        r=assess(dict(population=100,arable=4,job_capacity=None,food_supply=None,food_demand=10),DEFAULTS)
        self.assertIsNone(r['estimated_unemployment']);self.assertIsNone(r['food_shortfall']);self.assertEqual(r['risks'],[])
    def test_unemployment_and_food_are_independent(self):
        r=assess(dict(population=100,arable=4,job_capacity=10,food_supply=10,food_demand=10),DEFAULTS)
        self.assertEqual(r['risks'],['unemployment'])
        r=assess(dict(population=100,arable=4,job_capacity=25,food_supply=5,food_demand=10),DEFAULTS)
        self.assertEqual(r['risks'],['food'])
    def test_exact_food_threshold_is_inclusive_despite_float_rounding(self):
        r=assess(dict(population=100,arable=4,job_capacity=25,food_supply=80,food_demand=100),DEFAULTS)
        self.assertIn('food',r['risks'])
    def test_zero_population_no_division(self):
        r=assess(dict(population=0,arable=0,job_capacity=0,food_supply=0,food_demand=0),DEFAULTS)
        self.assertEqual(r['estimated_unemployment'],0);self.assertEqual(r['food_shortfall'],0)
    def test_apportion_never_invents_land(self):
        for total in range(15):
            self.assertEqual(sum(apportion(total,{'A':2,'B':3,'C':7}).values()),total)
        self.assertEqual(apportion(1,{'B':1,'A':1}),{'B':0,'A':1})
    def test_invalid_numeric_parameters(self):
        for bad in [float('nan'),float('inf'),True,-1,6,'1']:
            with self.assertRaises(ValueError):settings(dict(population_multiplier=bad))
        with self.assertRaises(ValueError):settings(dict(small_arable=3.5))
    def test_region_transfer_preserves_other_state(self):
        owners,aliases,transfers,_=resolve_merges(PARTS,[dict(kind='region',state='S',source='AAA',target='BBB')],EDGES)
        self.assertEqual(owners['x000001'],'BBB');self.assertEqual(owners['x000003'],'AAA');self.assertFalse(aliases)
        self.assertEqual(transfers,{('S','AAA'):'BBB'})
    def test_country_chain_resolves_survivor(self):
        ops=[dict(kind='country',source='BBB',target='AAA'),dict(kind='country',source='AAA',target='CCC')]
        owners,aliases,_,_=resolve_merges(PARTS,ops,EDGES)
        self.assertEqual(set(owners.values()),{'CCC'});self.assertEqual(aliases,{'BBB':'CCC','AAA':'CCC'})
    def test_sea_and_cross_state_region_merge_rejected(self):
        for op in [dict(kind='country',source='BBB',target='CCC'),dict(kind='region',state='S',source='AAA',target='CCC')]:
            with self.assertRaises(ValueError):resolve_merges(PARTS,[op],EDGES)
    def test_last_region_requires_country_operation(self):
        with self.assertRaises(ValueError):resolve_merges(PARTS,[dict(kind='region',state='S',source='BBB',target='AAA')],EDGES)
    def test_investor_transfer_uses_exact_host(self):
        body='add_ownership = { building = { country = "c:AAA" region = "S" levels = 2 } building = { country = c:AAA region = T levels = 3 } }'
        changed=rewrite_investors(body,{('S','AAA'):'BBB'})
        self.assertIn('country = "c:BBB" region = "S"',changed);self.assertIn('country = c:AAA region = T',changed)
    def test_scoped_tags_do_not_replace_prefixes(self):
        self.assertEqual(scoped('c:AAA c:AAAA region_state:AAA AAA_label',{'AAA':'BBB'}),'c:BBB c:AAAA region_state:BBB AAA_label')
    def test_building_method_conflict_is_not_silent(self):
        a=dict(state='S',owner='AAA',building='farm',levels=1,pms=['p1'],guards=(),body='building = farm level = 1')
        with self.assertRaises(ValueError):merged_buildings([a,dict(a,pms=['p2'])])
    def test_building_levels_combine(self):
        a=dict(state='S',owner='AAA',building='farm',levels=1,pms=['p1'],guards=(),body='building = farm level = 1 activate_production_methods = { p1 }')
        row=merged_buildings([a,a])[0];self.assertEqual(row['levels'],2);self.assertIn('level = 2',row['body'])

class ExportTests(unittest.TestCase):
    def test_real_files_country_merge_population_and_building_conservation(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);mod=td/'source';mod.mkdir()
            data={STATES:'STATES = { s:S = { create_state = { country = c:AAA owned_provinces = { x000001 } state_type = incorporated } create_state = { country = c:BBB owned_provinces = { x000002 } state_type = incorporated } } }',
                  POPS:'POPS = { s:S = { region_state:AAA = { create_pop = { culture = a religion = r size = 100 } } region_state:BBB = { create_pop = { culture = a religion = r size = 200 } } } }',
                  BUILDINGS:'BUILDINGS = {}',
                  'common/history/countries/world.txt':'COUNTRIES = { c:AAA ?= { activate_law = law_type:a } c:BBB ?= { activate_law = law_type:b } }',
                  'common/country_definitions/world.txt':'AAA = { capital = S } BBB = { capital = S }'}
            for rel,text in data.items():p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
            parts={k:v for k,v in PARTS.items() if v['state']=='S'}
            w=SimpleNamespace(mod=mod,parts=parts,edges=EDGES,population=Counter({('S','AAA','a','r'):100,('S','BBB','a','r'):200}),buildings=[],
                              state_objects=dict(objects(root(data[STATES]).fields()['STATES'])),countries={'AAA':{},'BBB':{}},report={},fingerprint='test',verify_unchanged=lambda:None,
                              preview=lambda *_:dict(rows=[],assumptions=[]))
            p=dict(name='test',settings=DEFAULTS,merges=[dict(kind='country',source='AAA',target='BBB')])
            result=export_candidate(w,p,td/'out')
            self.assertEqual(result['population'],300);self.assertEqual(result['provinces'],2)
            from package_m4_population_test import parse_pops
            self.assertEqual(parse_pops(td/'out/eu5_converted'/POPS),{('S','BBB','a','r'):300})
            history=(td/'out/eu5_converted/common/history/countries/world.txt').read_text(encoding='utf-8-sig')
            self.assertNotIn('law_type:a',history);self.assertIn('c:BBB ?=',history)
            for rel,text in data.items():self.assertEqual((mod/rel).read_text(encoding='utf-8'),text)
            from test_converter_i18n import localization
            localization(mod,'english',' AAA:0 "Alpha"\n BBB:0 "Beta"\n')
            localization(mod,'simp_chinese',' AAA:0 "甲国"\n BBB:0 "乙国"\n')
            result_en=export_candidate(w,dict(p,output_language='en'),td/'english')
            self.assertEqual(result_en['population'],result['population'])
            self.assertEqual((td/'english/eu5_converted'/POPS).read_bytes(),(td/'out/eu5_converted'/POPS).read_bytes())
            report=json.loads((td/'english/package_report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['output_language'],'en')
            self.assertIn('Set Victoria 3 language to English',(td/'english/README.txt').read_text(encoding='utf-8'))
            self.assertTrue((td/'english/eu5_converted/localization/simp_chinese').is_dir())
            self.assertEqual(json.loads((td/'english/localization_verification.json').read_text(encoding='utf-8'))['checked_keys'],2)
            localization(mod,'english',' AAA:0 "Alpha"\n')
            with self.assertRaisesRegex(ValueError,'Missing english localization: BBB'):
                export_candidate(w,dict(p,output_language='en'),td/'invalid')
            self.assertFalse((td/'invalid').exists())
            self.assertEqual(len(list(td.glob('invalid.building-*/FAILED.json'))),1)

class ServerTests(unittest.TestCase):
    def test_local_host_and_mutation_token_required(self):
        from converter_app import App,handler
        with tempfile.TemporaryDirectory() as td:
            app=App(td);server=ThreadingHTTPServer(('127.0.0.1',0),handler(app))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}'
            try:
                self.assertEqual(json.load(urlopen(url+'/api/status'))['job']['status'],'idle')
                for req in [Request(url+'/api/status',headers={'Host':'attacker.test'}),Request(url+'/api/restore',data=b'{}',headers={'Content-Type':'application/json'})]:
                    with self.assertRaises(HTTPError) as caught:urlopen(req)
                    self.assertEqual(caught.exception.code,403)
                req=Request(url+'/api/restore',data=b'{}',headers={'X-Converter-Token':app.token,'Origin':'https://attacker.test'})
                with self.assertRaises(HTTPError) as caught:urlopen(req)
                self.assertEqual(caught.exception.code,403)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
