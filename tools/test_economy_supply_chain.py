from collections import Counter, defaultdict
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from economy_capacity import Ledger
from economy_model import Target
from economy_supply_chain import (naval_reserve, improve_existing, expansion_room,
                                  moderate_glass, source_glass_methods, replace_pm)
from pdx_text import root


class SupplyTests(unittest.TestCase):
    def ledger(self):
        target=Target.__new__(Target)
        target.buildings={'ranch':{'production_method_groups':root('base')},'glass':{'production_method_groups':root('glass')}}
        target.groups={'base':{'production_methods':root('simple sheep')},'glass':{'production_methods':root('forest leaded')}}
        target.pms={k:dict(root(v).entries()) for k,v in {
            'simple':'building_modifiers={workforce_scaled={goods_output_fabric_add=5} level_scaled={building_employment_laborers_add=10}}',
            'sheep':'unlocking_technologies={sheep} building_modifiers={workforce_scaled={goods_input_grain_add=10 goods_output_fabric_add=15} level_scaled={building_employment_laborers_add=10}}',
            'forest':'building_modifiers={workforce_scaled={goods_output_glass_add=30 goods_input_wood_add=30} level_scaled={building_employment_laborers_add=10}}',
            'leaded':'building_modifiers={workforce_scaled={goods_output_glass_add=40 goods_input_wood_add=20 goods_input_lead_add=10} level_scaled={building_employment_laborers_add=10}}'
        }.items()}
        target.prices={'fabric':20,'grain':20,'glass':40,'wood':20,'lead':40,'fish':20,'fruit':30,'meat':30,'groceries':30}
        target.prices.update(clothes=30,furniture=30,paper=30,coal=30)
        target.states={};target.aliases={};target.techs={'sheep':{}}
        rows=[{'state':'A','owner':'X','building':'ranch','levels':1,'pms':['simple']}]
        l=Ledger(target,rows,Counter(),{'X':{'sheep'}},{'X':set()},{},defaultdict(set),{})
        # Independent existing consumers supply the shortage; tests do not mirror
        # the production method selector's own net-delta calculation.
        l.military_demand['X']['fabric']=20
        l.military_demand['X']['grain']=-100
        return l

    def needs(self, *args):
        return {'basic_food':0,'standard_clothing':0,'simple_clothing':0,'furniture':0,'household_items':0,'heating':0}

    @patch('complete_economy.living_requirements', needs)
    def test_positive_existing_fabric_does_not_block_sheep_upgrade(self):
        l=self.ledger();improve_existing(l,'X','fabric',['ranch'])
        self.assertEqual(l.rows['A','X','ranch']['pms'],['sheep'])
        self.assertEqual(l.balance('X')['fabric'],-5)

    @patch('complete_economy.living_requirements', needs)
    def test_no_sheep_when_feed_is_short_or_technology_missing(self):
        for feed,tech in [(0,{'sheep'}),(-100,set())]:
            l=self.ledger();l.military_demand['X']['grain']=feed;l.techs['X']=tech
            improve_existing(l,'X','fabric',['ranch'])
            self.assertEqual(l.rows['A','X','ranch']['pms'],['simple'])

    @patch('complete_economy.living_requirements', needs)
    def test_guarded_assets_are_not_optimized(self):
        l=self.ledger();l.rows['A','X','ranch']['guards']=('unknown=yes',)
        improve_existing(l,'X','fabric',['ranch'])
        self.assertFalse(l.changes)

    def test_pm_edit_preserves_ownership_and_conditions(self):
        l=self.ledger();r=l.rows['A','X','ranch']
        r['body']='building=ranch add_ownership={building={type=manor country=c:Y levels=1}} activate_production_methods={simple}'
        replace_pm(l,r,['sheep'],'test')
        self.assertIn('country=c:Y levels=1',r['body'])
        self.assertEqual(r['levels'],1)

    def test_native_construction_goods_are_not_ordinary_shipyard_inputs(self):
        l=self.ledger();l._supply_ship={'base_construction_cost':'25','construction_goods':root('goods_input_fabric_add=130 goods_input_hardwood_add=130')}
        l.target.pms['simple']['country_modifiers']=root('workforce_scaled={country_ship_construction_add=5}')
        self.assertEqual(naval_reserve(l,'X'),{'fabric':26,'hardwood':26})
        self.assertEqual(naval_reserve(l,'X',.5)['fabric'],13)
        self.assertEqual(naval_reserve(l,'X',0)['fabric'],0)
        with self.assertRaises(ValueError):naval_reserve(l,'X',2)

    @patch('complete_economy.living_requirements', needs)
    def test_expansion_requires_inputs_but_does_not_remove_inherited_levels(self):
        l=self.ledger();l._supply_ship={'base_construction_cost':'25','construction_goods':root('')}
        l.supply_chain_policy={'naval_construction_utilization':1,'household_wealth_scenario':10}
        self.assertEqual(expansion_room(l,'X','ranch',['sheep'],100),10)
        l.military_demand['X']['grain']=0
        self.assertEqual(expansion_room(l,'X','ranch',['sheep'],100),0)
        self.assertEqual(l.rows['A','X','ranch']['levels'],1)

    def test_pottery_is_not_automatically_luxury_porcelain(self):
        t=SimpleNamespace(available=lambda *args:True)
        pm=['base','pm_disabled_ceramics']
        self.assertEqual(source_glass_methods(t,pm,set(),set(),{'pottery':100}),pm)
        self.assertEqual(source_glass_methods(t,pm,set(),set(),{'porcelain':60,'glass':40}),['base','pm_ceramics'])
        self.assertEqual(source_glass_methods(t,pm,set(),set(),{'porcelain':40,'glass':60}),pm)
        t.available=lambda *args:False
        self.assertEqual(source_glass_methods(t,pm,set(),set(),{'porcelain':100}),pm)

    @patch('complete_economy.living_requirements', needs)
    def test_feed_upgrade_cannot_reduce_food_below_existing_target(self):
        l=self.ledger()
        needs=self.needs();needs['basic_food']=2000
        with patch('complete_economy.living_requirements',return_value=needs):
            improve_existing(l,'X','fabric',['ranch'])
        self.assertEqual(l.rows['A','X','ranch']['pms'],['simple'])

    def test_packager_rejects_level_or_foreign_ownership_mutation(self):
        from copy import deepcopy
        from package_m5_supply_chain import verify_rows
        l=self.ledger();r=l.rows['A','X','ranch']
        r['body']='building=ranch add_ownership={building={type=manor country=c:Y levels=1}} activate_production_methods={simple}'
        old=deepcopy(r);new=deepcopy(r);new['body']=new['body'].replace('c:Y','c:X')
        with self.assertRaises(ValueError):verify_rows(l,[old],[new])
        new=deepcopy(r);new['levels']=2
        with self.assertRaises(ValueError):verify_rows(l,[old],[new])

    def test_packager_compares_guard_semantics_after_render(self):
        from copy import deepcopy
        from package_m5_supply_chain import verify_rows
        l=self.ledger();r=l.rows['A','X','ranch']
        r['body']='building=ranch level=1 activate_production_methods={simple}';r['guards']=('exists=yes',)
        new=deepcopy(r);new['guards']=('\n exists = yes\n',)
        self.assertEqual(verify_rows(l,[r],[new]),1)

    @patch('complete_economy.living_requirements', needs)
    def test_shipyard_expansion_reserves_extra_fabric(self):
        l=self.ledger();l._supply_ship={'base_construction_cost':'25','construction_goods':root('goods_input_fabric_add=130')}
        l.supply_chain_policy={'naval_construction_utilization':1,'household_wealth_scenario':10}
        l.target.pms['simple']['country_modifiers']=root('workforce_scaled={country_ship_construction_add=5}')
        l.military_demand['X']['fabric']=-63
        # Each extra level produces 5 but reserves 26: 42 existing spare fits 2.
        self.assertEqual(expansion_room(l,'X','ranch',['simple'],100),2)

    @patch('complete_economy.living_requirements', needs)
    def test_glass_moderation_preserves_levels_jobs_and_other_inputs(self):
        l=self.ledger();l.target.buildings['building_glassworks']=l.target.buildings.pop('glass')
        l.rows={};l.by_country=defaultdict(set);l.by_state=defaultdict(set)
        row={'state':'A','owner':'X','building':'building_glassworks','levels':1,'pms':['leaded']}
        key=('A','X','building_glassworks');l.rows[key]=row;l.by_country['X'].add(key)
        l.military_demand['X']['wood']=-100;l.military_demand['X']['lead']=-100
        moderate_glass(l,'X');self.assertEqual(row['pms'],['forest']);self.assertEqual(row['levels'],1)
        row['pms']=['leaded'];l.military_demand['X']['wood']=-20
        moderate_glass(l,'X');self.assertEqual(row['pms'],['leaded'])


if __name__=='__main__':unittest.main()
