from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from economy_agriculture import AgriculturePlanner
from economy_capacity import Ledger
from economy_source_structure import profile
from pdx_text import root


def fixture(pop=1000000, land=100, development=50, paid=100000):
    target = SimpleNamespace(states={'A':{'arable_land':str(land),'arable_resources':root('farm ranch'),
                                          'subsistence_building':'sub'}},aliases={},
        buildings={k:{} for k in ['farm','ranch','sub']},select=lambda *a:[],
        coefficients=lambda k,*a:{'jobs':10000 if k=='sub' else 5000})
    ledger = Ledger(target,[],{('A','X'):pop},{'X':set()},{'X':set()},{'A':{'a':'X'}},defaultdict(set),
        {'workforce_share':.25,'maximum_formal_workforce_share':.25,'rural_classes':['peasants'],
         'commercial_rural_workforce_limit':1,'geography_policy':'vanilla_capacity'})
    ledger.source_classes['A','X','peasants'] = pop-paid
    ledger.source_paid_agriculture['A','X'] = paid
    source = {'locations':{'1':{'name':'a','population':pop,'development':development}}}
    ledger.agriculture = AgriculturePlanner(ledger,source,{'a':{('A','X'):1}},{'X'},
        {'maximum_peasant_commercialization_fraction':.2})
    return ledger


class AgricultureTests(unittest.TestCase):
    def test_expansion_prices_replacement_methods_on_existing_levels(self):
        ledger=fixture()
        ledger.target.coefficients=lambda kind,pms,techs: {'jobs':3000 if pms==['automated'] else 8000}
        ledger.agriculture.profiles['A','X']['commercial_job_ceiling']=15333
        ledger.put('A','X','farm',1,'automated existing farm',['automated'])
        self.assertEqual(ledger.agriculture.room('A','X','farm',['manual']),0)
        self.assertEqual(ledger.capped_room('A','X','farm',['manual']),0)
        self.assertEqual(ledger.agriculture.room('A','X','farm',['automated']),4)

    def test_formal_and_rural_budgets_include_method_replacement(self):
        ledger=fixture()
        del ledger.agriculture
        ledger.target.coefficients=lambda kind,pms,techs: {'jobs':3000 if pms==['automated'] else 8000}
        ledger.put('A','X','farm',1,'seed',['automated'])
        ledger.config['maximum_formal_workforce_share']=.015333
        self.assertEqual(ledger.capped_room('A','X','farm',['manual']),0)
        ledger.config['maximum_formal_workforce_share']=.25
        ledger.source_classes['A','X','peasants']=0
        ledger.source_paid_agriculture['A','X']=61332
        self.assertEqual(ledger.capped_room('A','X','farm',['manual']),0)

    def test_landless_people_do_not_receive_subsistence_food_discount(self):
        from complete_economy import living_requirements
        ledger=fixture(land=10)
        ledger.buy_packages={'wealth_10':{'goods':root('popneed_basic_food=100')}}
        self.assertEqual(living_requirements(ledger,'X',10)['equivalent_consumers'],387500)
        ledger.target.states['A']['arable_land']='100'
        self.assertEqual(living_requirements(ledger,'X',10)['equivalent_consumers'],31250)

    def test_development_allows_limited_commercialization_and_preserves_subsistence(self):
        ledger = fixture()
        p = ledger.agriculture.profiles['A','X']
        self.assertEqual(p['commercial_job_ceiling'],47500)
        self.assertEqual(p['source_subsistence_worker_target'],202500)
        ledger.put('A','X','farm',60,'seed')
        ledger.put('A','X','ranch',20,'seed')
        ledger.agriculture.constrain_existing()
        audit = ledger.agriculture.audit()['states'][0]
        self.assertEqual(audit['commercial_levels'],9)
        self.assertGreaterEqual(audit['remaining_subsistence_land'],21)
        self.assertEqual(ledger.capped_room('A','X','farm'),0)

    def test_overcrowded_dry_state_keeps_both_livelihoods_without_creating_land(self):
        ledger = fixture(pop=10000000,land=10,development=20,paid=1000000)
        p = ledger.agriculture.profiles['A','X']
        self.assertGreater(p['commercial_land_ceiling'],0)
        self.assertLess(p['commercial_land_ceiling'],10)
        self.assertEqual(p['arable_share'],10)
        ledger.put('A','X','farm',1000,'seed')
        ledger.agriculture.constrain_existing()
        self.assertEqual(ledger.agriculture.audit()['states'][0]['commercial_land_excess'],0)
        self.assertEqual(ledger.capped_room('A','X','ranch'),0)

    def test_poor_pure_subsistence_is_not_forcibly_commercialized(self):
        ledger = fixture(development=0,paid=0)
        self.assertEqual(ledger.capped_room('A','X','farm'),0)
        self.assertEqual(ledger.agriculture.profiles['A','X']['source_subsistence_worker_target'],250000)

    def test_active_village_pm_and_processing_are_not_false_mines(self):
        with TemporaryDirectory() as d:
            base=Path(d); bt=base/'in_game/common/building_types'; bt.mkdir(parents=True)
            pm=base/'in_game/common/production_methods'; pm.mkdir()
            (bt/'test.txt').write_text('''
                village={pop_type=peasants possible_production_methods={fishing boats}}
                charcoal={pop_type=laborers unique_production_methods={burn={produced=coal lumber=1}}}
                bog_iron_smelter={pop_type=laborers unique_production_methods={bog={produced=iron}}}
            ''')
            (pm/'test.txt').write_text('fishing={produced=fish} boats={produced=naval_supplies}')
            source={'locations':{'1':{'name':'a','raw_material':'coal','rgo_workers':2000}},
                    'buildings':[{'type':k,'location':'1','employed':'10','pms':[method]}
                                 for k,method in [('village','boats'),('charcoal','burn'),('bog_iron_smelter','bog')]]}
            _,resources,report=profile(source,base,{'a':{('A','X'):1}})
            self.assertEqual(resources,Counter({('A','X','building_coal_mine'):2000}))
            source['buildings'][0]['pms']=['fishing']
            _,resources,report=profile(source,base,{'a':{('A','X'):1}})
            self.assertEqual(resources['A','X','building_fishing_wharf'],10000)
            self.assertEqual(len(report['non_mine_resource_processing']),2)

    def test_repeated_source_pm_blocks_keep_earlier_active_method(self):
        with TemporaryDirectory() as d:
            base=Path(d); bt=base/'in_game/common/building_types'; bt.mkdir(parents=True)
            (bt/'test.txt').write_text('mine={pop_type=laborers unique_production_methods={old={produced=iron}} unique_production_methods={new={produced=coal}}}')
            source={'locations':{'1':{'name':'a','raw_material':'clay','rgo_workers':0}},
                    'buildings':[{'type':'mine','location':'1','employed':'2','pms':['old']}]}
            _,resources,_=profile(source,base,{'a':{('A','X'):1}})
            self.assertEqual(resources,Counter({('A','X','building_iron_mine'):2000}))


if __name__=='__main__': unittest.main()
