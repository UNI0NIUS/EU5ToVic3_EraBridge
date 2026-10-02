from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from economy_fleets import BUILDING, convert, read_ships, verify
from pdx_text import root


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        game = Path(self.tmp.name)
        for directory, text in {
            'strategic_regions':'west={states={A B}} east={states={C D}}',
            'ship_types':'''heavy={modifier={ship_crew_max_add=800} unlocking_technologies={drydocks}}
                light={modifier={ship_crew_max_add=150}}''',
            'defines':'NMilitary={SAILORS_PER_BUILDING_LEVEL=1000 SAILORS_PER_ASSIGNMENT_SLOT=100}',
        }.items():
            folder=game/'common'/directory; folder.mkdir(parents=True)
            (folder/'test.txt').write_text(text)
        pms={'recruit':root('country_modifiers={workforce_scaled={country_sailors_max_add=1000}}').fields()}
        self.ledger=SimpleNamespace(target=SimpleNamespace(game=game,pms=pms,states={s:{} for s in 'ABCD'},
            coefficients=lambda *a:{'jobs':1000}),
            population={(s,'X'):100000 for s in 'ABCD'},
            owners={s:{s.lower():'X', 'foreign_'+s:'Y'} for s in 'ABCD'},
            coastal_provinces={'a','b','c','foreign_D'}, techs={'X':{'drydocks'}},rows={},
            allowed=lambda *a:True,pms=lambda *a:['recruit'])
        def put(s,t,k,n,reason,pms): self.ledger.rows[s,t,k]={'levels':n,'pms':pms}
        self.ledger.put=put
        self.classes=Counter({(s,'X','soldiers'):100 for s in 'ABCD'})
        self.policy={'military_population_weight':.7,'state_military_population_ceiling':.1}

    def convert(self,text):
        text, report=convert(self.ledger,text,{'X'},self.classes,self.policy)
        verify(self.ledger,text,report)
        return text,report

    def test_merge_hq_preserves_named_and_inline_ships_and_army(self):
        self.ledger.coastal_provinces={'a','b'}
        self.ledger.rows['D','X',BUILDING]={'levels':20}
        text,report=self.convert('''MILITARY_FORMATIONS={c:X ?={
          create_ship={type=ship_type:light fleet=scope:old name="Named Ship"}
          create_military_formation={type=army hq_region=sr:west}
          create_military_formation={type=fleet hq_region=sr:west save_scope_as=old
             ship={type=ship_type:heavy count=2 state_region=s:A flagship=yes}}
          create_military_formation={type=fleet hq_region=sr:west ship={type=ship_type:light count=1}}
        } c:Y ?={create_military_formation={type=fleet hq_region=sr:east ship={type=ship_type:heavy count=3}}}}''')
        r=report['countries']['X']
        self.assertEqual((r['exported_ships'],r['department_levels'],r['formation_count']),(4,2,1))
        self.assertEqual(r['unallocated_ships'],[])
        self.assertNotIn(('D','X',BUILDING),self.ledger.rows)
        self.assertIn('type=army',text)
        _,ships=read_ships(text,{'X','Y'})
        self.assertEqual(len(ships['Y']),3)
        self.assertEqual([s['name'] for s in ships['X'] if 'name' in s],['Named Ship'])
        self.assertEqual(sum(s.get('flagship')=='yes' for s in ships['X']),1)
        with self.assertRaises(ValueError): verify(self.ledger,text.replace('Named Ship','Lost Name'),report)

    def test_department_history_uses_government_levels_without_private_ownership(self):
        from economy_capacity import Ledger
        from economy_model import render_buildings, building_rows
        ledger=Ledger.__new__(Ledger)
        ledger.rows={};ledger.by_state=defaultdict(set);ledger.by_country=defaultdict(set);ledger.changes=[]
        ledger.allowed=lambda *a:True
        ledger.put('A','X',BUILDING,3,'navy',['recruit'])
        text=render_buildings(list(ledger.rows.values()))
        self.assertIn('level = 3',text)
        self.assertNotIn('add_ownership',text)
        path=Path(self.tmp.name)/'buildings.txt';path.write_text(text,encoding='utf-8-sig')
        self.assertEqual(building_rows(path)[0]['levels'],3)

    def test_two_hqs_round_separately_and_only_owned_coast_is_eligible(self):
        text,report=self.convert('''MILITARY_FORMATIONS={c:X ?={create_military_formation={
            type=fleet hq_region=sr:west ship={type=ship_type:heavy count=3}}}}''')
        self.assertEqual(report['countries']['X']['formation_count'],2)
        self.assertEqual(report['countries']['X']['department_levels'],3)
        self.assertNotIn('D',report['countries']['X']['state_caps'])

    def test_army_exhausted_population_reports_unallocated_ships(self):
        for s in 'ABC': self.ledger.rows[s,'X','building_barrack']={'levels':10}
        _,report=self.convert('''MILITARY_FORMATIONS={c:X ?={create_military_formation={
            type=fleet hq_region=sr:west ship={type=ship_type:heavy count=2}}}}''')
        r=report['countries']['X']
        self.assertEqual(r['exported_ships'],0)
        self.assertEqual(len(r['unallocated_ships']),2)
        self.assertEqual(r['unallocated_ships'][0]['reason'],'military_population_capacity')

    def test_landlocked_and_locked_technology_are_explicit(self):
        sample='''MILITARY_FORMATIONS={c:X ?={create_military_formation={
            type=fleet hq_region=sr:west ship={type=ship_type:heavy count=1}}}}'''
        self.ledger.coastal_provinces=set()
        _,report=self.convert(sample)
        self.assertEqual(report['countries']['X']['unallocated_ships'][0]['reason'],'no_owned_coast')
        self.ledger.coastal_provinces={'a'};self.ledger.allowed=lambda *a:False
        _,report=self.convert(sample)
        self.assertEqual(report['countries']['X']['unallocated_ships'][0]['reason'],'naval_department_technology_locked')
        self.ledger.allowed=lambda *a:True;self.ledger.techs['X']=set()
        _,report=self.convert(sample)
        self.assertEqual(report['countries']['X']['unallocated_ships'][0]['reason'],'ship_technology_locked')

    def test_no_ships_removes_obsolete_departments_without_empty_fleet(self):
        self.ledger.rows['A','X',BUILDING]={'levels':10}
        text,report=self.convert('MILITARY_FORMATIONS={c:X ?={}}')
        self.assertEqual(self.ledger.rows,{})
        self.assertEqual(report['formations'],[])

    def test_tampered_ship_count_and_department_capacity_fail_readback(self):
        text,report=self.convert('''MILITARY_FORMATIONS={c:X ?={create_military_formation={
            type=fleet hq_region=sr:west ship={type=ship_type:heavy count=1}}}}''')
        with self.assertRaises(ValueError): verify(self.ledger,text.replace('count = 1','count = 2'),report)
        key=next(k for k in self.ledger.rows if k[2]==BUILDING)
        self.ledger.rows[key]['levels']=0
        with self.assertRaises(ValueError): verify(self.ledger,text,report)

    def test_assignment_slots_round_each_ship_not_total_crew(self):
        self.ledger.coastal_provinces={'a'}
        _,report=self.convert('''MILITARY_FORMATIONS={c:X ?={create_military_formation={
            type=fleet hq_region=sr:west ship={type=ship_type:light count=6}}}}''')
        f=report['formations'][0]
        self.assertEqual((f['crew'],f['assignment_sailors'],f['department_levels']),(900,1200,2))


if __name__=='__main__': unittest.main()
