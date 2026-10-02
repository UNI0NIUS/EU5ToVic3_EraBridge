"""Allocate naval departments and one fleet per owned coastal HQ (V3 1.13)."""
from collections import Counter, defaultdict
import json
import math

from economy_capacity import capped_allocation
from economy_market import coastal
from economy_model import block, definitions
from extract_m3_politics import fields, sequence
from pdx_text import Object, root


BUILDING = 'building_naval_administration'


def naval_defines(game):
    result = {}
    # Define files extend the same namespace; unlike entity definitions this is valid.
    for path in sorted((game/'common/defines').glob('*.txt')):
        for key,obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if key == 'NMilitary': result.update(fields(obj))
    return result


def read_ships(text, managed):
    """Resolve both inline ships and named create_ship references before regrouping."""
    history = fields(root(text))['MILITARY_FORMATIONS']
    retained, ships, scopes, pending = defaultdict(list), defaultdict(list), {}, []
    for key, country in history.entries():
        tag = key.removeprefix('c:')
        for op, obj in country.entries():
            f = fields(obj)
            if tag in managed and op == 'create_military_formation' and f.get('type') == 'fleet':
                hq = f['hq_region'].removeprefix('sr:')
                scope = f.get('save_scope_as', f.get('save_temporary_scope_as'))
                if scope:
                    if scope in scopes: raise ValueError('Duplicate fleet scope: '+scope)
                    scopes[scope] = tag, hq
                for operation, ship in obj.entries():
                    if operation == 'ship':
                        sf = fields(ship)
                        if set(sf)-{'type', 'count', 'name', 'state_region', 'flagship'}:
                            raise ValueError('Unsupported ship history fields: '+str(set(sf)))
                        count = int(sf.get('count', 1))
                        if count <= 0: raise ValueError('Nonpositive ship history count')
                        for _ in range(count):
                            ships[tag].append({'type':sf['type'].removeprefix('ship_type:'), 'home_hq':hq,
                                               **({'flagship':sf['flagship']} if 'flagship' in sf else {}),
                                               **({'name':sf['name']} if 'name' in sf else {})})
            elif tag in managed and op == 'create_ship':
                pending.append((tag, f))
            else:
                retained[tag].append(block(op,obj.text()) if isinstance(obj,Object) else f'{op} = {obj}\n')
    for tag, f in pending:
        if set(f)-{'type', 'fleet', 'name'}:
            raise ValueError('Unsupported named ship history fields: '+str(set(f)))
        owner, hq = scopes[f['fleet'].removeprefix('scope:')]
        if owner != tag: raise ValueError('Foreign fleet scope')
        ships[tag].append({'type':f['type'].removeprefix('ship_type:'), 'home_hq':hq,
                           **({'name':f['name']} if 'name' in f else {})})
    return retained, ships


def crew_required(kind, shipdefs, modifications):
    definition = shipdefs[kind]
    modifier = Counter({k:float(v) for k,v in fields(definition['modifier']).items()
                        if k in ('ship_crew_max_add', 'ship_crew_max_mult')})
    for mod in fields(definition.get('default_modifications')).values():
        for key, value in fields(modifications[mod].get('modifier')).items():
            if key in ('ship_crew_max_add', 'ship_crew_max_mult'): modifier[key] += float(value)
    crew = math.ceil(modifier['ship_crew_max_add']*(1+modifier['ship_crew_max_mult']))
    if crew <= 0: raise ValueError('Nonpositive ship crew: '+kind)
    return crew


