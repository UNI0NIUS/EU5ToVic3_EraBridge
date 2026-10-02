from copy import deepcopy
import json
from pathlib import Path
from unittest import TestCase,main
from economy_source_development import industrial_uplift,factory_targets,bounded_import_need,same_economic_world
from economy_arable_adjustment import location_fraction,choose_land

ROOT=Path(__file__).resolve().parents[1]


class SourceDevelopmentTests(TestCase):
    def setUp(self):
        self.rules=json.loads((ROOT/'config/personal/economy_source_development.json').read_text())
        self.industry=self.rules['industry']
        self.land=json.loads((ROOT/'config/personal/economy_arable_adjustment.json').read_text())
        self.land.update(self.rules['arable'])

    def test_industrial_source_absence_not_unemployment_or_population_bonus(self):
        self.assertEqual(industrial_uplift(100,1,1,0,set(self.industry['technology_markers']),self.industry),0)

    def test_development_and_production_technology_raise_bounded_uplift(self):
        low=industrial_uplift(20,.1,0,.04,set(),self.industry)
        high=industrial_uplift(80,.5,1,.04,set(self.industry['technology_markers']),self.industry)
        self.assertLess(low,high)
        self.assertEqual(high,.5)

    def test_target_does_not_compound_current_growth(self):
        rows=[{'state':'A','owner':'X','building':'factory','levels':10}]
        profiles={('A','X'):{'development':80,'urban_share':.5,'modern_share':1,'source_industry_share':.04,'population':100000}}
        args=(rows,profiles,{('A','X','factory'):100},{'X':set(self.industry['technology_markers'])},self.industry,{'factory'})
        self.assertEqual(factory_targets(*args)[0],{('A','X','factory'):15})
        self.assertEqual(factory_targets(*args),factory_targets(*args))

    def test_source_mapping_required_for_each_factory_kind(self):
        rows=[{'state':'A','owner':'X','building':'factory','levels':10}]
        self.assertEqual(factory_targets(rows,{}, {},{'X':set()},self.industry,{'factory'})[0],{('A','X','factory'):10})

    def test_developed_tropical_cropland_recovers_more_than_undeveloped_jungle(self):
        geo={'topography':'flatland','climate':'tropical','vegetation':'jungle'}
        low=location_fraction(geo,{'development':20,'raw_material':'rice'},False,self.land)
        high=location_fraction(geo,{'development':70,'raw_material':'rice'},False,self.land)
        self.assertGreater(high,.5)
        self.assertGreater(high,low)
        mining=location_fraction(geo,{'development':70,'raw_material':'coal'},False,self.land)
        self.assertLess(mining,.1)

    def test_arid_desert_cannot_be_reclaimed_by_high_development(self):
        geo={'topography':'flatland','climate':'arid','vegetation':'desert'}
        self.assertEqual(location_fraction(geo,{'development':100,'raw_material':'rice'},False,self.land),0)
        self.assertLess(location_fraction(geo,{'development':100,'raw_material':'rice'},True,self.land),.05)

    def test_active_farms_count_even_if_main_resource_is_wood(self):
        geo={'topography':'flatland','climate':'tropical','vegetation':'jungle'}
        before=location_fraction(geo,{'development':70,'raw_material':'lumber'},False,self.land)
        after=location_fraction(geo,{'development':70,'raw_material':'lumber','observed_crop_building':True},False,self.land)
        self.assertGreater(after,before)
        self.assertGreater(after,.5)

    def test_land_demand_still_cannot_raise_natural_ceiling(self):
        self.assertEqual(choose_land(40,.75,{'X':1},{'X':(10**9,5000)})[0],70)
        self.assertEqual(choose_land(40,.75,{'X':1},{'X':(0,5000)})[0],40)

    def test_import_credit_is_against_original_not_previous_iteration(self):
        self.assertTrue(bounded_import_need({'fabric':-50},{'fabric':-60},{'fabric':100},{'fabric':20},1000,self.industry))
        self.assertFalse(bounded_import_need({'fabric':-50},{'fabric':-61},{'fabric':100},{'fabric':20},1000,self.industry))

    def test_import_budget_cannot_add_new_unsupported_input_or_exceed_output_value(self):
        self.assertFalse(bounded_import_need({}, {'steel':-1},{},{'steel':50},1000,self.industry))
        self.assertFalse(bounded_import_need({'fabric':-50},{'fabric':-60},{'fabric':100},{'fabric':20},100,self.industry))

    def test_existing_import_gap_does_not_forbid_fully_supplied_increment(self):
        self.assertTrue(bounded_import_need({'fabric':-50},{'fabric':-50},{'fabric':100},{'fabric':20},0,self.industry))

    def test_switching_population_modes_does_not_reopen_expansion_plan(self):
        before={'common/history/buildings/world.txt':'a','common/history/pops/world.txt':'original','.metadata/metadata.json':'v1'}
        after=dict(before);after['common/history/pops/world.txt']='reserve15';after['.metadata/metadata.json']='v2'
        self.assertTrue(same_economic_world(before,after))
        after['common/history/buildings/world.txt']='new economic policy'
        self.assertFalse(same_economic_world(before,after))


if __name__=='__main__':main()
