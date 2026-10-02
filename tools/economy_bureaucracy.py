"""National administration planning floor; estimates are not runtime budgets."""
from collections import Counter
import math
import re
from extract_m3_politics import fields
from pdx_text import Object, root
from economy_model import definitions
from economy_administration import pm_modifier

KIND = 'building_government_administration'


def incorporated_states(path):
    result = set()
    for state, obj in fields(root(path.read_text(encoding='utf-8-sig')))['STATES'].entries():
        for key, value in obj.entries():
            if key != 'create_state': continue
            f = fields(value)
            if f.get('state_type') == 'incorporated':
                result.add((state.removeprefix('s:'), f['country'].removeprefix('c:')))
    return result


def institution_levels(history, active, laws):
    # An enabling law starts an institution at one, even without an explicit override.
    result = {laws[l]['institution']: 1 for l in active if 'institution' in laws[l]}
    for key, value in history.entries():
        if key == 'set_institution_investment_level':
            f = fields(value)
            if f['institution'] in result: result[f['institution']] = int(f['level'])
        elif isinstance(value, Object) and 'set_institution_investment_level' in value.text():
            raise ValueError('Conditional institution investment needs explicit resolution')
    return result


class AdministrationBudget:
    def __init__(self, ledger, tags, history, state_history, policy):
        self.ledger, self.tags, self.policy = ledger, tags, policy
        self.incorporated = incorporated_states(state_history)
        self.laws = definitions(ledger.target.game/'common/laws')
        text = (ledger.target.game/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig')
        keys = ('STATE_BUREAUCRACY_BASE_COST', 'STATE_BUREAUCRACY_POP_BASE_COST',
                'STATE_BUREAUCRACY_POP_MULTIPLE', 'MINIMUM_INVESTMENT_COST', 'BUILDING_LEVEL_BUREAUCRACY_COST')
        self.defines = {k: float(re.search(r'\b'+k+r'\s*=\s*([\d.]+)', text)[1]) for k in keys}
        self.modifiers, self.institutions = {}, {}
        for tag in sorted(tags):
            mods = Counter({k: float(v) for k, v in ledger.target.base_modifiers.items()
                            if 'bureaucracy' in k or k.startswith('country_institution_cost_')})
            for f in [*(ledger.target.techs[t] for t in sorted(ledger.techs[tag])),
                      *(self.laws[l] for l in sorted(ledger.laws[tag]))]:
                for k, v in fields(f.get('modifier')).items():
                    if 'bureaucracy' in k or k.startswith('country_institution_cost_'): mods[k] += float(v)
            self.modifiers[tag] = mods
            self.institutions[tag] = institution_levels(history[tag], ledger.laws[tag], self.laws)

    def budget(self, tag):
        ledger, p, d, m = self.ledger, self.policy, self.defines, self.modifiers[tag]
        states = [(s, pop) for (s, t), pop in ledger.population.items() if t == tag and (s, t) in self.incorporated]
        population = sum(pop for s, pop in states)
        state_cost = len(states)*d['STATE_BUREAUCRACY_BASE_COST'] + population/d['STATE_BUREAUCRACY_POP_MULTIPLE']*d['STATE_BUREAUCRACY_POP_BASE_COST']*max(0, 1+m['state_bureaucracy_population_base_cost_factor_mult'])
        # Per-person investment scaling is a configurable engine-model assumption;
        # the population unit and minimum are read from the installed game's defines.
        factor = max(d['MINIMUM_INVESTMENT_COST'], population/d['STATE_BUREAUCRACY_POP_MULTIPLE']*p['institution_cost_per_population_unit']*max(0, 1+m['country_bureaucracy_investment_cost_factor_mult']))
        institutions = {i: level*factor*max(0, 1+m['country_institution_cost_'+i+'_mult']) for i, level in self.institutions[tag].items()}
        rows = [ledger.rows[k] for k in sorted(ledger.by_country[tag]) if k in ledger.rows]
        # Public-service levels are included as a conservative ownership allowance.
        # This intentionally overestimates: not every public service is charged by the engine.
        public_levels = sum(r['levels'] for r in rows if r.get('body') and
                            re.search(r'(?m)^\s*level\s*=', r['body']))
        ownership = public_levels*d['BUILDING_LEVEL_BUREAUCRACY_COST']
        demand = state_cost+sum(institutions.values())+ownership
        required = demand*(1+p['demand_reserve_fraction'])+p['minimum_other_cost_reserve']
        output = sum(pm_modifier(ledger.target, r['pms'], 'country_modifiers', 'country_bureaucracy_add')*r['levels'] for r in rows if r['building'] == KIND)
        mult = max(0, 1+m['country_bureaucracy_mult'])
        full = (m['country_bureaucracy_add']+output)*mult
        planned = (m['country_bureaucracy_add']+output*p['staffing_fraction'])*mult
        return {'country': tag, 'incorporated_states': len(states), 'incorporated_population': population,
                'institution_levels': self.institutions[tag], 'institution_costs': institutions,
                'state_cost': state_cost, 'public_ownership_allowance': ownership,
                'estimated_demand': demand, 'required_with_reserve': required,
                'government_administration_levels': sum(r['levels'] for r in rows if r['building'] == KIND),
                'full_staffing_supply': full, 'planned_supply': planned,
                'planning_gap': max(0, required-planned), 'full_staffing_balance': full-demand,
                'core_demand_gap_at_planned_staffing': max(0, demand-planned),
                'paper_net_industrial_supply': ledger.balance(tag)['paper']}

    def provision(self, local_tax_report, preserve_existing_methods=False):
        ledger, changes = self.ledger, []
        tax = {(r['state'], r['country']): r for r in local_tax_report}
        for tag in sorted(self.tags):
            before = self.budget(tag)
            candidates = [s for s, t in ledger.population if t == tag]
            if not ledger.allowed(KIND, tag):
                changes.append({'country': tag, 'before': before, 'added_levels': 0, 'reason': 'technology_locked'})
                continue
            methods = ledger.pms(KIND, tag)
            # Include administrations in unincorporated states: they still produce BUR.
            for state in candidates:
                old = ledger.rows.get((state, tag, KIND))
                if old and not (preserve_existing_methods and all(ledger.target.available(pm, ledger.techs[tag], ledger.laws[tag]) for pm in old['pms'])):
                    ledger.put(state, tag, KIND, old['levels'], 'unlocked_national_administration', methods)
            per_level = pm_modifier(ledger.target, methods, 'country_modifiers', 'country_bureaucracy_add')
            net = per_level*self.policy['staffing_fraction']*max(0, 1+self.modifiers[tag]['country_bureaucracy_mult']) - self.defines['BUILDING_LEVEL_BUREAUCRACY_COST']*(1+self.policy['demand_reserve_fraction'])
            if net <= 0: raise ValueError('Administration cannot cover its own planning cost: '+tag)
            needed = max(0, math.ceil(self.budget(tag)['planning_gap']/net-1e-9))
            added = 0
            while needed:
                eligible = [s for s in candidates if ledger.capped_room(s, tag, KIND) > 0]
                if not eligible: break
                def score(s):
                    row = tax.get((s, tag), {})
                    existing = ledger.rows.get((s, tag, KIND), {}).get('levels', 0)
                    # First reduce tax collection gaps, then spread by population/load.
                    gap = max(0, row.get('remaining_tax_capacity_gap', 0))
                    return (-gap, -(ledger.population[s, tag]/(1+existing)), s)
                state = min(eligible, key=score)
                ledger.add(state, tag, KIND, 1, 'national_bureaucracy_floor', methods)
                added += 1; needed -= 1
                if (state, tag) in tax:
                    tax[state, tag]['remaining_tax_capacity_gap'] = max(0, tax[state, tag]['remaining_tax_capacity_gap']-tax[state, tag]['tax_capacity_per_level'])
                    tax[state, tag]['national_floor_added_levels'] = tax[state, tag].get('national_floor_added_levels', 0)+1
            changes.append({'country': tag, 'before': before, 'added_levels': added, 'unplaced_levels': needed})
        return changes

    def audit(self):
        rows = [self.budget(t) for t in sorted(self.tags)]
        return {'status': 'static_planning_estimate_runtime_pending', 'policy': self.policy,
                'defines': self.defines, 'countries': rows,
                'countries_with_planning_gap': [r['country'] for r in rows if r['planning_gap'] > .001],
                'countries_below_core_demand': [r['country'] for r in rows if r['core_demand_gap_at_planned_staffing'] > .001],
                'limitations': ['Actual hiring, qualifications, input shortages and government wages require game testing.',
                                'No positive credit for throughput, power blocs, interest groups, rulers or temporary modifiers.',
                                'Public ownership is an upper allowance; commanders and unmodelled costs use the reserve.',
                                'Institution per-person coefficient is a planning assumption pending 1.13.11 runtime cross-check.']}
