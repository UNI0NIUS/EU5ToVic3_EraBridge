"""Regression tests for the regional exporter, including cross-state references."""
import copy
import tempfile
import unittest
from pathlib import Path

from build_m2_prototype import Prototype, allocate, patch, remap_local_investors, resolve_mapping
from pdx_text import root


class M2Tests(unittest.TestCase):
    def test_remainders_conserve_tiny_and_large_populations(self):
        for count in [0, 1, 7, 8, 1000000001]:
            split = allocate(count, {'ITA': 7, 'PAP': 1})
            self.assertEqual(count, sum(split.values()))
            self.assertTrue(all(n >= 0 for n in split.values()))
        self.assertEqual({'ITA': 1, 'PAP': 0}, allocate(1, {'ITA': 7, 'PAP': 1}))
        with self.assertRaises(ValueError):
            allocate(5, {})

    def test_external_investors_keep_their_home_country(self):
        source = 'add_ownership={ country={country="c:FRA" levels=1} building={country="c:FRA" region="STATE_PARIS" levels=2} building={country="c:FRA" region="STATE_PROVENCE" levels=3} }'
        result = remap_local_investors(source, 'STATE_PROVENCE', 'FRA', 'ITA')
        self.assertIn('country="c:FRA" region="STATE_PARIS"', result)
        self.assertIn('country="c:ITA" region="STATE_PROVENCE"', result)
        self.assertIn('country="c:ITA" levels=1', result)

    def test_span_edits_reject_overlap(self):
        self.assertEqual('aXdeY', patch('abcdef', [(1, 3, 'X'), (5, 6, 'Y')]))
        with self.assertRaises(ValueError):
            patch('abcdef', [(1, 4, 'X'), (3, 5, 'Y')])

    def test_mapping_refuses_missing_provinces_and_mixed_owners(self):
        definitions = root('STATE_ONE={provinces={x111111 x222222}}').fields()
        audit = {'countries': [{'id': 1, 'tag': 'ITA'}, {'id': 2, 'tag': 'PAP'}],
                 'locations': [{'name': 'roma', 'owner': 1}, {'name': 'avignon', 'owner': 2}]}
        profile = {'states': {'STATE_ONE': {'x111111': ['roma'], 'x222222': ['avignon']}}, 'country_tags': {'ITA': 'ITA', 'PAP': 'PAP'}}
        self.assertEqual('PAP', resolve_mapping(profile, audit, definitions)['STATE_ONE']['x222222'])
        missing = copy.deepcopy(profile)
        del missing['states']['STATE_ONE']['x222222']
        with self.assertRaises(ValueError):
            resolve_mapping(missing, audit, definitions)
        mixed = copy.deepcopy(profile)
        mixed['states']['STATE_ONE']['x111111'] = ['roma', 'avignon']
        with self.assertRaises(ValueError):
            resolve_mapping(mixed, audit, definitions)

    def test_export_transfers_units_repairs_investors_and_keeps_outside_state(self):
        with tempfile.TemporaryDirectory() as folder:
            game = Path(folder)
            files = {
                'map_data/state_regions/00_test.txt': 'STATE_ONE={provinces={x111111 x222222}}',
                'common/history/states/00_states.txt': 'STATES={s:STATE_ONE={create_state={country=c:SAR owned_provinces={x111111 x222222}} add_homeland=cu:north_italian} s:STATE_OUTSIDE={create_state={country=c:SAR owned_provinces={x333333}}}}',
                'common/history/pops/00_test.txt': 'POPS={s:STATE_ONE={region_state:SAR={create_pop={culture=north_italian size=5}}} s:STATE_OUTSIDE={region_state:SAR={create_pop={culture=north_italian size=8}}}}',
                'common/history/buildings/00_test.txt': 'BUILDINGS={s:STATE_ONE={region_state:SAR={create_building={building="building_wheat_farm" add_ownership={building={country="c:SAR" region="STATE_ONE" levels=1}}}}} s:STATE_OUTSIDE={region_state:SAR={create_building={building="building_wheat_farm" add_ownership={building={country="c:SAR" region="STATE_ONE" levels=1}}}}}}',
                'common/history/military_formations/00_test.txt': 'MILITARY_FORMATIONS={c:SAR ?={create_military_formation={type=army combat_unit={type=unit_type:combat_unit_type_line_infantry state_region=s:STATE_ONE count=2}}}}',
                'common/country_definitions/00_countries.txt': 'ITA={capital=STATE_OUTSIDE} SAR={capital=STATE_ONE}',
                'common/history/countries/sar - sardinia.txt': 'COUNTRIES={c:SAR ?={set_tax_level=medium}}',
                'common/history/population/sar - sardinia.txt': 'POPULATION={c:SAR ?={effect_starting_pop_wealth_high=yes}}',
            }
            for path, text in files.items():
                p = game / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding='utf-8')
            profile = {'states': {'STATE_ONE': {'x111111': ['roma'], 'x222222': ['avignon']}},
                       'country_tags': {'ITA': 'ITA', 'PAP': 'PAP'}, 'capital_overrides': {'ITA': 'STATE_ONE', 'SAR': 'STATE_OUTSIDE'}}
            audit = {'countries': [{'id': 1, 'tag': 'ITA'}, {'id': 2, 'tag': 'PAP'}],
                     'locations': [{'name': 'roma', 'owner': 1}, {'name': 'avignon', 'owner': 2}]}
            prototype = Prototype(game, profile, audit)
            prototype.build()
            self.assertEqual(5, sum(prototype.pop_after.values()))
            self.assertEqual(2, sum(x['count'] for x in prototype.moved_units))
            self.assertIn('c:ITA', prototype.outputs['common/history/military_formations/99_m2_formations.txt'])
            self.assertNotIn('combat_unit=', prototype.outputs['common/history/military_formations/00_test.txt'])
            self.assertIn('country="c:ITA" region="STATE_ONE"', prototype.outputs['common/history/buildings/00_test.txt'])
            for path, text in files.items():
                self.assertEqual(text, (game / path).read_text(encoding='utf-8'))
            # Corrupt an emitted scope: independent validation must catch it.
            path = 'common/history/pops/00_test.txt'
            prototype.outputs[path] = prototype.outputs[path].replace('region_state:ITA', 'region_state:FRA')
            with self.assertRaisesRegex(ValueError, 'Dangling output substate'):
                prototype.validate()


if __name__ == '__main__':
    unittest.main()
