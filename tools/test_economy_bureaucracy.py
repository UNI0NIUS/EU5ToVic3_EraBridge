import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from economy_bureaucracy import AdministrationBudget, KIND, incorporated_states, institution_levels
from pdx_text import root


class BudgetTests(unittest.TestCase):
    def test_actual_split_state_incorporation(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'states.txt'
            p.write_text('STATES = { s:STATE_A = { create_state = { country = c:AAA state_type = incorporated } create_state = { country = c:BBB state_type = unincorporated } } }')
            self.assertEqual(incorporated_states(p), {('STATE_A', 'AAA')})

    def test_enabled_default_and_explicit_investment(self):
        laws = {'school': {'institution': 'schools'}, 'police': {'institution': 'police'}}
        h = root('set_institution_investment_level = { institution = schools level = 3 } set_institution_investment_level = { institution = health level = 5 }')
        self.assertEqual(institution_levels(h, laws, laws), {'schools': 3, 'police': 1})

    def model(self):
        m = AdministrationBudget.__new__(AdministrationBudget)
        m.tags = {'AAA'}
        m.policy = {'staffing_fraction': .75, 'demand_reserve_fraction': .15,
                    'minimum_other_cost_reserve': 25, 'institution_cost_per_population_unit': 1}
        m.defines = dict(STATE_BUREAUCRACY_BASE_COST=10, STATE_BUREAUCRACY_POP_BASE_COST=4,
                        STATE_BUREAUCRACY_POP_MULTIPLE=100000, MINIMUM_INVESTMENT_COST=10,
                        BUILDING_LEVEL_BUREAUCRACY_COST=1)
        m.modifiers = {'AAA': Counter(country_bureaucracy_add=100, state_bureaucracy_population_base_cost_factor_mult=-.25)}
        m.institutions = {'AAA': {'schools': 2}}
        m.incorporated = {('A', 'AAA')}
        ledger = SimpleNamespace(population={('A', 'AAA'): 10000000, ('B', 'AAA'): 90000000}, rows={}, by_country={'AAA': set()},
                                 target=SimpleNamespace(pms={'cabinet': {'country_modifiers': root('workforce_scaled = { country_bureaucracy_add = 50 }')}}))
        ledger.balance = lambda tag: Counter(paper=0)
        ledger.allowed = lambda kind, tag: True
        ledger.pms = lambda kind, tag: ['cabinet']
        ledger.capped_room = lambda s, t, k: 100
        def add(s, t, k, n, reason, methods):
            key = s, t, k
            row = ledger.rows.setdefault(key, {'levels': 0, 'pms': methods, 'building': k, 'body': 'level = 1'})
            row['levels'] += n
            ledger.by_country[t].add(key)
        ledger.add = add
        ledger.put = lambda *a: None
        m.ledger = ledger
        return m

    def test_cost_excludes_unincorporated_population_and_applies_law(self):
        b = self.model().budget('AAA')
        self.assertEqual(b['incorporated_population'], 10000000)
        self.assertEqual(b['state_cost'], 310)
        self.assertEqual(b['institution_costs'], {'schools': 200})

    def test_floor_overrides_unprofitable_local_tax_screen_and_honours_staffing(self):
        m = self.model()
        rows = [{'state': 'A', 'country': 'AAA', 'added_levels': 0, 'remaining_tax_capacity_gap': 400,
                 'tax_capacity_per_level': 10, 'weekly_cost_per_level_at_reference_wage': 500,
                 'reference_revenue_per_added_capacity': 1}]
        m.provision(rows)
        self.assertEqual(m.budget('AAA')['planning_gap'], 0)
        self.assertGreater(m.ledger.rows['A', 'AAA', KIND]['levels'], 0)
        self.assertNotIn(('B', 'AAA', KIND), m.ledger.rows)
        count = m.budget('AAA')['government_administration_levels']
        m.provision(rows)
        self.assertEqual(m.budget('AAA')['government_administration_levels'], count)

    def test_capacity_shortage_is_reported_without_inventing_labor(self):
        m = self.model()
        m.ledger.capped_room = lambda *args: 0
        result = m.provision([])
        self.assertGreater(result[0]['unplaced_levels'], 0)
        self.assertEqual(m.audit()['countries_with_planning_gap'], ['AAA'])

    def test_political_update_preserves_valid_existing_administration_methods(self):
        m = self.model()
        m.provision([])
        m.ledger.techs = {'AAA': set()}
        m.ledger.laws = {'AAA': set()}
        m.ledger.target.available = lambda *args: True
        rewrites = []
        m.ledger.put = lambda *args: rewrites.append(args)
        m.provision([], preserve_existing_methods=True)
        self.assertEqual(rewrites, [])
        m.ledger.target.available = lambda *args: False
        m.provision([], preserve_existing_methods=True)
        self.assertTrue(rewrites)


if __name__ == '__main__': unittest.main()
