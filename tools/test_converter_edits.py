from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from converter_edits import materialize,resize_building,write_geography,rewrite_hosts,rewrite_investor_locations,plan_bulk,plan_population
from converter_reconcile import reconcile
from converter_world import STATES,POPS,BUILDINGS
from converter_project import DEFAULTS
from converter_export import export_candidate
from pdx_text import root
from build_m2_prototype import objects
from economy_model import building_rows,definitions

class EditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
        self.mod=self.base/'source';self.game=self.base/'game';self.game.mkdir()
        text='STATES={s:S={create_state={country=c:AAA owned_provinces={x000001 x000002}} create_state={country=c:BBB owned_provinces={x000003}}} s:T={create_state={country=c:AAA owned_provinces={x000004}}}}'
        files={STATES:text,POPS:'POPS={}',BUILDINGS:'BUILDINGS={s:S={region_state:AAA={create_building={building=farm level=5 activate_production_methods={manual}}}}}',
               'common/country_definitions/a.txt':'AAA={capital=S} BBB={capital=S}',
               'common/history/diplomacy/a.txt':'DIPLOMACY={c:BBB ?={create_diplomatic_pact={country=c:AAA type=vassal}}}',
               'common/history/treaties/a.txt':'TREATIES={create_treaty={name=a first_country=c:AAA second_country=c:BBB}}',
               'map_data/state_regions/a.txt':'S={arable_land=10 provinces={x000001 x000002 x000003} city=x000002 farm=x000001} T={arable_land=20 provinces={x000004} city=x000004}'}
        for rel,body in files.items():
            path=self.mod/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body)
        target=SimpleNamespace(states=definitions(self.mod/'map_data/state_regions'),buildings={'farm':{},'mill':{}},
            select=lambda *a:['manual'],available=lambda *a:True,complete_methods=lambda kind,pms,defaults:pms,
            coefficients=lambda *a:{'jobs':5,'inputs':{},'outputs':{}})
        self.world=SimpleNamespace(mod=self.mod,game=self.game,parts={
            'S|AAA':dict(state='S',country='AAA',provinces=['x000001','x000002']),
            'S|BBB':dict(state='S',country='BBB',provinces=['x000003']),
            'T|AAA':dict(state='T',country='AAA',provinces=['x000004'])},
            edges=[('x000001','x000002'),('x000002','x000003'),('x000002','x000004')],
            state_objects=dict(objects(root(text).fields()['STATES'])),target=target,
            population=Counter({('S','AAA','c','r'):101,('S','BBB','c','r'):40,('T','AAA','c','r'):10}),
            buildings=building_rows(self.mod/BUILDINGS),techs={'AAA':set(),'BBB':set()},laws={'AAA':set(),'BBB':set()},
            countries={'AAA':{},'BBB':{}},report={},fingerprint='fixture',verify_unchanged=lambda:None,
            preview=lambda *a:dict(rows=[],assumptions=[]))

    def test_partial_capital_transfer_selects_remaining_populated_state(self):
        view=materialize(self.world,[dict(kind='region',state='S',source='AAA',target='BBB')])
        files,notes=reconcile(self.world,view)
        self.assertIn('capital = T',files['common/country_definitions/a.txt'])
        self.assertTrue(any('迁都' in n for n in notes))
        self.assertFalse(view._edit_aliases)

    def test_country_subject_merge_removes_self_pact_and_internal_treaty(self):
        view=materialize(self.world,[dict(kind='country',source='AAA',target='BBB')])
        files,notes=reconcile(self.world,view)
        self.assertNotIn('create_diplomatic_pact',files['common/history/diplomacy/a.txt'])
        self.assertNotIn('create_treaty',files['common/history/treaties/a.txt'])
        self.assertEqual(sum(view.population.values()),151)
        self.assertEqual(sum(b['levels'] for b in view.buildings),5)

    def test_last_region_becomes_full_country_merge(self):
        view=materialize(self.world,[dict(kind='region',state='S',source='BBB',target='AAA')])
        self.assertEqual(view._edit_aliases,{'BBB':'AAA'})

    def test_cross_state_province_moves_conserve_population_buildings_and_map(self):
        view=materialize(self.world,[dict(kind='province',provinces=['x000002'],target='AAA',target_state='T')])
        self.assertEqual(sum(view.population.values()),151)
        self.assertEqual(view.population['S','AAA','c','r'],51)
        self.assertEqual(view.population['T','AAA','c','r'],60)
        self.assertEqual(sum(b['levels'] for b in view.buildings),5)
        write_geography(view,self.base/'output',1)
        states=definitions(self.base/'output/map_data/state_regions')
        self.assertNotIn('x000002',states['S']['provinces'].text())
        self.assertIn('x000002',states['T']['provinces'].text())
        self.assertNotEqual(states['S']['city'],'x000002')

    def test_empty_state_and_nonadjacent_transfer_rejected_without_mutating_input(self):
        for provinces,target,state in [(['x000004'],'BBB','S'),(['x000001'],'BBB','S')]:
            with self.assertRaises(ValueError):materialize(self.world,[dict(kind='province',provinces=provinces,target=target,target_state=state)])
        self.assertEqual(self.world.population['S','AAA','c','r'],101)

    def test_levels_and_whole_state_arable_export_and_readback(self):
        ops=[dict(kind='arable',state='S',value=37),dict(kind='building',state='S',country='AAA',levels={'farm':2,'mill':3})]
        view=materialize(self.world,ops)
        self.assertEqual({r['building']:r['levels'] for r in view.buildings},{'farm':2,'mill':3})
        result=export_candidate(self.world,dict(settings=DEFAULTS,merges=ops),self.base/'export')
        self.assertEqual(result['building_levels'],5)
        self.assertEqual(definitions(self.base/'export/eu5_converted/map_data/state_regions')['S']['arable_land'],'37')
        self.assertEqual(self.world.target.states['S']['arable_land'],'10')

    def test_proportional_investor_tranches_preserved(self):
        row=dict(building='farm',levels=5,body='building=farm add_ownership={building={country=c:AAA region=S levels=3} building={country=c:BBB region=T levels=2}}')
        resized=resize_building(row,3)
        self.assertIn('country=c:AAA region=S levels=2',resized['body'])
        self.assertIn('country=c:BBB region=T levels=1',resized['body'])

    def test_merge_opposing_war_sides_retires_war(self):
        path=self.mod/'common/history/diplomatic_plays/a.txt';path.parent.mkdir()
        path.write_text('DIPLOMATIC_PLAYS={c:AAA ?={create_diplomatic_play={name=w target_country=c:BBB}}}')
        view=materialize(self.world,[dict(kind='country',source='AAA',target='BBB')])
        files,notes=reconcile(self.world,view)
        self.assertNotIn('create_diplomatic_play',files['common/history/diplomatic_plays/a.txt'])
        self.assertTrue(any('战争' in n for n in notes))

    def test_foreign_investor_district_follows_removed_region(self):
        view=materialize(self.world,[dict(kind='region',state='S',source='AAA',target='BBB')])
        body='add_ownership={building={country=c:AAA region=S levels=2} building={country=c:AAA region=T levels=3}}'
        changed=rewrite_hosts(body,view)
        self.assertIn('country=c:BBB region=S levels=2',changed)
        self.assertIn('country=c:AAA region=T levels=3',changed)
        body='add_ownership={building={country=c:AAA region=S levels=2} building={country=c:BBB region=S levels=3}}'
        changed=rewrite_investor_locations(body,{('S','AAA'):('T','AAA')})
        self.assertIn('country=c:AAA region=T levels=2',changed)
        self.assertIn('country=c:BBB region=S levels=3',changed)

    def test_subject_merge_does_not_invent_cycle_or_second_overlord(self):
        path=self.mod/'common/history/diplomacy/a.txt'
        path.write_text('DIPLOMACY={c:CCC={create_diplomatic_pact={country=c:BBB type=vassal}} c:AAA={create_diplomatic_pact={country=c:CCC type=vassal}}}')
        view=materialize(self.world,[dict(kind='country',source='AAA',target='BBB')])
        files,notes=reconcile(self.world,view)
        body=files['common/history/diplomacy/a.txt']
        self.assertEqual(body.count('create_diplomatic_pact'),1)
        self.assertTrue(any('成环' in n for n in notes))

    def test_unrelated_multi_organization_leader_preserved(self):
        path=self.mod/'common/history/power_blocs/a.txt';path.parent.mkdir()
        path.write_text('POWER_BLOCS={c:CCC={create_power_bloc={name=a member=c:DDD} create_power_bloc={name=b member=c:EEE}}}')
        view=materialize(self.world,[dict(kind='country',source='AAA',target='BBB')])
        files,notes=reconcile(self.world,view)
        self.assertEqual(files['common/history/power_blocs/a.txt'].count('create_power_bloc'),2)

    def test_barracks_edit_updates_existing_formation_count(self):
        self.world.target.buildings['building_barrack']={}
        self.world.buildings[0]['building']='building_barrack'
        self.world.buildings[0]['body']=self.world.buildings[0]['body'].replace('building=farm','building=building_barrack')
        path=self.mod/'common/history/military_formations/a.txt';path.parent.mkdir()
        path.write_text('MILITARY_FORMATIONS={c:AAA={create_military_formation={type=army hq_region=sr:region combat_unit={type=unit_type:combat_unit_type_irregular_infantry state_region=s:S count=5}}}}')
        view=materialize(self.world,[dict(kind='building',state='S',country='AAA',levels={'building_barrack':2})])
        files,notes=reconcile(self.world,view)
        self.assertIn('count = 2',files['common/history/military_formations/a.txt'])
        self.assertNotIn('count = 5',files['common/history/military_formations/a.txt'])
        self.assertTrue(any('营数同步' in n for n in notes))

    def test_bulk_uses_largest_province_owner_and_either_risk(self):
        rows=[dict(state='S',country=t,province_count=n,risks=risks) for t,n,risks in [('AAA',5,[]),('BBB',1,['food']),('CCC',2,['unemployment']),('DDD',3,['arable'])]]
        op=plan_bulk(rows)
        self.assertEqual([m['source'] for m in op['transfers']],['BBB','CCC'])
        self.assertEqual({m['target'] for m in op['transfers']},{'AAA'})
        self.assertEqual(len(plan_bulk(rows,'state','S')['transfers']),3)
        rows[1]['province_count']=5
        self.assertEqual({m['target'] for m in plan_bulk(rows)['transfers']},{'AAA'})

    def test_bulk_atomic_transfer_and_one_replay_undo(self):
        op=dict(kind='bulk',transfers=[dict(state='S',source='BBB',target='AAA')])
        view=materialize(self.world,[op])
        self.assertEqual(view._bulk_outcomes[-1]['applied'],1)
        self.assertEqual(view.owners['S']['x000003'],'AAA')
        self.assertEqual(sum(view.population.values()),151)
        original=materialize(self.world,[])
        self.assertEqual(original.owners['S']['x000003'],'BBB')

    def test_bulk_skips_incompatible_region_but_applies_others(self):
        self.world.parts['S|CCC']=dict(state='S',country='CCC',provinces=['x000005'])
        self.world.population['S','CCC','c','r']=20
        self.world.techs['CCC']=set();self.world.laws['CCC']=set()
        self.world.target.buildings['locked']={'unlocking_technologies':root('future')}
        self.world.buildings.append(dict(state='S',owner='BBB',building='locked',levels=1,pms=['manual'],guards=(),body='building=locked level=1 activate_production_methods={manual}'))
        op=dict(kind='bulk',transfers=[dict(state='S',source=t,target='AAA') for t in ('BBB','CCC')])
        view=materialize(self.world,[op]);outcome=view._bulk_outcomes[-1]
        self.assertEqual((outcome['requested'],outcome['applied']),(2,1))
        self.assertEqual(view.owners['S']['x000003'],'BBB')
        self.assertEqual(view.owners['S']['x000005'],'AAA')
        self.assertEqual(outcome['skipped'][0]['source'],'BBB')

    def test_incremental_replay_matches_full_replay(self):
        first=[dict(kind='region',state='S',source='BBB',target='AAA')]
        materialize(self.world,first)
        ops=first+[dict(kind='building',state='S',country='AAA',levels={'farm':8})]
        incremental=materialize(self.world,ops)
        self.world._edit_cache=None
        complete=materialize(self.world,ops)
        self.assertEqual(incremental.population,complete.population)
        self.assertEqual(incremental.buildings,complete.buildings)
        self.assertEqual(incremental.owners,complete.owners)
        self.assertEqual(incremental._edit_aliases,complete._edit_aliases)

    def test_demolition_requires_explicit_choice_and_undo_restores_buildings(self):
        self.world.target.buildings['locked']={'unlocking_technologies':root('future')}
        self.world.buildings.append(dict(state='S',owner='BBB',building='locked',levels=3,pms=['manual'],guards=(),body='building=locked level=3 activate_production_methods={manual}'))
        op=dict(kind='bulk',transfers=[dict(state='S',source='BBB',target='AAA')])
        skipped=materialize(self.world,[op]);self.assertEqual(skipped._bulk_outcomes[-1]['applied'],0)
        self.assertEqual(skipped._bulk_outcomes[-1]['conflicts'][0]['levels'],3)
        self.assertEqual(sum(r['levels'] for r in skipped.buildings),8)
        automatic=dict(op,demolish=True);view=materialize(self.world,[automatic])
        self.assertEqual(view._bulk_outcomes[-1]['applied'],1)
        self.assertEqual(view._bulk_outcomes[-1]['demolitions'][0]['building'],'locked')
        self.assertEqual(sum(r['levels'] for r in view.buildings),5)
        self.assertEqual(sum(view.population.values()),151)
        result=export_candidate(self.world,dict(settings=DEFAULTS,merges=[automatic]),self.base/'demolished')
        self.assertEqual(result['building_levels'],5)
        restored=materialize(self.world,[])
        self.assertEqual(sum(r['levels'] for r in restored.buildings),8)
        self.assertEqual(restored.owners['S']['x000003'],'BBB')

    def test_food_sources_select_different_parts_and_record_reasons(self):
        rows=[dict(state='S',country=t,province_count=n,risks=[],market_food_shortfall=market,local_food_shortfall=local)
              for t,n,market,local in [('AAA',5,0,0),('BBB',1,0,.9),('CCC',1,.6,0),('DDD',1,None,None)]]
        local=plan_bulk(rows,risks=['local_food']);market=plan_bulk(rows,risks=['market_food'])
        self.assertEqual([m['source'] for m in local['transfers']],['BBB'])
        self.assertEqual([m['source'] for m in market['transfers']],['CCC'])
        self.assertEqual(market['transfers'][0]['reasons'],['market_food'])
        with self.assertRaises(ValueError):plan_bulk(rows,risks=['market_food'],food_threshold=.8)

    def test_strategic_majority_spans_states_and_can_enter_new_state(self):
        rows=[dict(state=s,country=t,province_count=n,risks=['food'],strategic_region='region')
              for s,t,n in [('S','AAA',2),('S','BBB',1),('T','AAA',1)]]
        op=plan_bulk(rows,grouping='strategic_region');self.assertEqual(op['transfers'][0]['target'],'AAA')
        # T is a different state owned solely by AAA; BBB holds the majority in S
        # only after adding a larger province count in the actual fixture.
        self.world.parts['S|BBB']['provinces']+=['x000005','x000006','x000007']
        self.world.strategic_regions={'S':'region','T':'region'}
        rows=[dict(state=r['state'],country=r['country'],province_count=len(r['provinces']),risks=['food'],strategic_region='region') for r in self.world.parts.values()]
        op=plan_bulk(rows,grouping='strategic_region');view=materialize(self.world,[op])
        self.assertEqual(view.owners['T']['x000004'],'BBB')
        self.assertEqual(view._bulk_outcomes[-1]['applied'],2)
        self.assertEqual(sum(view.population.values()),151)
        self.assertEqual(sum(r['levels'] for r in view.buildings),5)
        self.assertEqual(materialize(self.world,[]).owners['T']['x000004'],'AAA')

    def test_population_batch_preserves_composition_buildings_and_undo(self):
        self.world.population['S','AAA','other','r']=99
        self.world.preview=lambda *a:dict(rows=[dict(id='S|AAA',state='S',country='AAA',job_capacity=10),dict(id='S|BBB',state='S',country='BBB',job_capacity=None)])
        op=plan_population(self.world,DEFAULTS,[],['S|AAA','S|BBB'],percent=50)
        view=materialize(self.world,[op])
        self.assertEqual(view.population['S','AAA','c','r'],51)
        self.assertEqual(view.population['S','AAA','other','r'],49)
        self.assertEqual(view.population['S','BBB','c','r'],20)
        self.assertEqual(view.population['T','AAA','c','r'],10)
        self.assertEqual(sum(r['levels'] for r in view.buildings),5)
        # Export fixture supplies a compact preview; replay and readback still check all populations.
        self.world.preview=lambda *a:dict(rows=[],assumptions=[])
        result=export_candidate(self.world,dict(settings=DEFAULTS,merges=[op]),self.base/'population-export')
        self.assertEqual(result['population'],130)
        self.assertEqual(sum(materialize(self.world,[]).population.values()),250)

    def test_population_jobs_mode_skips_unknown_and_rejects_stale_counts(self):
        self.world.preview=lambda *a:dict(rows=[dict(id='S|AAA',state='S',country='AAA',job_capacity=10),dict(id='S|BBB',state='S',country='BBB',job_capacity=None)])
        op=plan_population(self.world,DEFAULTS,[],['S|AAA','S|BBB'],mode='jobs')
        self.assertEqual(op['targets'][0]['value'],40);self.assertEqual(op['skipped_unknown'],['S|BBB'])
        self.world.population['S','AAA','c','r']=102
        self.world._edit_cache=None
        with self.assertRaisesRegex(ValueError,'已变化'):materialize(self.world,[op])

if __name__=='__main__':unittest.main()
