from types import SimpleNamespace
from unittest.mock import patch
import unittest
from converter_arable_advice import advice
from converter_project import DEFAULTS,apportion


class ArableAdviceTests(unittest.TestCase):
    def setUp(self):
        self.options=dict(DEFAULTS,workforce_share=.25,staffing=1,unemployment_threshold=.25)
        self.row=dict(id='S|AAA',state='S',country='AAA',province_count=1,arable=10,state_arable=100,
            population=40000,formal_jobs=1000,job_capacity=1500,estimated_unemployment=.85,buildings={'farm':5})
        self.other=dict(id='S|BBB',state='S',country='BBB',province_count=9,arable=90)
        target=SimpleNamespace(states={'S':{'subsistence_building':'sub'}},select=lambda *a:[],coefficients=lambda *a:{'jobs':100})
        self.view=SimpleNamespace(target=target,techs={'AAA':set()},laws={'AAA':set()},arable_kinds={'farm'})
        self.world=SimpleNamespace(preview=lambda *a:{'rows':[self.row,self.other]})

    def calculate(self):
        with patch('converter_arable_advice.materialize',return_value=self.view):
            return advice(self.world,self.options,[],'S|AAA')

    def test_whole_state_suggestion_accounts_for_minority_land_and_existing_farms(self):
        result=self.calculate()
        self.assertEqual(result['relief']['state_base'],710)
        self.assertEqual(result['relief']['added_base'],610)
        self.assertEqual(result['relief']['region_arable'],71)
        self.assertLess(result['relief']['unemployment'],.25)
        self.assertEqual(result['full']['state_base'],950)
        self.assertEqual(result['full']['unemployment'],0)

    def test_global_multiplier_is_inverted_without_double_applying(self):
        self.options['arable_multiplier']=2
        result=self.calculate()
        self.assertEqual(result['relief']['state_base'],355)
        self.assertEqual(result['relief']['state_effective'],710)

    def test_satisfied_region_never_recommends_reducing_land(self):
        self.row.update(job_capacity=15000,formal_jobs=14500,estimated_unemployment=0)
        result=self.calculate()
        for key in ('full','relief'):
            self.assertTrue(result[key]['already_satisfied']);self.assertEqual(result[key]['added_base'],0)

    def test_unknown_jobs_and_missing_region_are_not_zero(self):
        self.row['job_capacity']=None
        with self.assertRaisesRegex(ValueError,'未知'):self.calculate()
        self.row['id']='T|AAA'
        with self.assertRaisesRegex(ValueError,'变化'):self.calculate()

    def test_unrepresentable_advice_is_reported_without_invalid_value(self):
        self.row['population']=1e12
        result=self.calculate()
        self.assertFalse(result['relief']['available']);self.assertNotIn('state_base',result['relief'])

    def test_quota_guarantee_under_unequal_apportionment(self):
        for count in (1,2,7,19):
            for factor in (.1,.7,1,1.3,5):
                self.other['province_count']=count;self.options['arable_multiplier']=factor
                result=self.calculate()
                for key in ('relief','full'):
                    value=result[key];land=apportion(value['state_effective'],{'AAA':1,'BBB':count})['AAA']
                    unemployment=max(0,1-(1000+(land-5)*100)/10000)
                    self.assertEqual(value['unemployment'],unemployment)
                    self.assertLess(unemployment,.25)
                    if key=='full':self.assertEqual(unemployment,0)


if __name__=='__main__':unittest.main()
