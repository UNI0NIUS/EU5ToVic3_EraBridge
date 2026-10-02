"""Account for ALL source production buildings, including paid agricultural work."""
from collections import Counter, defaultdict
import math
from economy_model import definitions, apportioned
from extract_m3_politics import fields, sequence
from pdx_text import Object, root
from economy_geography import preserve_geography, local_limit

AGRICULTURAL = {'wheat','legumes','potato','rice','maize','millet','fruit','olives','livestock','wool','horses',
                'fiber_crops','cotton','silk','dyes','sugar','tobacco','tea','coffee','cocoa','saffron','cloves',
                'chili','incense','medicaments','beeswax','wine','wild_game','fur'}
RESOURCES = {'lumber':'building_logging_camp','iron':'building_iron_mine','coal':'building_coal_mine',
             'lead':'building_lead_mine','fish':'building_fishing_wharf'}
EXTRACTION_GOODS = set(RESOURCES) | {'stone','clay','marble','salt','copper','tin','silver','goods_gold','alum','mercury','gems','sand','saltpeter'}


def profile(source,eu5,links):
    definitions_by_type = definitions(eu5/'in_game/common/building_types')
    global_methods = definitions(eu5/'in_game/common/production_methods')
    commercial_agriculture, extraction, employment = Counter(),Counter(),defaultdict(Counter)
    building_catalogue, unmapped, processing = {},Counter(),Counter()
    methods_by_type = defaultdict(dict)
    # EU5 permits repeated unique_production_methods blocks (e.g. guns plus
    # ammunition). A dict of building fields retains only the last block.
    for path in sorted((eu5/'in_game/common/building_types').glob('*.txt')):
        for kind,obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if not isinstance(obj,Object): continue
            for key,value in obj.entries():
                if key=='unique_production_methods':
                    methods_by_type[kind].update({pm:fields(o) for pm,o in fields(value).items() if isinstance(o,Object)})
                elif key=='possible_production_methods':
                    methods_by_type[kind].update({pm:global_methods[pm] for pm in sequence(value) if pm in global_methods})
    for kind,f in definitions_by_type.items():
        methods = methods_by_type[kind]
        produced = {v['produced'] for v in methods.values() if v.get('produced')}
        building_catalogue[kind] = {'pop_type':f.get('pop_type'),'category':f.get('category'),
                                    'produced_goods':sorted(produced)}
    for b in source['buildings']:
        loc = source['locations'][b['location']]
        f = building_catalogue[b['type']]
        people = float(b.get('employed',0))*1000  # Already TOTAL across levels.
        # An active boatyard in a fishing village is not fish production. Missing
        # PM data in older fixtures falls back only to unambiguous unique output.
        methods = methods_by_type[b['type']]
        active = b.get('pms')
        if active is not None:
            unknown = set(active)-methods.keys()
            if unknown:
                raise ValueError('Unknown active source PM: '+b['type']+' '+str(sorted(unknown)))
            goods = sorted({methods[pm]['produced'] for pm in active if methods[pm].get('produced')})
        else:
            goods = f['produced_goods'] if len(f['produced_goods'])==1 else []
        section = 'paid_agriculture' if goods and set(goods)<=AGRICULTURAL else 'extraction' if goods and set(goods)<=EXTRACTION_GOODS else 'manufacturing' if goods else 'other_building_employment'
        for (state,tag),fraction in links.get(loc['name'],{}).items():
            employment[tag][section] += people*fraction
            if section=='paid_agriculture' and f['pop_type'] not in ('peasants','tribesmen','slaves'):
                commercial_agriculture[state,tag] += people*fraction
            for g in goods:
                if g in RESOURCES:
                    amount = people*fraction/len(goods)
                    wood_fuel = g=='coal' and any(m.get('produced')=='coal' and 'lumber' in m for m in methods.values())
                    if wood_fuel or (g=='iron' and b['type']=='bog_iron_smelter'):
                        processing[tag,b['type']] += amount
                    else:
                        extraction[state,tag,RESOURCES[g]] += amount
            if not goods and people: unmapped[b['type']] += people*fraction
    for loc in source['locations'].values():
        for (state,tag),fraction in links.get(loc['name'],{}).items():
            employment[tag]['rgo'] += loc['rgo_workers']*fraction
            if loc['raw_material'] in AGRICULTURAL:
                stats = loc.get('class_employment')
                if stats is None: raise ValueError('Source ledger lacks class-level RGO employment')
                paid = sum(f.get('employed_in_rgo',0) for c,f in stats.items() if c not in ('peasants','tribesmen','slaves'))
                commercial_agriculture[state,tag] += paid*fraction
            if loc['raw_material'] in RESOURCES:
                extraction[state,tag,RESOURCES[loc['raw_material']]] += loc['rgo_workers']*fraction
    return commercial_agriculture,extraction,{'all_building_types':building_catalogue,
             'countries':{t:dict(c) for t,c in employment.items()},'other_employment_by_building':dict(unmapped),
             'non_mine_resource_processing':[{'country':t,'building':k,'person_equivalents':n} for (t,k),n in sorted(processing.items())],
             'resource_evidence_rule':'Use active PMs; wood-derived charcoal and bog-iron processing do not seed mines. Multiple output goods share employment equally because PM-specific employment is unavailable.',
             'note':'Source employment is an EU5 population-equivalent measure. A configurable V3 workforce share converts it to job capacity; laborers include paid farm and resource work.'}


