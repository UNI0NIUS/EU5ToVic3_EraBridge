import unittest
from pathlib import Path
from pdx_text import root
from m3_flags import FlagExporter
from source_flag_context import rank_evidence

class SourceFlagsTests(unittest.TestCase):
    def test_rank_history_dates_not_input_order_or_power_rank(self):
        raw={'level':'2','great_power_rank':'1','country_rank_history':[
            [None,[['country_rank','rank_empire'],['date','1800.1.1']]],
            [None,[['country_rank','rank_kingdom'],['date','1700.1.1']]],
            [None,[['country_rank','rank_duchy']]]]}
        self.assertEqual(rank_evidence(raw,'1780.7.4')['rank'],'rank_kingdom')
        self.assertIsNone(rank_evidence({'level':'3'},'1780.7.4')['rank'])
    def test_override_is_explicit_and_audited(self):
        raw={'country_rank_history':[[None,[['country_rank','rank_empire']]]]}
        r=rank_evidence(raw,'1780.7.4','rank_kingdom')
        self.assertTrue(r['history_disagrees_with_override'])
    def test_rank_and_variable_negation(self):
        f=FlagExporter.__new__(FlagExporter);f.triggers={}
        s={'country_rank':'rank_empire','variable_names':[]}
        self.assertTrue(f.trigger(root('country_rank=country_rank:rank_empire NOT={has_variable=roses}'),s,None))
        self.assertIsNone(f.trigger(root('NOT={has_variable=roses}'),{},None))
    def test_nested_colonies_and_unknown_capital(self):
        f=FlagExporter.__new__(FlagExporter);f.triggers={}
        f.source_countries={'b':{'subject_ids':['c'],'subject_type':'vassal'},
                            'c':{'subject_ids':[],'subject_type':'colonial_nation','capital_continent':'america'}}
        cond=root('any_subject_or_below={is_subject_type=colonial_nation capital ?= {continent=continent:america}}')
        self.assertTrue(f.trigger(cond,{'subject_ids':['b']},None))
        self.assertFalse(f.trigger(cond,{'subject_ids':[]},None))
        f.source_countries['c']['capital_continent']=None
        self.assertIsNone(f.trigger(cond,{'subject_ids':['b']},None))

if __name__=='__main__':unittest.main()
