"""Save-independent land completion from explicit source/review evidence only.

This planner has no vanilla-owner input. Every target land province is either
anchored, connected to an anchor by an auditable land path, or explicitly
unresolved. State borders and impassable terrain do not break land continuity;
sea/strait edges must be excluded by the map adapter.
"""
from collections import defaultdict, deque, Counter
from fractions import Fraction


TRUSTED = {'source_owned', 'source_native_population', 'reviewed'}


def source_seeds(province_states, mapping, locations, uninhabitable, populations, culture_map=None, location_weights=None):
    """Create seed facts for any save; never use existing V3 ownership as evidence."""
    inverse = defaultdict(set)
    for p, names in mapping.items():
        if p in province_states:
            for name in set(names):inverse[name].add(p)
    seeds, unresolved, native_cultures = {}, [], {}
    uninhabitable = set(uninhabitable)
    weights={n:{p:1 for p in ps} for n,ps in inverse.items()}
    for name,reviewed in (location_weights or {}).items():
        if set(reviewed)!=inverse[name] or any(v<=0 for v in reviewed.values()):
            raise ValueError('Invalid reviewed geographical weights: '+name)
        weights[name]=reviewed
    for p in sorted(province_states):
        names = set(mapping.get(p, [])) - uninhabitable
        if any(n not in locations for n in names):
            raise ValueError('Mapping references an unknown source location: ' + p)
        owned = Counter()
        for n in names:
            sid = str(locations[n]['owner'])
            if sid != '0':owned[sid] += max(Fraction(1), Fraction(str(locations[n]['population_persons'])))
        if owned:
            sid = min(owned,key=lambda k:(-owned[k],k))
            seeds[p] = {'owner':'source:'+sid,'kind':'source_owned','source_locations':sorted(names),
                        'competing_source_owners':sorted(owned)}
            continue
        cultures = defaultdict(Fraction)
        for n in names:
            for c,amount in populations.get(n,{}).items():
                if amount > 0:cultures[c] += Fraction(amount*weights[n][p],sum(weights[n].values()))
        if cultures:
            primary = min(cultures,key=lambda c:(-cultures[c],c))
            mapped = (culture_map or {}).get(primary,primary)
            owner = 'native:'+mapped
            native_cultures[owner] = mapped
            seeds[p] = {'owner':owner,'kind':'source_native_population','source_locations':sorted(names),
                        'source_culture':primary,'mapped_culture':mapped,
                        'culture_mapping_missing':culture_map is not None and primary not in culture_map}
        elif names:
            unresolved.append({'province':p,'reason':'unowned_habitable_without_population_evidence','source_locations':sorted(names)})
    return seeds, native_cultures, unresolved


def complete(province_states, edges, seeds, native_cultures=None):
    """Build an exact land partition plus explicit unresolved connected components."""
    land = set(province_states)
    if not seeds.keys() <= land:
        raise ValueError('Seed outside target land map')
    for p,r in seeds.items():
        if r.get('kind') not in TRUSTED or not r.get('owner'):
            raise ValueError('Untrusted/inferred owner cannot become a seed: '+p)
    adjacent = {p:set() for p in land}
    for a,b in edges:
        if a in land and b in land and a != b:
            adjacent[a].add(b);adjacent[b].add(a)
    distances = {p:0 for p in seeds}
    queue = deque(sorted(seeds))
    while queue:
        p = queue.popleft()
        for q in sorted(adjacent[p]):
            if q not in distances:
                distances[q] = distances[p]+1;queue.append(q)
    rows, contenders = {}, {}
    for p in sorted(distances,key=lambda q:(distances[q],q)):
        if p in seeds:
            rows[p] = {'province':p,'state':province_states[p],'owner':seeds[p]['owner'],
                       'kind':seeds[p]['kind'],'root':p,'parent':None,'distance':0}
            contenders[p] = {seeds[p]['owner']}
        else:
            parents = [q for q in adjacent[p] if distances.get(q) == distances[p]-1]
            parent = min(parents,key=lambda q:(rows[q]['root'],q))
            contenders[p] = set.union(*(contenders[q] for q in parents))
            rows[p] = {'province':p,'state':province_states[p],'owner':rows[parent]['owner'],
                       'kind':'land_inferred','root':rows[parent]['root'],'parent':parent,
                       'distance':distances[p],'equidistant_owners':sorted(contenders[p]) if len(contenders[p])>1 else []}
    # Identity is grouped AFTER terrain filling, so a wasteland bridge can
    # join native anchors across state borders. Sea gaps remain separate.
    native_cultures = native_cultures or {}
    unseen = {p for p,r in rows.items() if r['owner'] in native_cultures}
    native_components = []
    while unseen:
        first = min(unseen);culture = native_cultures[rows[first]['owner']]
        members, visit = [], [first];unseen.remove(first)
        while visit:
            p=visit.pop();members.append(p)
            for q in sorted(adjacent[p] & unseen):
                if native_cultures[rows[q]['owner']] == culture:
                    unseen.remove(q);visit.append(q)
        key='native:'+culture+':'+min(members)
        native_components.append({'owner':key,'culture':culture,'provinces':sorted(members),
                                  'states':sorted({province_states[p] for p in members})})
        for p in members:rows[p]['owner']=key
    unresolved,unseen = [], land-rows.keys()
    while unseen:
        first=min(unseen);members=[];visit=[first];unseen.remove(first)
        while visit:
            p=visit.pop();members.append(p)
            for q in sorted(adjacent[p] & unseen):unseen.remove(q);visit.append(q)
        unresolved.append({'component':first,'provinces':sorted(members),
                           'states':sorted({province_states[p] for p in members}),
                           'reason':'land_component_has_no_source_or_reviewed_anchor'})
    result={'schema':1,'provinces':rows,'unresolved_components':unresolved,'native_components':native_components,
            'summary':{'target_land_provinces':len(land),'anchored':len(seeds),'land_inferred':len(rows)-len(seeds),
                       'unresolved_provinces':sum(len(r['provinces']) for r in unresolved),
                       'unresolved_components':len(unresolved),'native_countries':len(native_components),
                       'native_countries_crossing_state_borders':sum(len(r['states'])>1 for r in native_components),
                       'equidistant_owner_conflicts':sum(bool(r.get('equidistant_owners')) for r in rows.values()),
                       'vanilla_fallbacks_used':0,'all_target_land_accounted':len(rows)+sum(len(r['provinces']) for r in unresolved)==len(land)},
            'export_ready':not unresolved}
    validate(result,province_states,edges,seeds)
    return result


def validate(result,province_states,edges,seeds):
    rows=result['provinces'];unresolved=[p for c in result['unresolved_components'] for p in c['provinces']]
    assert len(unresolved)==len(set(unresolved)) and not set(unresolved)&rows.keys()
    assert set(rows)|set(unresolved)==set(province_states)
    land_edges={frozenset((a,b)) for a,b in edges}
    for p,r in rows.items():
        if p in seeds:
            assert r['root']==p and r['parent'] is None and r['distance']==0
            if not seeds[p]['owner'].startswith('native:'):assert r['owner']==seeds[p]['owner']
        else:
            q=r['parent'];assert frozenset((p,q)) in land_edges
            assert rows[q]['distance']==r['distance']-1 and rows[q]['root']==r['root']
            assert rows[q]['owner']==r['owner']
            assert r['root'] in seeds and seeds[r['root']]['kind'] in TRUSTED
    return True


def require_export_ready(result):
    if not result['export_ready']:
        raise ValueError(f"Unresolved terrain blocks export: {result['summary']['unresolved_provinces']} provinces in {result['summary']['unresolved_components']} land components")
    return result
