"""Conservative opening PM choices and marginal expansion checks.

Domestic flows are a planning screen, not prices or a self-sufficiency mandate.
Inherited capacity is retained. Unknown imports never justify *extra* consumers.
"""
from collections import Counter
import math
import re

from economy_model import definitions
from extract_m3_politics import fields, sequence


def source_glass_methods(target, methods, techs, laws, weights):
    """One PM per regional factory: dominant actual porcelain, not generic pottery."""
    chosen = list(methods)
    if weights.get('porcelain', 0) <= sum(v for g,v in weights.items() if g!='porcelain'):
        return chosen
    if not target.available('pm_ceramics',techs,laws): return chosen
    for i,pm in enumerate(chosen):
        if pm == 'pm_disabled_ceramics': chosen[i] = 'pm_ceramics'
    return chosen


def naval_reserve(ledger, tag, utilization=1.0):
    """Supply-ship construction scenario, separate from ordinary shipyard inputs.

Uses native construction points and goods per completed hull. Utilization is an
explicit scenario, not a prediction of the engine's high/medium queue setting.
Does not include warship queues, ship modifications or construction maintenance.
"""
    if not 0 <= utilization <= 1:
        raise ValueError('Invalid ship construction utilization')
    if not hasattr(ledger, '_supply_ship'):
        ledger._supply_ship = definitions(ledger.target.game/'common/ship_types')['ship_type_supply_ship']
    ship = ledger._supply_ship
    points = 0
    for key in sorted(ledger.by_country[tag]):
        row = ledger.rows.get(key)
        if not row or row.get('guards'):
            continue
        for pm in row['pms']:
            for scale, obj in fields(ledger.target.pms[pm].get('country_modifiers')).items():
                value = float(fields(obj).get('country_ship_construction_add', 0))
                if value and scale not in ('workforce_scaled', 'level_scaled'):
                    raise ValueError('Unsupported ship construction scaling: '+scale)
                points += value*row['levels']
    return Counter({k[len('goods_input_'):-4]: float(v)*points*utilization/float(ship['base_construction_cost'])
                    for k, v in fields(ship['construction_goods']).items()
                    if k.startswith('goods_input_') and k.endswith('_add')})


def planning_balance(ledger, tag):
    result = ledger.balance(tag)
    policy = getattr(ledger, 'supply_chain_policy', {})
    if policy:
        result.subtract(naval_reserve(ledger, tag, policy['naval_construction_utilization']))
    return result


def planning_coefficients(ledger, kind, methods, tag):
    c = ledger.target.coefficients(kind, methods, ledger.techs[tag])
    policy = getattr(ledger, 'supply_chain_policy', {})
    if not policy: return c
    points = sum(float(fields(obj).get('country_ship_construction_add',0))
                 for pm in methods for scale,obj in fields(ledger.target.pms[pm].get('country_modifiers')).items()
                 if scale in ('workforce_scaled','level_scaled'))
    if not points: return c
    if not hasattr(ledger,'_supply_ship'):
        ledger._supply_ship = definitions(ledger.target.game/'common/ship_types')['ship_type_supply_ship']
    ship=ledger._supply_ship; inputs=Counter(c['inputs'])
    for k,v in fields(ship['construction_goods']).items():
        if k.startswith('goods_input_') and k.endswith('_add'):
            inputs[k[len('goods_input_'):-4]] += float(v)*points*policy['naval_construction_utilization']/float(ship['base_construction_cost'])
    return {**c,'inputs':inputs}


def household_plan(ledger, tag, balance=None):
    from complete_economy import living_requirements
    from economy_consumption import allocate
    wealth = getattr(ledger, 'supply_chain_policy', {}).get('household_wealth_scenario', 10)
    needs = living_requirements(ledger, tag, wealth)
    return needs, allocate(needs, planning_balance(ledger, tag) if balance is None else balance, ledger.target.prices)


def safe_delta(ledger, tag, delta, balance=None):
    """Do not deepen other deficits or reduce already supplied basic consumption."""
    before = planning_balance(ledger, tag) if balance is None else balance
    after = before.copy(); after.update(delta)
    if any(v < -1e-7 and after[g] < min(0, before[g])-1e-7 for g, v in delta.items()):
        return False
    needs, old = household_plan(ledger, tag, before)
    _, new = household_plan(ledger, tag, after)
    if any(new['shortfalls'][g] > old['shortfalls'][g]+1e-6 for g in old['shortfalls']):
        return False
    foods = {'grain', 'fish', 'meat', 'fruit', 'groceries'}
    food = lambda b: sum(b[g]*ledger.target.prices[g] for g in foods)
    floor = max(needs['basic_food']*1.1, getattr(ledger, 'food_reference_floors', {}).get(tag, 0))
    return food(after) >= min(food(before), floor)-1e-6


def net_delta(before, after, levels=1):
    result = Counter()
    for sign, c in ((-1, before), (1, after)):
        for g, n in c['outputs'].items(): result[g] += sign*n*levels
        for g, n in c['inputs'].items(): result[g] -= sign*n*levels
    return result


def alternatives(ledger, row):
    """Single-group changes only; unresolved script conditions remain excluded."""
    target, tag = ledger.target, row['owner']
    for group in sequence(target.buildings[row['building']]['production_method_groups']):
        choices = sequence(target.groups[group]['production_methods'])
        positions = [i for i, pm in enumerate(row['pms']) if pm in choices]
        if len(positions) != 1: raise ValueError('Incomplete or ambiguous PM group')
        i = positions[0]
        for pm in choices:
            if pm != row['pms'][i] and target.available(pm, ledger.techs[tag], ledger.laws[tag]):
                yield row['pms'][:i]+[pm]+row['pms'][i+1:]


