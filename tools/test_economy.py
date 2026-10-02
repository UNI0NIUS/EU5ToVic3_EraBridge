import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from economy_model import (Target, apportioned, building_rows, closure, definitions, render_buildings)
from technology_mapping import TechnologyMapper
from pdx_text import root


class TechnologyTests(unittest.TestCase):
    def make_mapper(self, extra=''):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        advances = p/'in_game/common/advances'; advances.mkdir(parents=True)
        (p/'in_game/common/building_types').mkdir()
        (advances/'0_generic.txt').write_text('''
            farm = { age = age_1_traditions global_monthly_food_modifier = 1 }
            factory = { age = age_6_revolutions global_production_efficiency = 1 }
            track_invention = { age = age_6_revolutions unlock_road_type = railroad }
        ''', encoding='utf-8')
        if extra: (advances/'culture_example.txt').write_text(extra, encoding='utf-8')
        techs = {k: dict(o.entries()) for k,o in root('''
            manufacturies = { category = production era = era_1 }
            atmospheric_engine = { category = production era = era_2 unlocking_technologies = { manufacturies } }
            railways = { category = production era = era_2 unlocking_technologies = { atmospheric_engine } }
            electricity = { category = production era = era_3 }
        ''').entries()}
        target = SimpleNamespace(techs=techs, buildings={'building_railway': dict(root('unlocking_technologies = { railways }').entries())}, pms={})
        policy = {'age_weights': {str(i): i for i in range(7)}, 'era_thresholds': {'era_1': [0.1,0.5], 'era_2': [0.1,0.2]}}
        return TechnologyMapper(p, target, {'manufacturies','atmospheric_engine','railways'}, policy, [])

    def test_semantic_railroad_unlock_not_specific_advance_name(self):
        mapper = self.make_mapper()
        techs, report = mapper.map({'advances':['track_invention'], 'institutions':[]})
        self.assertEqual(techs, {'railways','atmospheric_engine','manufacturies'})
        self.assertEqual(report['decisions']['railways']['decision'], 'semantic_unlock')
        self.assertFalse(report['decisions']['electricity']['researched'])

    def test_progress_and_generic_building_evidence_do_not_invent_railways(self):
        mapper = self.make_mapper()
        techs, report = mapper.map({'advances':['farm','factory'], 'institutions':[]})
        self.assertNotIn('railways', techs)
        self.assertEqual(len(report['decisions']), 4)

    def test_country_exclusive_nodes_do_not_lower_progress(self):
        first = self.make_mapper()
        _, before = first.map({'advances':['farm','factory'], 'institutions':[]})
        second = self.make_mapper('foreign_factory = { age = age_6_revolutions potential = { tag = X } global_production_efficiency = 9 }')
        _, after = second.map({'advances':['farm','factory'], 'institutions':[]})
        self.assertEqual(before['branch_progress'], after['branch_progress'])
        self.assertEqual(len(second.source), len(first.source)+1)

    def test_unknown_researched_advance_is_not_silently_ignored(self):
        mapper = self.make_mapper()
        with self.assertRaisesRegex(ValueError, 'Unknown researched'):
            mapper.map({'advances':['missing'], 'institutions':[]})

    def test_prerequisite_cycles_and_missing_nodes_rejected(self):
        techs = {k: dict(o.entries()) for k,o in root('a = { unlocking_technologies = { b } } b = { unlocking_technologies = { a } }').entries()}
        with self.assertRaisesRegex(ValueError, 'cycle'): closure({'a'}, techs)
        with self.assertRaisesRegex(ValueError, 'Undefined'): closure({'x'}, techs)


class EconomicTests(unittest.TestCase):
    def test_allocation_does_not_inflate_tiny_state_shares(self):
        self.assertEqual(sum(apportioned({str(i): .1 for i in range(100)}).values()), 10)
        self.assertEqual(apportioned({'b':1,'a':1},1), {'b':0,'a':1})
        with self.assertRaises(ValueError): apportioned({'a': -1})

    def test_pm_signed_flows_and_technology_throughput(self):
        t = Target.__new__(Target)
        t.aliases = {}; t.prices = {'cloth':20, 'iron':40}
        t.pms = {k:dict(o.entries()) for k,o in root('''
          base = { building_modifiers = { workforce_scaled = { goods_input_iron_add = 5 goods_output_cloth_add = 20 } level_scaled = { building_employment_laborers_add = 100 } } }
          automation = { building_modifiers = { workforce_scaled = { goods_output_cloth_add = -5 } level_scaled = { building_employment_laborers_add = -20 } } }
        ''').entries()}
        t.techs = {'advanced':dict(root('modifier = { building_factory_throughput_add = 0.25 }').entries())}
        c=t.coefficients('building_factory',['base','automation'],{'advanced'})
        self.assertEqual(c['jobs'],80); self.assertEqual(c['outputs']['cloth'],18.75)
        self.assertEqual(c['inputs']['iron'],6.25); self.assertEqual(c['gross'],375)

    def test_conditional_monument_and_ownership_levels_roundtrip(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'history.txt'
            p.write_text('BUILDINGS={s:STATE_X={region_state:ABC={if={limit={has_dlc=yes} create_building={building=monument level=1}} create_building={building=factory add_ownership={building={levels=2} country={levels=3}} activate_production_methods={base}}}}}',encoding='utf-8')
            first=building_rows(p)
            p.write_text(render_buildings(first),encoding='utf-8')
            second=building_rows(p)
            self.assertEqual({r['building']:r['levels'] for r in second},{'monument':1,'factory':5})
            self.assertEqual(tuple(g.strip() for g in next(r for r in second if r['building']=='monument')['guards']),
                             tuple(g.strip() for g in first[0]['guards']))


if __name__ == '__main__': unittest.main()
