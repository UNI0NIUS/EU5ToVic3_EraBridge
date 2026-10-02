import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from collections import Counter

from audit_subsistence_jobs import audit


class SubsistenceAuditTests(TestCase):
    def sample(self):
        return '''date=1836.1.1
        meta_data={version="1.13.11" mods={"fixture"}}
        country_manager={database={1={definition=ITA} 2={definition=BOH}}}
        states={database={
            10={country=1 region=STATE_FULL arable_land=1}
            11={country=1 region=STATE_EMPTY arable_land=1}
            12={country=2 region=STATE_FOREIGN arable_land=1}
        }}
        building_manager={database={
            20={building=building_subsistence_farm state=10 levels=1 production_methods={pm_test}}
            21={building=building_subsistence_farm state=11 levels=1 production_methods={pm_test}}
            22={building=building_subsistence_farm state=12 levels=1 production_methods={pm_test}}
        }}
        pops={database={
            30={type=peasants location=10 workplace=20 workforce=80 dependents=240}
            31={type=slaves location=10 workplace=20 workforce=20 dependents=60}
            32={type=laborers location=10 workforce=50 dependents=150}
            33={type=laborers location=11 workforce=5 dependents=15}
            34={type=laborers location=12 workforce=10 dependents=30}
        }}'''

    def test_only_local_vacancies_can_absorb_unemployment(self):
        with TemporaryDirectory() as d:
            path=Path(d)/'save.txt';path.write_text(self.sample(),encoding='utf-8')
            before=path.read_bytes()
            with patch('audit_subsistence_jobs.Target') as target:
                target.return_value.numeric.return_value=Counter({'building_employment_peasants_add':100})
                result=audit(path,{'ITA'})
            self.assertEqual(before,path.read_bytes())
        c=result['countries']['ITA']
        self.assertEqual(c['unemployed_workers'],55)
        self.assertEqual(c['possible_local_reassignment_workers'],5)
        self.assertEqual(c['unemployment_beyond_local_subsistence_vacancies'],50)
        self.assertEqual(c['vacant_peasant_slots'],100)
        self.assertEqual(c['subsistence_workers'],100)
        self.assertEqual(c['population'],620)
        self.assertEqual(len(result['states']),2)
        # A report must never serialize parser Object reprs containing the save.
        self.assertLess(len(json.dumps(result)),10000)


if __name__=='__main__': main()
