"""Separate capacity, living-cost and fiscal screens; never call them runtime balance."""
from collections import Counter
from economy_model import definitions
from extract_m3_politics import fields, sequence
from pdx_text import Object,root


def british_fiscal_reference(path):
    doc = root(path.read_text(encoding='utf-8-sig')).fields()
    for obj in fields(fields(doc['country_manager'])['database']).values():
        if not isinstance(obj,Object): continue
        country = fields(obj)
        if country.get('definition') != 'GBR': continue
        budget = fields(country['budget'])
        return {'weekly_base_wage_per_10000':float(budget['base_wage']),
                'weekly_income':sum(float(v) for v in sequence(budget['weekly_income'])),
                'weekly_expenses':sum(float(v) for v in sequence(budget['weekly_expenses']))}
    raise ValueError('No British fiscal reference')


def screen(ledger,baseline,reference,army_report,market,infra,wealth):
    from complete_economy import living_requirements
    pops = definitions(ledger.target.game/'common/pop_types')
    public = {'building_government_administration','building_university','building_construction_sector','building_barrack','building_naval_administration'}
    result = {}
    for tag in sorted(army_report['countries']):
        costs,wages,low_margin = Counter(),Counter(),[]
        rail_ceiling = 0
        for key in sorted(ledger.by_country[tag]):
            if key not in ledger.rows: continue
            r = ledger.rows[key]; k,n = r['building'],r['levels']
            values = ledger.target.numeric(r['pms'])
            weighted = sum(v*float(pops.get(a[20:-4],{}).get('wage_weight',1)) for a,v in values.items() if a.startswith('building_employment_'))
            if k=='building_barrack':
                ratio = fields(ledger.target.pms[r['pms'][0]].get('profession_ratio'))
                weighted = 1000*sum(float(pops[p].get('wage_weight',1))*float(v)/100 for p,v in ratio.items())
            pay = weighted*reference['weekly_base_wage_per_10000']/10000
            c = ledger.coefficients(r)
            inputs = sum(ledger.target.prices[g]*v for g,v in c['inputs'].items())
            if k in public:
                costs[k] += (pay+inputs)*n; wages[k] += pay*n
            elif k=='building_railway':
                rail_ceiling += (pay+inputs)*n
            elif c['gross']>0 and c['gross']-inputs-pay < 0:
                low_margin.append({'state':r['state'],'building':k,'levels':n,
                                   'margin_per_level_at_reference_wage':round(c['gross']-inputs-pay,2)})
        costs['army_goods'] = sum(ledger.target.prices[g]*v for g,v in ledger.military_demand[tag].items())
        pop = sum(p for (s,t),p in ledger.population.items() if t==tag)
        reference_revenue = pop/baseline['population']*reference['weekly_income']
        requirements = living_requirements(ledger,tag,wealth)
        balance = ledger.balance(tag)
        food = sum(max(0,balance[g])*ledger.target.prices[g] for g in ('grain','fish','meat','fruit','groceries'))
        available = {'basic_food':food,'clothing':max(0,balance['clothes'])*ledger.target.prices['clothes'],
                     'furniture':max(0,balance['furniture'])*ledger.target.prices['furniture'],
                     'heating':max(0,balance['coal'])*ledger.target.prices['coal']}
        shortages = {k:round(max(0,requirements[k]-v),2) for k,v in available.items()}
        household = None
        if hasattr(ledger,'development'):
            from economy_consumption import screen as household_screen
            household = household_screen(ledger,tag,wealth)
            h = household['shortfalls']
            shortages.update(clothing=round(h['standard_clothing']+h['simple_clothing'],2),
                             furniture=round(h['furniture'],2),heating=round(h['heating'],2),
                             household_items=round(h['household_items'],2))
            available.update({k:round(requirements[k]-shortages[k],2) for k in ('clothing','furniture','heating','household_items')})
        costs = {k:round(v,2) for k,v in costs.items()}
        cash_cost = sum(costs.values())
        result[tag] = {'status':'static_screen_only_runtime_required',
                       'household_substitution':household,
                       'living_standard_target_wealth':wealth,'basic_need_base_value_requirements':requirements,
                       'basic_need_base_value_available':available,'basic_need_base_value_shortfalls':shortages,
                       'weekly_public_cost_at_reference_wage_and_base_prices':costs,
                       'weekly_public_cost_total':round(cash_cost,2),
                       'railway_full_cost_subsidy_ceiling':round(rail_ceiling,2),
                       'reference_revenue_at_british_per_person_rate':round(reference_revenue,2),
                       'revenue_is_forecast':False,
                       'required_weekly_revenue_before_ship_upkeep_debt_diplomacy':round(cash_cost+rail_ceiling,2),
                       'reference_budget_gap_including_full_rail_cost':round(reference_revenue-cash_cost-rail_ceiling,2),
                       'public_wage_plus25pct_cost_total':round(cash_cost+sum(wages.values())*.25,2),
                       'low_margin_production_rows':low_margin,
                       'unresolved_market_components':[g for g in market if g['country']==tag and not g['has_local_port_connection']],
                       'owned_coastal_port_available':any(g['port_state'] for g in market if g['country']==tag),
                       'world_trade_access':'owned_coast_candidate_runtime_shipping_check' if any(g['port_state'] for g in market if g['country']==tag) else 'requires_existing_or_negotiated_transit_no_treaty_added',
                       'infrastructure_gaps':[r for r in infra if r['country']==tag],
                       'military_policy':'Preserve source establishments even when the fiscal screen is negative, per user instruction.',
                       'limitations':['Needs use base-expenditure equivalence and fixed workforce/dependent ratios; substitute-goods demand and market prices are not simulated.',
                                      'Naval department wages are included; ship upkeep, institutions, diplomacy, debt, tax waste and dividends remain excluded; rail cost is a conservative full-subsidy ceiling.',
                                      'Revenue is a British per-capita comparison only. Tax laws, incorporation, institutions and actual hiring require a new-game budget audit.']}
    return result