def replace_pm(ledger, row, methods, reason):
    before = list(row['pms'])
    if before == methods: return
    if row.get('body') is not None:
        body, count = re.subn(r'\bactivate_production_methods\s*=\s*\{[^{}]*\}',
                             'activate_production_methods = { '+' '.join(methods)+' }', row['body'])
        if count != 1: raise ValueError('Ambiguous PM block')
        row['body'] = body
    row['pms'] = methods
    ledger.changes.append({'state': row['state'], 'country': row['owner'], 'building': row['building'],
                           'before': row['levels'], 'after': row['levels'], 'before_pms': before,
                           'after_pms': methods, 'reason': reason})


def improve_existing(ledger, tag, good, kinds):
    """Use existing capacity before spending scarce land/workers on more levels."""
    for key in sorted(ledger.by_country[tag]):
        row = ledger.rows.get(key)
        if not row or row['building'] not in kinds or row.get('guards'): continue
        if planning_balance(ledger, tag)[good] >= -1e-7: break
        old = planning_coefficients(ledger,row['building'],row['pms'],tag)
        choices = []
        for methods in alternatives(ledger, row):
            c = planning_coefficients(ledger,row['building'],methods,tag)
            delta = net_delta(old, c, row['levels'])
            # Retain occupation capacity and owner staffing during safe deployment.
            if c['jobs'] != old['jobs'] or delta[good] <= 1e-7: continue
            if not safe_delta(ledger, tag, delta): continue
            useful = min(delta[good], -planning_balance(ledger, tag)[good])
            choices.append((-useful, tuple(methods)))
        if choices:
            replace_pm(ledger, row, list(min(choices)[1]), 'existing_capacity_input_support_'+good)


def expansion_room(ledger, tag, kind, methods, room, output_good=None):
    """Bound extra consumer levels by available inputs; preserve inherited assets."""
    if not getattr(ledger, 'supply_chain_policy', None): return room
    c = planning_coefficients(ledger,kind,methods,tag)
    balance = planning_balance(ledger, tag)
    _, household = household_plan(ledger, tag, balance)
    for g, v in c['inputs'].items():
        net = v-c['outputs'].get(g, 0)
        if net <= 0: continue
        spare = max(0, balance[g]-household['goods_reserved'].get(g, 0))
        room = min(room, math.floor((spare+1e-7)/net))
    # Food consumption is a basket, so validate substitutions rather than
    # protecting all grain as if fish/meat could not feed anyone.
    if room and not safe_delta(ledger, tag, net_delta({'inputs': {}, 'outputs': {}}, c, room), balance):
        low, high = 0, room
        while low < high:
            mid = (low+high+1)//2
            if safe_delta(ledger, tag, net_delta({'inputs': {}, 'outputs': {}}, c, mid), balance): low = mid
            else: high = mid-1
        room = low
    return room


def moderate_glass(ledger, tag):
    """Keep factory levels/jobs; avoid high-output PMs without household support.

The guard reserves the *entire* household-items budget for glass, even though
paper/furniture compete for it. This is a generous demand scenario, not a quota
for national self-sufficiency. No source asset or potential export is deleted.
"""
    for key in sorted(ledger.by_country[tag]):
        row = ledger.rows.get(key)
        if not row or row['building'] != 'building_glassworks' or row.get('guards'): continue
        old = ledger.coefficients(row)
        balance = planning_balance(ledger, tag)
        needs, _ = household_plan(ledger, tag, balance)
        reserve = needs['household_items']/ledger.target.prices['glass']
        options = []
        for methods in alternatives(ledger, row):
            c = ledger.target.coefficients(row['building'], methods, ledger.techs[tag])
            delta = net_delta(old, c, row['levels'])
            if c['jobs'] != old['jobs'] or delta['glass'] >= -1e-7: continue
            if balance['glass']+delta['glass'] < reserve-1e-7: continue
            # Do not remove porcelain or other byproducts to treat a glass surplus.
            if any(c['outputs'].get(g, 0)<n for g,n in old['outputs'].items() if g!='glass'): continue
            old_cost = sum(n*ledger.target.prices[g] for g,n in old['inputs'].items())
            new_cost = sum(n*ledger.target.prices[g] for g,n in c['inputs'].items())
            if new_cost > old_cost+1e-7 or not safe_delta(ledger, tag, delta, balance): continue
            options.append((c['outputs'].get('glass', 0), new_cost, tuple(methods)))
        if options:
            replace_pm(ledger, row, list(min(options)[2]), 'glass_household_demand_and_input_cost_screen')


def apply(ledger, tags, policy, goods):
    ledger.supply_chain_policy = dict(policy)
    start = len(ledger.changes)
    # Glass may release an intermediate input, so follow it with input support.
    for tag in sorted(tags): moderate_glass(ledger, tag)
    for tag in sorted(tags):
        for good, kinds in goods.items(): improve_existing(ledger, tag, good, kinds)
    return ledger.changes[start:]


def audit(ledger, tags):
    result = {}
    for tag in sorted(tags):
        balance = ledger.balance(tag)
        planned = planning_balance(ledger, tag)
        result[tag] = {'ordinary_building_balance': dict(sorted(balance.items())),
                       'supply_ship_construction_scenario': dict(naval_reserve(ledger, tag, ledger.supply_chain_policy['naval_construction_utilization'])),
                       'domestic_input_gaps_with_scenario': {g:-n for g,n in sorted(planned.items()) if n < -1e-6}}
    return result