def seed_resources(ledger,source_weights,managed_tags):
    """Source employment guides buildings within geographic caps, not deposits."""
    requested,changes = {},{}
    for (s,t,k),people in source_weights.items():
        if t not in managed_tags or not ledger.allowed(k,t): continue
        jobs = ledger.target.coefficients(k,ledger.pms(k,t),ledger.techs[t])['jobs']
        n = math.floor(people*ledger.config['workforce_share']/jobs+.5) if jobs else 0
        if n: requested[s,t,k] = n
    keys = {(s,k) for s,t,k in requested}
    for s,k in sorted(keys) if not preserve_geography(ledger) else []:
        caps = fields(ledger.target.states[s].get('capped_resources'))
        original = int(caps.get(k,0)); shares = Counter(ledger.owners[s].values())
        n = max([original]+[math.ceil(v*sum(shares.values())/shares[t]) for (state,t,kind),v in requested.items() if state==s and kind==k])
        while any(apportioned(shares,n).get(t,0)<v for (state,t,kind),v in requested.items() if state==s and kind==k): n += 1
        if n>original:
            changes.setdefault(s,{})[k] = {'before':original,'after':n,'source_employment_person_equivalents':sum(v for (state,t,kind),v in source_weights.items() if state==s and kind==k)}
            caps[k] = str(n)
            ledger.target.states[s]['capped_resources'] = root(' '.join(f'{kind} = {value}' for kind,value in caps.items()))
    from economy_market import coastal
    ledger.source_resource_requests = []
    for (s,t,k),n in sorted(requested.items()):
        has_coast = k!='building_fishing_wharf' or coastal(ledger,s,t)
        desired = n
        old = ledger.rows.get((s,t,k),{}).get('levels',0)
        n = min(max(0,n-old),ledger.capped_room(s,t,k)) if has_coast else 0
        if n: ledger.add(s,t,k,n,'all_source_rgo_and_resource_building_employment')
        actual = ledger.rows.get((s,t,k),{}).get('levels',0)
        cap = local_limit(ledger,s,t,k)
        ledger.source_resource_requests.append({'state':s,'country':t,'building':k,
            'source_employment_person_equivalents':source_weights[s,t,k], 'requested_levels':desired,
            'geographic_share':cap,'built_after_seeding':actual,
            'unrepresented_levels':max(0,desired-actual),'geographic_shortfall':max(0,desired-(cap or 0)),
            'coastal_requirement_satisfied':has_coast})
    return changes
