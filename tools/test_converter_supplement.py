from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import unittest
from converter_project import DEFAULTS
from converter_supplement import proposal
from pdx_text import root


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.options=dict(DEFAULTS,workforce_share=.25,staffing=1)
        self.row=dict(id='S|AAA',state='S',country='AAA',provinces=['x1','x2'],province_count=2,
            population=4000,formal_jobs=0,job_capacity=200,food_shortfall=.5,food_demand=100,
            buildings={},arable=20)
        self.target=SimpleNamespace(buildings={'mill':{'building_group':'bg_manufacturing'},'farm':{}},
            building_groups={'bg_manufacturing':{}},states={'S':{'arable_resources':root('farm')}},
            select=lambda *a:['manual'],coefficients=lambda *a:dict(jobs=100,outputs={'grain':1}))
        self.view=SimpleNamespace(target=self.target,buildings=[],arable_kinds={'farm'},techs={'AAA':set()},laws={'AAA':set()})
        self.operations=[dict(kind='bulk')];self.calls=[]
        def preview(options,ops):
            self.calls.append(deepcopy(ops));row=deepcopy(self.row)
            if len(ops)>1:
                n=next(iter(ops[-1]['levels'].values()))
                row['job_capacity']+=n*100;row['food_shortfall']=max(0,.5-n*.1)
            return {'rows':[row]}
        self.world=SimpleNamespace(preview=preview)

    def run_proposal(self,**kw):
        with patch('converter_supplement.materialize',return_value=self.view):
            return proposal(self.world,self.options,self.operations,'x2',kw.pop('building','mill'),**kw)

    def test_food_uses_current_market_deficit_and_one_province_share(self):
        result=self.run_proposal()
        self.assertEqual(result['need_share'],25)
        self.assertEqual(result['added'],3)
        self.assertEqual(result['operation']['supplement_province'],'x2')
        self.assertEqual(self.operations,[dict(kind='bulk')])
        self.assertEqual(len(self.calls[-1]),2) # Trial is replaced, never added twice.

    def test_jobs_and_limit(self):
        result=self.run_proposal(goal='unemployment',maximum=2)
        self.assertEqual(result['wanted'],4);self.assertEqual(result['added'],2)
        self.assertTrue(result['limited'])

    def test_no_capacity_or_unknown_demand_does_not_make_operation(self):
        self.row['food_shortfall']=None
        with self.assertRaisesRegex(ValueError,'未知'):self.run_proposal()
        self.row['food_shortfall']=.5;self.row['formal_jobs']=1000
        with self.assertRaisesRegex(ValueError,'容量'):self.run_proposal()

    def test_arable_room_includes_other_farms(self):
        self.row['arable']=1
        result=self.run_proposal(building='farm')
        self.assertEqual(result['added'],1);self.assertTrue(result['limited'])

    def test_negative_marginal_food_effect_is_not_recommended(self):
        original=self.world.preview
        def preview(options,ops):
            result=original(options,ops)
            if len(ops)>1:result['rows'][0]['food_shortfall']=.6
            return result
        self.world.preview=preview
        with self.assertRaisesRegex(ValueError,'未改善'):self.run_proposal()

    def test_locked_building_and_special_conditions_rejected(self):
        self.target.buildings['mill']['unlocking_technologies']=root('future')
        with self.assertRaisesRegex(ValueError,'未解锁'):self.run_proposal()
        self.target.buildings['mill']={'building_group':'bg_oil_extraction'}
        with self.assertRaisesRegex(ValueError,'特殊条件'):self.run_proposal()

    def test_fixed_resource_capacity_and_coastal_part_are_required(self):
        self.target.states['S']['capped_resources']=root('mill=2')
        self.view.owners={'S':{'x1':'AAA','x2':'AAA','x3':'BBB'}}
        self.target.buildings['mill']['potential']=root('is_sea_adjacent=yes')
        self.view.coastal_provinces={'x3'}
        with self.assertRaisesRegex(ValueError,'沿海'):self.run_proposal()
        self.view.coastal_provinces={'x2'}
        result=self.run_proposal()
        self.assertEqual(result['added'],1) # Two deposits apportioned 2:1 give this part one.
        self.assertTrue(result['limited'])


if __name__=='__main__':unittest.main()
