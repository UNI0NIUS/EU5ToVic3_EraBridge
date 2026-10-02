import unittest
from political_historical_context import classify_migration,historical_candidates,GEOGRAPHIC_REGION_OVERRIDES,macro_region
import test_political_rules as base
from test_political_rules import fixture_catalog
from build_political_rules_report import evaluate
from political_rulebook import rulebook


class HistoricalContextTest(unittest.TestCase):
    def test_american_immigrant_exception(self):
        groups={'italian':'heritage_group_european','native':'heritage_group_indigenous_american'}
        self.assertTrue(classify_migration('05_north_america',True,['italian'],groups,'recognized')['eligible'])
        for region,independent,heritages,kind in [
            ('00_west_europe',True,['italian'],'recognized'),
            ('05_north_america',False,['italian'],'recognized'),
            ('05_north_america',True,['native'],'recognized'),
            ('05_north_america',True,['italian','native'],'recognized'),
            ('05_north_america',True,[None],'recognized'),
            ('05_north_america',True,['italian'],'decentralized'),
            ('05_north_america',True,['italian'],'colonial')]:
            with self.subTest(region=region,heritages=heritages,kind=kind):
                self.assertFalse(classify_migration(region,independent,heritages,groups,kind)['eligible'])

    def test_african_diaspora_is_not_excluded_by_race(self):
        self.assertTrue(classify_migration('06_central_america',True,['diaspora'],{'diaspora':'heritage_group_african'},'recognized')['eligible'])

    def test_hawaii_is_oceania_despite_native_map_filename(self):
        region=GEOGRAPHIC_REGION_OVERRIDES['STATE_HAWAIIAN_ISLANDS']
        self.assertFalse(classify_migration(region,True,['polynesian'],{'polynesian':'heritage_group_indigenous_oceanic'},'recognized')['eligible'])
        self.assertEqual(macro_region('00_west_europe'),macro_region('02_east_europe'))

    def test_source_open_borders_alone_now_means_controls(self):
        r=base.PoliticalRulesTest().run_case(['open_borders_law'])
        self.assertEqual(r['laws']['lawgroup_migration']['law'],'law_migration_controls')

    def test_exception_requires_source_open_law(self):
        context={'facts':['american_independent_immigrant']}
        for policy,expected in [('open_borders_law','law_no_migration_controls'),('closed_borders_law','law_closed_borders'),(None,'law_migration_controls')]:
            r=base.PoliticalRulesTest().run_case([policy] if policy else [],historical_context=context)
            self.assertEqual(r['laws']['lawgroup_migration']['law'],expected)

    def test_historical_priors_do_not_override_explicit_policy(self):
        prior=dict(id='historical.test',group='lawgroup_trade_policy',law='law_protectionism',priority=35,
                   reason='test',evidence=[],confidence='historical_inference')
        r=base.PoliticalRulesTest().run_case(['free_trade_policy'],historical_priors=[prior])
        self.assertEqual(r['laws']['lawgroup_trade_policy']['law'],'law_free_trade')

    def test_unverified_native_law_not_a_reference(self):
        context={'facts':['developed_market_administration','settled_state'],'primary_heritages':['x'],'capital_region':'r'}
        native={'countries':{'GBR':{'law_sequence':['law_interventionism','law_traditionalism'],'file':'test','region':'other','heritages':['y']}}}
        rows=historical_candidates(context,native,fixture_catalog())
        self.assertFalse(any(r['law']=='law_interventionism' for r in rows))

    def test_weak_fiscal_prior_cannot_delete_traditional_economy(self):
        catalog=fixture_catalog()
        catalog['law_per_capita_based_taxation']={'group':'lawgroup_taxation','disallowing_laws':['law_traditionalism'],
             'technologies':[],'unlocking_laws':[],'institution':None,'script':''}
        prior=dict(id='historical.tax',group='lawgroup_taxation',law='law_per_capita_based_taxation',priority=40,
                   reason='test',evidence=[],confidence='historical_inference')
        r=evaluate({'government':'monarchy'},{},{},catalog,rulebook(),historical_priors=[prior])
        self.assertEqual(r['laws']['lawgroup_taxation']['law'],'law_land_based_taxation')
        self.assertEqual(r['laws']['lawgroup_economic_system']['law'],'law_traditionalism')
        self.assertFalse(any(v['confidence']=='blocked' for v in r['laws'].values()))

    def test_cultural_prior_requires_cohort_agreement(self):
        context={'facts':[],'primary_heritages':['x'],'capital_region':'r'}
        native={'countries':{t:{'law_sequence':['law_guild_system'],'file':'test','region':'r','heritages':['x']} for t in ['A','B']}}
        rows=historical_candidates(context,native,fixture_catalog())
        self.assertTrue(any(r['law']=='law_guild_system' for r in rows))
        native['countries']['B']['heritages']=['y']
        self.assertFalse(historical_candidates(context,native,fixture_catalog()))


if __name__=='__main__':unittest.main()
