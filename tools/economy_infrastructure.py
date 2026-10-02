"""Resource/workforce constrained support for converted railway economies."""
import math
from collections import Counter, defaultdict
from economy_model import apportioned, block
from extract_m3_politics import fields, sequence


def support(target, retained, generated, population, techs, laws, owners, british_pms, calibration):
    by_state = defaultdict(list)
    for row in retained+generated: by_state[row['state'], row['owner']].append(row)
    additions, warnings = [], []

    def add(state, tag, kind, wanted, reason):
        if wanted <= 0 or not set(sequence(target.buildings[kind].get('unlocking_technologies'))) <= techs[tag]: return 0
        rs = by_state[state, tag]
        old = next((r for r in rs if r['building'] == kind), None)
        pms = old['pms'] if old else target.select(kind, techs[tag], british_pms[kind], laws[tag])
        c = target.coefficients(kind, pms, techs[tag])
        occupied = sum(target.coefficients(r['building'], r['pms'], techs[tag])['jobs']*r['levels'] for r in rs)
        room = max(0, population[state, tag]*calibration['workforce_share_ceiling']-occupied)
        n = min(wanted, math.floor(room/c['jobs'])) if c['jobs'] else 0
        cap = fields(target.states[state].get('capped_resources')).get(kind)
        if cap is not None:
            share = apportioned(Counter(owners[state].values()), int(cap))[tag]
            n = min(n, max(0, share-(old['levels'] if old else 0)))
        if n <= 0: return 0
        if old:
            old['levels'] += n
            if 'body' in old:
                old['body'] += block('add_ownership', block('building', f'type = "{kind}"\ncountry = "c:{tag}"\nregion = "{state}"\nlevels = {n}'))
        else:
            old = {'state': state, 'owner': tag, 'building': kind, 'levels': n, 'pms': pms}
            generated.append(old); rs.append(old)
        additions.append({'state': state, 'country': tag, 'building': kind, 'levels': n, 'reason': reason})
        return n

    def provision_railways():
        for (state, tag), rs in sorted(by_state.items()):
            usage = sum(target.infrastructure_usage(r['building'])*r['levels'] for r in rs)
            available = target.infrastructure(state, population[state, tag], techs[tag], rs)
            if usage <= available: continue
            if 'railways' not in techs[tag]: continue
            pms = target.select('building_railway', techs[tag], british_pms['building_railway'], laws[tag])
            dummy = {'building': 'building_railway', 'levels': 1, 'pms': pms}
            gain = target.infrastructure(state, population[state, tag], techs[tag], rs+[dummy])-available-target.infrastructure_usage('building_railway')
            if gain > 0: add(state, tag, 'building_railway', math.ceil((usage-available)/gain), 'target_infrastructure_requirement_not_source_track_count')

    def goods_balance(tag):
        balance = Counter()
        for (state, owner), rs in by_state.items():
            if owner != tag: continue
            for r in rs:
                c = target.coefficients(r['building'], r['pms'], techs[tag])
                for g, v in c['outputs'].items(): balance[g] += v*r['levels']
                for g, v in c['inputs'].items(): balance[g] -= v*r['levels']
        return balance

    # Railway additions imply engine/steel/coal demand. Two deterministic passes
    # account for the infrastructure used by these supporting factories.
    for iteration in range(2):
        provision_railways()
        rail_countries = sorted({tag for (state, tag), rs in by_state.items() if 'railways' in techs[tag] and any(r['building']=='building_railway' for r in rs)})
        for tag in rail_countries:
            for good, kind in (('engines','building_motor_industry'), ('steel','building_steel_mill'), ('coal','building_coal_mine')):
                need = max(0, -goods_balance(tag)[good])
                if not need: continue
                candidates = [(s, sum(r['levels'] for r in rs if r['building'] in ('building_tooling_workshop','building_steel_mill','building_motor_industry','building_coal_mine')))
                              for (s,t),rs in by_state.items() if t==tag and (kind!='building_coal_mine' or int(fields(target.states[s].get('capped_resources')).get(kind,0))>0)]
                for state, _ in sorted(candidates, key=lambda x: (-x[1], x[0])):
                    pm = target.select(kind, techs[tag], british_pms[kind], laws[tag])
                    output = target.coefficients(kind, pm, techs[tag])['outputs'].get(good, 0)
                    if not output: break
                    n = add(state, tag, kind, math.ceil(need/output), 'rail_economy_input_support_'+good)
                    need -= n*output
                    if need <= 0: break
    for (state, tag), rs in sorted(by_state.items()):
        usage = sum(target.infrastructure_usage(r['building'])*r['levels'] for r in rs)
        available = target.infrastructure(state, population[state, tag], techs[tag], rs)
        if usage > available+0.00001:
            warnings.append({'state': state, 'country': tag, 'estimated_usage': usage, 'estimated_available': available,
                             'railway_researched': 'railways' in techs[tag]})
    return {'additions': additions, 'unresolved_infrastructure': warnings,
            'assumption': 'Full staffing, current template society technology, static state traits and PMs; excludes laws, decrees and market access. Rail levels meet target demand, not a count of EU5 track links.'}
