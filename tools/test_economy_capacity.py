import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from collections import Counter

from economy_capacity import capped_allocation,write_land
from economy_model import Target
from economy_market import components,coastal
from economy_source_structure import profile
from extract_military_source import extract
from extract_m3_politics import fields
from pdx_text import root
from unittest.mock import patch


class CapacityTests(unittest.TestCase):
    def test_railways_recheck_transport_demand_created_by_automation(self):
        from complete_economy import provision_rails
        rows=[{'building':'factory','levels':1,'pms':[],'demand':10}]
        def coefficients(kind,pms,techs):
            return {'jobs':0,'inputs':{},'outputs':{'transportation':10} if kind=='building_railway' else {}}
        target=SimpleNamespace(infrastructure_usage=lambda k:0,
            infrastructure=lambda s,p,t,rs:100+20*sum(r['levels'] for r in rs if r['building']=='building_railway'),coefficients=coefficients)
        ledger=SimpleNamespace(population={('A','X'):10000},techs={'X':set()},target=target,changes=[],
            allowed=lambda k,t:True,local=lambda s,t:rows,pms=lambda k,t:[],capped_room=lambda s,t,k:100)
        ledger.coefficients=lambda r: coefficients(r['building'],[],set()) if r['building']=='building_railway' else {'inputs':{'transportation':r['demand']},'outputs':{}}
        def add(s,t,k,n,reason,pms):
            if n:
                rows.append({'building':k,'levels':n,'pms':pms});ledger.changes.append(n)
        ledger.add=add
        def automate(*args,**kwargs): rows[0]['demand']=30
        with patch('complete_economy.workforce_room',side_effect=automate): provision_rails(ledger,{'X'})
        self.assertEqual(sum(r['levels'] for r in rows if r['building']=='building_railway'),3)

    def test_omitted_and_reordered_history_methods_are_completed_by_group(self):
        t=Target.__new__(Target)
        t.buildings={'factory':{'production_method_groups':root('main automation extra')}}
        t.groups={g:{'production_methods':root(p)} for g,p in {'main':'hand machine','automation':'manual steam','extra':'off on'}.items()}
        self.assertEqual(t.complete_methods('factory',['steam','machine'],['hand','manual','off']),['machine','steam','off'])
        with self.assertRaises(ValueError): t.complete_methods('factory',['hand','machine'],['hand','manual','off'])
        with self.assertRaises(ValueError): t.complete_methods('factory',['foreign'],['hand','manual','off'])

    def test_capped_allocation_redistributes_and_reports_unrepresented(self):
        values,missing = capped_allocation({'a':100,'b':1},30,{'a':5,'b':20})
        self.assertEqual(values,{'a':5,'b':20});self.assertEqual(missing,5)
        values,missing = capped_allocation({'a':0,'b':0},8,{'a':3,'b':9})
        self.assertEqual(sum(values.values()),8);self.assertEqual(missing,0)

    def test_law_unlocks_are_alternatives_and_empty_geographic_list_is_unrestricted(self):
        t=Target.__new__(Target)
        t.pms={'p':dict(root('unlocking_laws={tenant owner} unlocking_geographic_regions={}').entries())}
        self.assertTrue(t.available('p',set(),{'owner'}))
        self.assertFalse(t.available('p',set(),{'serfdom'}))
        t.pms['p']['disallowing_laws']=root('owner')
        self.assertFalse(t.available('p',set(),{'owner'}))

    def test_foreign_land_does_not_connect_domestic_components(self):
        owners={'A':{'x000001':'X'},'B':{'x000002':'Y'},'C':{'x000003':'X'}}
        actual=components(owners,[('x000001','x000002'),('x000002','x000003')],{('A','X'):1,('B','Y'):1,('C','X'):1})
        self.assertEqual(len(actual),3)

    def test_split_state_coast_does_not_require_owning_vanilla_port_marker(self):
        ledger=SimpleNamespace(target=SimpleNamespace(states={'A':{'port':'x000001'}}),
                               owners={'A':{'x000001':'X','x000002':'Y'}},coastal_provinces={'x000002'})
        self.assertTrue(coastal(ledger,'A','Y'))
        self.assertFalse(coastal(ledger,'A','X'))

    def test_source_waged_farming_is_not_mistaken_for_manufacturing(self):
        with TemporaryDirectory() as d:
            eu5=Path(d);p=eu5/'in_game/common/building_types';p.mkdir(parents=True)
            (p/'test.txt').write_text('farm={pop_type=laborers unique_production_methods={pm={produced=fiber_crops}}}')
            source={'locations':{'1':{'name':'town','raw_material':'wheat','rgo_workers':2000,
                     'class_employment':{'laborers':{'employed_in_rgo':1500},'peasants':{'employed_in_rgo':500}}}},
                    'buildings':[{'type':'farm','location':'1','level':'5','employed':'1'}]}
            ag,resource,report=profile(source,eu5,{'town':{('A','X'):.4,('B','X'):.6}})
            self.assertEqual(sum(ag.values()),2500) # total employed=1000, NOT 1000*5 levels
            self.assertEqual(report['countries']['X']['paid_agriculture'],1000)
            self.assertEqual(report['countries']['X']['rgo'],2000)

    def test_levy_pop_lists_and_mercenary_ids_are_not_regular_soldiers(self):
        with TemporaryDirectory() as d:
            base=Path(d);defs=base/'in_game/common/unit_types';defs.mkdir(parents=True)
            (defs/'units.txt').write_text('base={category=army_heavy_infantry max_strength=2.5} infantry={copy_from=base}')
            save=base/'sample.eu5'
            save.write_text('''unit_manager={database={10={country=1 is_army=yes}}}
            subunit_manager={database={1={owner=1 type=infantry levies={99}}
            2={owner=1 type=infantry mercenary=123} 3={owner=1 type=infantry}
            4={owner=1 type=infantry prisoner=yes}}}''')
            output=base/'result.json';extract(save,base,output)
            data=json.loads(output.read_text());rows={r['id']:r for r in data['subunits']}
            self.assertTrue(rows['1']['levies']);self.assertTrue(rows['2']['mercenary'])
            self.assertFalse(rows['3']['levies']);self.assertEqual(rows['3']['establishment_persons'],2500)
            self.assertIsNone(rows['3']['serialized_strength']);self.assertNotIn('4',rows)

    def test_capacity_edits_preserve_provinces_and_other_state_definitions(self):
        with TemporaryDirectory() as d:
            base=Path(d);game=base/'game';directory=game/'map_data/state_regions';directory.mkdir(parents=True)
            text='A={\n arable_land=10\n provinces={x000001 x000002}\n capped_resources={mine=2}\n}\nB={arable_land=4}'
            (directory/'states.txt').write_text(text)
            target=SimpleNamespace(game=game,states={'A':{'capped_resources':root('mine=5 wood=7')}})
            out=base/'out';write_land(target,base/'empty_mod',out,{'A':30},{'A':{'mine':5}})
            doc=root((out/'map_data/state_regions/states.txt').read_text(encoding='utf-8-sig')).fields()
            self.assertEqual(fields(doc['A'])['arable_land'],'30')
            self.assertEqual(fields(doc['A'])['provinces'].text(),'x000001 x000002')
            self.assertEqual(fields(fields(doc['A'])['capped_resources']),{'mine':'5','wood':'7'})
            self.assertEqual(doc['B'].text(),'arable_land=4')


if __name__=='__main__': unittest.main()
