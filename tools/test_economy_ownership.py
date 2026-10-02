from collections import Counter,defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from economy_capacity import Ledger
from economy_model import building_rows,render_buildings
from economy_ownership import OwnershipPlanner,MANOR,FINANCE,shares,province_evidence,vanilla_reference
from pdx_text import root

POLICY=json.loads((Path(__file__).resolve().parents[1]/'config/personal/economy_capacity.json').read_text(encoding='utf-8'))['ownership']
POLICY['calibrated_reference_shares']={profile:{s:{'manor':.1,'finance':.75,'self':.15} for s in POLICY['sectors']} for profile in ['agrarian','mixed','industrial']}


def fixture():
    kinds={'farm':'bg_agriculture','factory':'bg_manufacturing',MANOR:'owners',FINANCE:'owners','government':'public'}
    t=SimpleNamespace(states={'A':{},'B':{}},aliases={},buildings={k:{'building_group':v} for k,v in kinds.items()},
        building_groups={v:{} for v in kinds.values()},select=lambda k,*a:[k],
        coefficients=lambda k,*a:{'jobs':150 if k==MANOR else 100 if k==FINANCE else 1000},
        numeric=lambda p:Counter({'building_employment_aristocrats_add' if p==[MANOR] else 'building_employment_capitalists_add':50}))
    ledger=Ledger(t,[],{('A','X'):1000000,('B','X'):1000000},{'X':set()},{'X':set()},
        {'A':{'a':'X'},'B':{'b':'X'}},defaultdict(set),{'workforce_share':.25})
    ps={('A','X','a'):{'state':'A','country':'X','province':'a','population':1000000,'classes':Counter(nobles=10000,burghers=50000,laborers=400000,peasants=540000),'noble_share':.01,'burgher_share':.05,'development':50,'urban_population':450000},
        ('B','X','b'):{'state':'B','country':'X','province':'b','population':1000000,'classes':Counter(laborers=400000,peasants=600000),'noble_share':0,'burgher_share':0,'development':50,'urban_population':0}}
    return ledger,ps


class OwnershipTests(unittest.TestCase):
    def test_vanilla_reference_excludes_public_and_company_assets(self):
        ledger,_=fixture()
        with TemporaryDirectory() as d:
            base=Path(d);folder=base/'common/history/buildings';folder.mkdir(parents=True)
            (folder/'test.txt').write_text('''BUILDINGS={s:A={region_state:X={create_building={building=factory add_ownership={
              country={country="c:X" levels=50}
              building={type=building_financial_district country="c:X" region=A levels=3}
              building={type=factory country="c:X" region=A levels=1}
              building={type=building_company_headquarter country="c:X" region=A levels=90}
            }}}}}''')
            ledger.target.game=base
            policy={**POLICY,'sectors':['industry'],'vanilla_reference_profiles':{'agrarian':['X'],'mixed':['X'],'industrial':['X']}}
            result=vanilla_reference(ledger.target,policy)
            self.assertEqual(result['profiles']['industrial']['industry'],{'manor':0,'finance':.75,'self':.25})
            self.assertEqual(result['countries']['X']['industry']['government'],50)

    def test_local_development_blends_vanilla_profiles_without_country_tag(self):
        policy={**POLICY,'calibrated_reference_shares':{
            'agrarian':{'industry':{'manor':0,'finance':.1,'self':.9}},
            'mixed':{'industry':{'manor':0,'finance':.5,'self':.5}},
            'industrial':{'industry':{'manor':0,'finance':.9,'self':.1}}}}
        low=shares(.01,.05,0,'industry',set(),policy,0)
        high=shares(.01,.05,100,'industry',set(),policy,1)
        self.assertGreater(high['finance'],low['finance'])
    def test_elite_share_increases_corresponding_sector_ownership(self):
        a=shares(.005,.03,50,'agriculture',set(),POLICY)
        b=shares(.01,.03,50,'agriculture',set(),POLICY)
        self.assertGreater(b['manor'],a['manor'])
        a=shares(.005,.03,50,'industry',set(),POLICY)
        b=shares(.005,.06,50,'industry',set(),POLICY)
        self.assertGreater(b['finance'],a['finance'])
        self.assertEqual(shares(0,0,100,'industry',set(),POLICY)['self'],1)
        self.assertEqual(shares(.1,.4,100,'industry',{'law_cooperative_ownership'},POLICY)['self'],1)

    def test_no_country_average_or_cross_state_investor_pool(self):
        ledger,ps=fixture()
        for s in ['A','B']:ledger.put(s,'X','factory',100,'seed')
        planner=OwnershipPlanner(ledger,ps,{'X'},POLICY);result=planner.apply()
        a=next(r for r in result['assets'] if r['state']=='A')
        b=next(r for r in result['assets'] if r['state']=='B')
        self.assertEqual(a['after']['finance'],50)  # 20% of local burgher workforce / 50 capitalists
        self.assertGreater(a['after']['finance']+a['after']['manor'],50)
        self.assertEqual(b['after'],{'self':100})
        self.assertEqual(sum(r['levels'] for r in ledger.rows.values()),200)

    def test_preserve_public_foreign_and_company_shares_and_roundtrip(self):
        ledger,ps=fixture()
        ledger.put('A','X','factory',100,'seed')
        r=ledger.rows['A','X','factory']
        r['body']='''building=factory reserves=0.7 add_ownership={
          country={country="c:X" levels=10}
          building={type="building_financial_district" country="c:Y" region="FOREIGN" levels=20}
          building={type="building_company_headquarter" country="c:X" region="A" levels=10}
          building={type=factory country="c:X" region="A" levels=60}
        } activate_production_methods={factory}'''
        planner=OwnershipPlanner(ledger,ps,{'X'},POLICY);planner.apply()
        self.assertIn('country="c:Y"',r['body']);self.assertIn('reserves=0.7',r['body'])
        with TemporaryDirectory() as d:
            path=Path(d)/'history.txt';path.write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8')
            rows=building_rows(path)
            self.assertEqual(rows[0]['levels'],100)
            self.assertEqual(planner.verify(rows),1)

    def test_owner_jobs_use_safety_staffing_and_report_full_staffing_pressure(self):
        ledger,ps=fixture();ledger.put('A','X','factory',249,'seed')
        planner=OwnershipPlanner(ledger,ps,{'X'},POLICY);result=planner.apply()
        self.assertGreater(ledger.jobs('A','X'),250000)
        self.assertTrue(all(r['safety_staffing_excess_jobs']==0 for r in result['owner_hosts']))
        self.assertTrue(any(r['full_staffing_excess_jobs']>0 for r in result['owner_hosts']))
        self.assertTrue(result['unmet_owner_allocations'])
        self.assertEqual(sum(result['assets'][0]['after'].values()),249)

    def test_province_ratios_are_calculated_before_state_aggregation(self):
        source={'locations':{'1':{'name':'urban','development':80,'rank':'city'},'2':{'name':'rural','development':10,'rank':'rural_settlement'}}}
        rows=[{'target_state':'A','target_owner':'X','target_province':p,'source_location':loc,'source_class':c,'centipersons':str(n*100)}
            for p,loc,c,n in [('a','urban','burghers',800),('a','urban','laborers',200),('b','rural','peasants',10000)]]
        provinces=province_evidence(rows,source)
        self.assertEqual(provinces['A','X','a']['burgher_share'],.8)
        self.assertEqual(provinces['A','X','b']['burgher_share'],0)
        self.assertEqual(provinces['A','X','b']['development'],10)


if __name__=='__main__':unittest.main()
