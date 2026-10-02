from collections import Counter, defaultdict
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from economy_capacity import Ledger, carry_land, write_land
from economy_geography import constrain_existing
from economy_source_structure import seed_resources
from extract_m3_politics import fields
from pdx_text import root


def fixture(pop=100000):
    states={'A':{'arable_land':'10','arable_resources':root('farm ranch'),
                 'subsistence_building':'subsistence','capped_resources':root('wood=20')},
            'B':{'arable_land':'10','arable_resources':root('farm ranch'),
                 'subsistence_building':'subsistence','capped_resources':root('wood=1 mine=10')}}
    target=SimpleNamespace(states=states,aliases={},buildings={k:{} for k in ['farm','ranch','wood','mine','factory','subsistence']},
                           select=lambda *args:[],coefficients=lambda *args:{'jobs':5000})
    ledger=Ledger(target,[],{('A','X'):pop,('A','Y'):pop},{'X':set(),'Y':set()},{'X':set(),'Y':set()},
                  {'A':{str(i):'X' if i==0 else 'Y' for i in range(25)},'B':{'a':'X'}},defaultdict(set),
                  {'workforce_share':.25,'maximum_formal_workforce_share':.25,'formal_staffing_safety_fraction':.75,
                   'rural_classes':['peasants'],'commercial_rural_workforce_limit':1,'geography_policy':'vanilla_capacity'})
    return ledger


class GeographyTests(unittest.TestCase):
    def test_restore_state_that_originally_had_no_fixed_resource_block(self):
        with TemporaryDirectory() as directory:
            p=Path(directory);game=p/'game';base=p/'base';out=p/'out'
            for folder in [game,base]:(folder/'map_data/state_regions').mkdir(parents=True)
            (game/'map_data/state_regions/states.txt').write_text('A={\n arable_land=10\n provinces={x1}\n}')
            (base/'map_data/state_regions/states.txt').write_text('A={\n arable_land=100\n provinces={x1}\n capped_resources={wood=50}\n custom_field=kept\n}')
            target=SimpleNamespace(game=game,states={'A':{'arable_land':'10'}})
            write_land(target,base,out,{'A':10},{'A':True})
            state=fields(root((out/'map_data/state_regions/states.txt').read_text(encoding='utf-8-sig')).fields()['A'])
            self.assertEqual(state['arable_land'],'10')
            self.assertEqual(fields(state['capped_resources']),{})
            self.assertEqual(state['custom_field'],'kept')

    def test_small_fragment_and_huge_population_do_not_create_land(self):
        ledger=fixture(100000000)
        land,audit=carry_land(ledger,Counter(),{'X','Y'})
        self.assertEqual(land,{})
        self.assertEqual(sum(r['new_arable_share'] for r in audit),10)
        self.assertGreater(sum(r['capacity_gap_full_staffing'] for r in audit),49000000)
        self.assertTrue(all(r['unmet_arable_demand']>0 for r in audit))

    def test_source_jobs_cannot_multiply_small_fragment_resource_cap_or_create_deposit(self):
        ledger=fixture()
        changes=seed_resources(ledger,{('A','X','wood'):95000,('A','X','mine'):100000}, {'X'})
        self.assertEqual(changes,{})
        self.assertEqual(ledger.rows['A','X','wood']['levels'],1)  # 1/25 of original 20
        self.assertNotIn(('A','X','mine'),ledger.rows)
        report={r['building']:r for r in ledger.source_resource_requests}
        self.assertEqual(report['wood']['requested_levels'],5)
        self.assertEqual(report['wood']['geographic_shortfall'],4)
        self.assertEqual(report['mine']['geographic_share'],0)

    def test_farms_share_one_envelope_and_missing_resource_is_zero(self):
        ledger=fixture(1000000)
        ledger.source_classes['A','Y','peasants']=1000000
        ledger.put('A','Y','farm',7,'seed')
        ledger.put('A','Y','ranch',2,'seed')
        self.assertEqual(ledger.capped_room('A','Y','farm'),1)
        self.assertEqual(ledger.capped_room('A','Y','ranch'),1)
        self.assertEqual(ledger.capped_room('A','X','mine'),0)

    def test_constrain_existing_cuts_only_overflow_and_keeps_industry(self):
        ledger=fixture(1000000)
        for kind,n in [('farm',8),('ranch',8),('wood',22),('factory',9)]:
            ledger.put('A','Y',kind,n,'seed')
        changes=constrain_existing(ledger)
        self.assertEqual(sum(r['levels'] for r in ledger.local('A','Y') if r['building'] in {'farm','ranch'}),10)
        self.assertEqual(ledger.rows['A','Y','wood']['levels'],19)
        self.assertEqual(ledger.rows['A','Y','factory']['levels'],9)
        self.assertEqual(sum(r['displaced_job_capacity'] for r in changes),45000)

    def test_explicit_legacy_mode_reproduces_old_inflation_for_audit(self):
        ledger=fixture()
        ledger.config['geography_policy']='legacy_employment_expansion'
        changes=seed_resources(ledger,{('A','X','wood'):95000},{'X'})
        self.assertEqual(changes['A']['wood']['after'],125)


if __name__=='__main__':unittest.main()
