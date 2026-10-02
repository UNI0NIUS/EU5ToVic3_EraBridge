"""One-to-one source warship counts using existing vanilla V3 hull types."""
from collections import Counter, defaultdict

from economy_fleets import BUILDING
from economy_model import closure, definitions
from extract_m3_politics import sequence


TYPES = {'navy_heavy_ship':'ship_type_ship_of_the_line',
         'navy_light_ship':'ship_type_frigate','navy_galley':'ship_type_frigate'}


def prepare(ledger, source, naval, political, links):
    if source['source_sha256'] != naval['source_sha256'] or naval['source_sha256'] != political['source_sha256']:
        raise ValueError('Naval/economic/political source mismatch')
    lookup = {str(c['source_id']):t for t,c in political['countries'].items() if c['source_id'] is not None}
    regions = {s:k for k,f in definitions(ledger.target.game/'common/strategic_regions').items() for s in sequence(f.get('states'))}
    shipdefs = definitions(ledger.target.game/'common/ship_types')
    ships = defaultdict(list)
    countries = {t:{'source_warships':0,'source_transports':0,'source_categories':Counter(),'transports':[],'excluded':[]} for t in lookup.values()}
    unmatched, seen = [], set()
    for row in naval['ships']+naval['excluded']:
        if row['id'] in seen: raise ValueError('Duplicate source hull: '+row['id'])
        seen.add(row['id'])
        if row.get('hulls') != 1: raise ValueError('Source hull count must be one per ID')
        tag = lookup.get(row['owner'])
        if not tag: unmatched.append(row); continue
        report = countries[tag]
        report['source_categories'][row['category']] += 1
        if 'reason' in row: report['excluded'].append(row); continue
        if row['category']=='navy_transport':
            report['source_transports'] += 1
            report['transports'].append(row)
            continue
        if row['category'] not in TYPES: raise ValueError('Unmapped naval category: '+row['category'])
        kind = TYPES[row['category']]
        if kind not in shipdefs: raise ValueError('Missing vanilla ship type: '+kind)
        home = {}
        for location_id in (row['home'],row['last_port']):
            location = source['locations'].get(location_id,{}).get('name')
            home = {s:w for (s,t),w in links.get(location,{}).items() if t==tag and (s,t) in ledger.population}
            if home: break
        weight = sum(home.values())
        if weight: home = {s:w/weight for s,w in home.items()}
        home_hq = regions[max(home,key=lambda s:(home[s],s))] if home else ''
        ships[tag].append({'type':kind,'home_hq':home_hq,'home_weights':home,
                           'source_id':row['id'],'source_type':row['type'],'source_category':row['category']})
        report['source_warships'] += 1
    technology = {}
    for tag,members in ships.items():
        needed = set(sequence(ledger.target.buildings[BUILDING].get('unlocking_technologies')))
        for ship in members: needed.update(sequence(shipdefs[ship['type']].get('unlocking_technologies')))
        before = set(ledger.techs[tag])
        ledger.techs[tag] = closure(before|needed,ledger.target.techs)
        technology[tag] = sorted(ledger.techs[tag]-before)
    report = {'source_sha256':naval['source_sha256'],'countries':countries,'unmapped_owner_ships':unmatched,
              'source_records':len(seen),'vanilla_types':TYPES,'transports':'reported_separately_not_warships',
              'technology_added':technology,
              'technology_basis':'Extant source warships justify only baseline vanilla hull/recruitment technologies and prerequisites; no advanced hulls.',
              'count_basis':'One source warship hull becomes one requested vanilla warship. Actual exported plus unallocated equals source warships.'}
    if sum(c['source_warships']+c['source_transports']+len(c['excluded']) for c in countries.values())+len(unmatched) != len(seen):
        raise ValueError('Source hull accounting mismatch')
    return ships,report
