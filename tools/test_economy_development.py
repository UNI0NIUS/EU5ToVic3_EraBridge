import unittest
from collections import Counter
from types import SimpleNamespace
from economy_development import development_parameters, manufacturing_kinds, DevelopmentPlanner
from economy_consumption import allocate


POLICY = dict(manufacturing_expansion_base=1.25,manufacturing_expansion_industrial=.75,
              observed_manufacturing_tolerance=1.5,artisan_workforce_ceiling=.02,
              urban_artisan_workforce_fraction=.1,food_reference_floor=.15,
              food_commercial_weight=.6,food_industrial_weight=.25,trade_reference_floor=.1,
              trade_commercial_weight=.6,trade_industrial_weight=.3,new_heavy_industry_intensity_min=.35,
              heavy_industry_kinds=['steel'])


class DevelopmentTests(unittest.TestCase):
    def test_input_support_preserves_useful_byproduct_and_automation_methods(self):
        from complete_economy import output_pms
        ledger=SimpleNamespace(pms=lambda *args:['basic','no_hardwood','no_automation'],techs={'X':set()},
                               target=SimpleNamespace(coefficients=lambda *args:{'outputs':{'wood':20,'hardwood':10}}))
        existing=['basic','hardwood','automation']
        self.assertEqual(output_pms(ledger,'X','logging','wood',existing),existing)

    def test_no_universal_industrialization_from_large_population(self):
        poor = development_parameters(0,0,0,0,0,100000000,.25,POLICY)
        self.assertEqual(poor['manufacturing_job_ceiling'],0)
        self.assertFalse(poor['heavy_industry_expansion_allowed'])
        self.assertLess(poor['trade_reference_factor'],.2)

    def test_industrial_base_preserved_with_differentiated_expansion(self):
        poor = development_parameters(.1,.05,.1,1000,5000,1000000,.25,POLICY)
        advanced = development_parameters(1,.5,.1,1000,5000,1000000,.25,POLICY)
        self.assertGreaterEqual(poor['manufacturing_job_ceiling'],5000)
        self.assertGreater(advanced['manufacturing_job_ceiling'],poor['manufacturing_job_ceiling'])
        self.assertGreater(advanced['commercial_food_reference_factor'],poor['commercial_food_reference_factor'])

    def test_strength_is_source_relative_not_british_absolute_size_cap(self):
        a = development_parameters(1,.5,.1,1000,5000,1000000,.25,POLICY)
        b = development_parameters(1,.5,.1,10000,50000,10000000,.25,POLICY)
        self.assertEqual(b['manufacturing_job_ceiling'],a['manufacturing_job_ceiling']*10)

    def test_building_group_ancestry_includes_heavy_and_light_industry(self):
        t = SimpleNamespace(buildings={'steel':{'building_group':'heavy'},'cloth':{'building_group':'light'},'farm':{'building_group':'rural'}},
                            building_groups={'heavy':{'parent_group':'bg_manufacturing'},'light':{'parent_group':'bg_manufacturing'},'rural':{},'bg_manufacturing':{}})
        self.assertEqual(manufacturing_kinds(t),{'steel','cloth'})

    def test_heavy_industry_gate_and_existing_industry_exception(self):
        d = DevelopmentPlanner.__new__(DevelopmentPlanner)
        d.manufacturing={'steel'};d.policy=POLICY;d.denied=Counter()
        d.profiles={'X':{'scope':'source_economy','heavy_industry_expansion_allowed':False,'seed_manufacturing_levels':{},'manufacturing_job_ceiling':10000}}
        d.jobs=lambda t:0
        d.ledger=SimpleNamespace(target=SimpleNamespace(coefficients=lambda *args:{'jobs':5000}),techs={'X':set()},pms=lambda *args:[],rows={})
        self.assertEqual(d.room('A','X','steel'),0)
        d.profiles['X']['seed_manufacturing_levels']['steel']=1
        self.assertEqual(d.room('A','X','steel'),2)
        d.ledger.rows['A','X','steel']={'levels':1}
        d.ledger.coefficients=lambda row:{'jobs':1000}
        d.jobs=lambda tag:1000
        d.profiles['X']['manufacturing_job_ceiling']=9000
        self.assertEqual(d.room('A','X','steel'),0)

    def test_household_raw_goods_not_counted_twice(self):
        needs=dict(standard_clothing=0,simple_clothing=100,furniture=100,household_items=0,heating=100)
        plan=allocate(needs,Counter(wood=10,fabric=10),{'wood':10,'fabric':10,'clothes':30,'furniture':30,'glass':40,'paper':30,'coal':30})
        self.assertLessEqual(plan['goods_reserved']['wood'],10)
        self.assertLessEqual(plan['goods_reserved']['fabric'],10)
        self.assertGreater(sum(plan['shortfalls'].values()),0)
        self.assertEqual(plan['allocations']['furniture']['wood'],50)
        self.assertEqual(plan['allocations']['heating']['wood'],50)

    def test_negative_industrial_balance_is_not_available_to_households(self):
        needs=dict(standard_clothing=0,simple_clothing=0,furniture=0,household_items=0,heating=100)
        plan=allocate(needs,Counter(wood=-20),dict(wood=10,fabric=10,clothes=30,furniture=30,glass=40,paper=30,coal=30))
        self.assertEqual(plan['shortfalls']['heating'],100)


if __name__=='__main__': unittest.main()