def convert(ledger, text, managed, classes, policy, source_ships=None):
    if not hasattr(ledger, 'coastal_provinces'):
        raise ValueError('Fleet allocation requires actual owned coastal provinces')
    target = ledger.target
    regions = {s:k for k,f in definitions(target.game/'common/strategic_regions').items()
               for s in sequence(f.get('states'))}
    shipdefs = definitions(target.game/'common/ship_types')
    modifications = definitions(target.game/'common/ship_modifications')
    defines = naval_defines(target.game)
    per_level = int(defines['SAILORS_PER_BUILDING_LEVEL'])
    slot = int(defines['SAILORS_PER_ASSIGNMENT_SLOT'])
    forms, ships = read_ships(text, managed)
    if source_ships is not None:
        ships = defaultdict(list,{t:[dict(s) for s in ss] for t,ss in source_ships.items()})
    for key in list(ledger.rows):
        if key[1] in managed and key[2] == BUILDING: del ledger.rows[key]
    countries, formations = {}, []
    for tag in sorted(managed):
        incoming = ships[tag]
        for ship in incoming:
            ship['crew'] = crew_required(ship['type'], shipdefs, modifications)
            ship['assignment_sailors'] = math.ceil(ship['crew']/slot)*slot
        states = sorted(s for s,t in ledger.population if t == tag and coastal(ledger,s,t))
        home = Counter()
        for ship in incoming: home[ship['home_hq']] += ship['assignment_sailors']
        soldiers = {s:classes[s,tag,'soldiers'] for s in states}
        hq_population = Counter()
        for s in states: hq_population[regions[s]] += ledger.population[s,tag]
        origin = {s:home[regions[s]]*ledger.population[s,tag]/hq_population[regions[s]] if hq_population[regions[s]] else 0 for s in states}
        if source_ships is not None:
            origin = {s:sum(ship['assignment_sailors']*ship.get('home_weights',{}).get(s,0) for ship in incoming) for s in states}
        def normalized(values):
            total = sum(values.values())
            return {s:v/total for s,v in values.items()} if total else {}
        a,b = normalized(soldiers),normalized(origin)
        weight = policy['military_population_weight']
        weights = {s:weight*a.get(s,0)+(1-weight)*b.get(s,0) for s in states}
        if not sum(weights.values()): weights = {s:ledger.population[s,tag] for s in states}
        unlocked = ledger.allowed(BUILDING,tag)
        pms = ledger.pms(BUILDING,tag) if unlocked else []
        jobs = target.coefficients(BUILDING,pms,ledger.techs[tag])['jobs'] if unlocked else 0
        sailors = sum(float(fields(fields(target.pms[pm].get('country_modifiers')).get('workforce_scaled')).get('country_sailors_max_add',0)) for pm in pms)
        if unlocked and (jobs <= 0 or sailors != per_level):
            raise ValueError('Unsupported naval department employment/capacity')
        # The army and navy share the population envelope; barracks have priority.
        caps = {s:max(0,math.floor((ledger.population[s,tag]*policy['state_military_population_ceiling']-
                     ledger.rows.get((s,tag,'building_barrack'),{}).get('levels',0)*1000)/jobs)) if unlocked else 0 for s in states}
        hq_caps, hq_weights = Counter(), Counter()
        for s in states:
            hq_caps[regions[s]] += caps[s]*per_level
            hq_weights[regions[s]] += weights[s]
        total = sum(s['assignment_sailors'] for s in incoming)
        targets = {h:total*w/sum(hq_weights.values()) for h,w in hq_weights.items()} if sum(hq_weights.values()) else {}
        assigned, used, unallocated = defaultdict(list), Counter(), []
        for ship in sorted(incoming,key=lambda s:(-s['assignment_sailors'],s['type'],s.get('name',''),s['home_hq'])):
            if not set(sequence(shipdefs[ship['type']].get('unlocking_technologies'))) <= ledger.techs[tag]:
                unallocated.append({**ship,'reason':'ship_technology_locked'}); continue
            eligible = [h for h in hq_caps if hq_caps[h]-used[h] >= ship['assignment_sailors']]
            if not eligible:
                reason = 'no_owned_coast' if not states else 'naval_department_technology_locked' if not unlocked else 'military_population_capacity'
                unallocated.append({**ship,'reason':reason}); continue
            hq = max(eligible,key=lambda h:(targets.get(h,0)-used[h],h==ship['home_hq'],h))
            assigned[hq].append(ship); used[hq] += ship['assignment_sailors']
        allocation = {}
        for hq, members in sorted(assigned.items()):
            local = [s for s in states if regions[s] == hq]
            levels = math.ceil(used[hq]/per_level)
            allocated, missing = capped_allocation({s:weights[s] for s in local},levels,{s:caps[s] for s in local})
            if missing: raise ValueError('Fleet without naval department capacity')
            allocation.update(allocated)
            for state, n in allocated.items():
                if n: ledger.put(state,tag,BUILDING,n,'fleet_crew_and_local_military_population',pms)
            body = f'type = fleet\nhq_region = sr:{hq}\n'
            scope = f'eu5_allocated_{tag}_{hq}'
            named = []
            flagship_assigned = False
            for ship in members:
                if 'name' in ship:
                    named.append(block('create_ship',f'type = ship_type:{ship["type"]}\nfleet = scope:{scope}\nname = {json.dumps(ship["name"],ensure_ascii=False)}\n'))
                else:
                    flagship = ship.get('flagship') == 'yes' and not flagship_assigned
                    body += block('ship',f'type = ship_type:{ship["type"]}\ncount = 1\n'+('flagship = yes\n' if flagship else ''))
                    flagship_assigned |= flagship
            if named: body += f'save_scope_as = {scope}\n'
            forms[tag].append(block('create_military_formation',body))
            forms[tag].extend(named)
            formations.append({'country':tag,'hq':hq,'ships':len(members),'crew':sum(s['crew'] for s in members),
                               'source_ids':[s['source_id'] for s in members if 'source_id' in s],
                               'assignment_sailors':used[hq],'department_levels':levels,'capacity':levels*per_level})
        countries[tag] = {'input_ships':len(incoming),'exported_ships':sum(len(v) for v in assigned.values()),
                          'input_types':dict(Counter(s['type'] for s in incoming)),
                          'exported_types':dict(Counter(s['type'] for v in assigned.values() for s in v)),
                          'input_names':dict(Counter(s['name'] for s in incoming if 'name' in s)),
                          'exported_names':dict(Counter(s['name'] for v in assigned.values() for s in v if 'name' in s)),
                          'unallocated_ships':unallocated,'state_allocation':allocation,'state_caps':caps,
                          'formation_count':len(assigned),'department_levels':sum(allocation.values())}
    result = block('MILITARY_FORMATIONS',''.join(block('c:'+t,''.join(fs)).replace(' = {',' ?= {',1) for t,fs in sorted(forms.items())))
    return result, {'countries':countries,'formations':formations,'policy':policy,'sailors_per_level':per_level,
                    'basis':'Source EU5 warship hull counts; transports excluded; vanilla V3 hull types.' if source_ships is not None else 'Existing converted ships; source EU5 ship-count/type conversion remains pending.',
                    'rounding':'Crew rounded to assignment slots per ship; department levels rounded up per HQ.'}


