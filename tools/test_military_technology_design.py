import copy
from types import SimpleNamespace
import unittest

from military_technology_design import evaluate, validate
from pdx_text import root


class MilitaryDesignTests(unittest.TestCase):
    def setUp(self):
        self.target=SimpleNamespace(techs={
            'base':{'category':'military'},
            'organization':{'category':'military','unlocking_technologies':root('base')},
            'rifling':{'category':'military'}})
        self.advances={'corps':{},'supply':{},'long_rifle':{},'unlock':{'unlock_unit':'logistics_corps'}}
        self.units={'logistics_corps':{}}
        self.policy={'military_generic_progress_grants':False,'rules':{
            'base':{'mode':'evidence','reason':'standing forces','any_of':[{'regular_army':True}]},
            'organization':{'mode':'combined','reason':'combined capabilities','any_of':[
                {'advances_all':['corps','supply'],'unlocked_units_any':['logistics_corps']} ]},
            'rifling':{'mode':'withhold','reason':'no ignition evidence','any_of':[],'related_advances':['long_rifle']}}}

    def evaluate(self,advances,actual=(),regular=False,ships=False):
        return evaluate({'advances':advances,'institutions':[]},actual,regular,ships,self.policy,self.target,self.advances)

    def test_combined_rule_requires_every_condition_and_retains_unlock_provenance(self):
        self.assertEqual(self.evaluate(['corps','supply'])[0],set())
        self.assertEqual(self.evaluate(['corps','unlock'])[0],set())
        chosen,decisions=self.evaluate(['corps','supply','unlock'])
        self.assertEqual(chosen,{'base','organization'})
        self.assertEqual(decisions['base']['decision'],'prerequisite_closure')
        self.assertEqual(decisions['organization']['source_evidence'][0]['unlock_advance_ids'],['unlock'])

    def test_related_evidence_does_not_grant_a_withheld_technology(self):
        chosen,decisions=self.evaluate(['long_rifle','corps','supply','unlock'])
        self.assertNotIn('rifling',chosen)
        self.assertEqual(decisions['rifling']['related_researched'],['long_rifle'])

    def test_actual_army_proves_baseline_only(self):
        self.assertEqual(self.evaluate([],regular=True)[0],{'base'})
        self.assertEqual(self.evaluate([],ships=True)[0],set())

    def test_actual_unit_and_researched_unlock_are_distinct(self):
        self.assertEqual(self.evaluate(['corps','supply'],actual=['logistics_corps'])[0],set())
        self.policy['rules']['organization']['any_of'][0]['actual_units_any']=['logistics_corps']
        del self.policy['rules']['organization']['any_of'][0]['unlocked_units_any']
        self.assertEqual(self.evaluate(['corps','supply'],actual=['logistics_corps'])[0],{'base','organization'})

    def test_unknown_sources_predicates_and_incomplete_catalogue_fail(self):
        validate(self.policy,self.target,self.advances,self.units,{})
        with self.assertRaises(ValueError):self.evaluate(['undefined'])
        bad=copy.deepcopy(self.policy);del bad['rules']['rifling']
        with self.assertRaises(ValueError):validate(bad,self.target,self.advances,self.units,{})
        bad=copy.deepcopy(self.policy);bad['rules']['base']['any_of']=[{'army_size':100}]
        with self.assertRaises(ValueError):validate(bad,self.target,self.advances,self.units,{})
        bad=copy.deepcopy(self.policy);bad['rules']['base']['any_of']=[{'advances_any':['imaginary']}]
        with self.assertRaises(ValueError):validate(bad,self.target,self.advances,self.units,{})

    def test_cycles_and_blank_grants_are_rejected(self):
        self.target.techs['base']['unlocking_technologies']=root('organization')
        with self.assertRaises(ValueError):validate(self.policy,self.target,self.advances,self.units,{})
        del self.target.techs['base']['unlocking_technologies']
        self.policy['rules']['base']['any_of']=[{}]
        with self.assertRaises(ValueError):validate(self.policy,self.target,self.advances,self.units,{})


if __name__=='__main__':unittest.main()
