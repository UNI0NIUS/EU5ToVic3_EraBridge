from unittest import TestCase
from unittest.mock import patch
import test_converter_arable_advice as advice_fixture
import test_converter_edits as edit_fixture
from converter_arable_advice import plan_bulk
from converter_edits import materialize


class ArableBulkTests(TestCase):
    setUp=advice_fixture.ArableAdviceTests.setUp
    def plan(self,cap=2):
        self.row['risks']=['unemployment'];self.other['risks']=[]
        with patch('converter_arable_advice.materialize',return_value=self.view):
            return plan_bulk(self.world,self.options,[],['S|AAA'],cap)

    def test_cap_applies_to_whole_state_once_and_reports_unresolved(self):
        op=self.plan()
        self.assertEqual(op['targets'],[dict(state='S',before=100,value=200,cap=200)])
        self.assertEqual(op['limited'],['S|AAA'])

    def test_large_cap_stops_at_required_land_not_ceiling(self):
        op=self.plan(10)
        self.assertEqual(op['targets'][0]['value'],710)
        self.assertEqual(op['limited'],[])

    def test_zero_base_is_not_multiplied_into_fabricated_land(self):
        self.row['state_arable']=0
        with self.assertRaises(ValueError):self.plan()

    def test_invalid_multiplier_rejected(self):
        for cap in (1,float('nan'),float('inf'),101,True):
            with self.assertRaises(ValueError):self.plan(cap)


class ArableBulkReplayTests(TestCase):
    setUp=edit_fixture.EditTests.setUp
    def test_replay_cap_staleness_and_undo(self):
        op=dict(kind='arable_bulk',max_multiplier=2,targets=[dict(state='S',before=10,value=20)])
        view=materialize(self.world,[op]);self.assertEqual(view.target.states['S']['arable_land'],'20')
        self.assertEqual(materialize(self.world,[]).target.states['S']['arable_land'],'10')
        self.assertEqual(sum(view.population.values()),151)
        with self.assertRaisesRegex(ValueError,'变化'):materialize(self.world,[op,op])
        op['targets'][0]['value']=21
        with self.assertRaisesRegex(ValueError,'上限'):materialize(self.world,[op])

    def test_core_country_survives_annexation_in_definitions(self):
        p=self.mod/'common/country_creation';p.mkdir()
        (p/'00_releasable_countries.txt').write_text('BBB={states={S} required_num_states=1}')
        from converter_reconcile import reconcile
        files,_=reconcile(self.world,materialize(self.world,[dict(kind='country',source='BBB',target='AAA')]))
        self.assertIn('BBB',files['common/country_definitions/a.txt'])