def verify(ledger, text, report):
    """Independently read emitted ships, locations and department capacity."""
    errors, actual = [], {}
    _, ships = read_ships(text,report['countries'])
    for tag, country in report['countries'].items():
        exported = Counter(s['type'] for s in ships[tag])
        if exported != Counter(country['exported_types']): errors.append('fleet ship readback '+tag)
        if exported+Counter(s['type'] for s in country['unallocated_ships']) != Counter(country['input_types']):
            errors.append('fleet ship conservation '+tag)
        names = Counter(s['name'] for s in ships[tag] if 'name' in s)
        if names != Counter(country['exported_names']): errors.append('fleet name readback '+tag)
        if names+Counter(s['name'] for s in country['unallocated_ships'] if 'name' in s) != Counter(country['input_names']):
            errors.append('fleet name conservation '+tag)
    regions = {s:k for k,f in definitions(ledger.target.game/'common/strategic_regions').items() for s in sequence(f.get('states'))}
    for (s,t,k), row in ledger.rows.items():
        if t not in report['countries'] or k != BUILDING: continue
        if not coastal(ledger,s,t): errors.append('inland naval department '+s+' '+t)
        if row['levels'] != report['countries'][t]['state_allocation'].get(s,0): errors.append('naval department level '+s+' '+t)
        if row['levels'] > report['countries'][t]['state_caps'].get(s,0): errors.append('naval population capacity '+s+' '+t)
        actual[t,regions[s]] = actual.get((t,regions[s]),0)+row['levels']
    shipdefs = definitions(ledger.target.game/'common/ship_types')
    mods = definitions(ledger.target.game/'common/ship_modifications')
    slot = int(naval_defines(ledger.target.game)['SAILORS_PER_ASSIGNMENT_SLOT'])
    seen = set()
    history = fields(root(text))['MILITARY_FORMATIONS']
    for key,country in history.entries():
        tag = key.removeprefix('c:')
        if tag not in report['countries']: continue
        for op,form in country.entries():
            f = fields(form)
            if op != 'create_military_formation' or f.get('type') != 'fleet': continue
            hq = f['hq_region'].removeprefix('sr:'); pair = tag,hq
            if pair in seen: errors.append('duplicate HQ fleet '+tag+' '+hq)
            seen.add(pair)
            members = [s for s in ships[tag] if s['home_hq']==hq]
            required = sum(math.ceil(crew_required(s['type'],shipdefs,mods)/slot)*slot for s in members)
            if not required or actual.get(pair,0) != math.ceil(required/report['sailors_per_level']):
                errors.append('fleet/department capacity '+tag+' '+hq)
    if set(actual) != seen: errors.append('naval department without fleet')
    if errors: raise ValueError('Fleet verification failed: '+str(errors))
    return len(seen)
