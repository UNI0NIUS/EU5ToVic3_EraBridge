"""Territorial market connectivity and productive ports for V3 1.13."""
from collections import Counter, defaultdict
import csv
import json
import math
from economy_model import apportioned,definitions
from extract_m3_politics import fields, sequence
from m3_world import digest
from pdx_text import root


def land_edges(game, cache, owners):
    """Read actual province raster borders; cache is invalidated by both map inputs."""
    import numpy as np
    from PIL import Image
    image = game/'map_data/provinces.png'
    adjacency = game/'map_data/adjacencies.csv'
    default_map = game/'map_data/default.map'
    signature = [digest(image),digest(adjacency),digest(default_map)]
    blocked = {p for f in definitions(game/'map_data/state_regions').values() for p in sequence(f.get('impassable'))}
    if cache.exists():
        saved = json.loads(cache.read_text(encoding='utf-8'))
        if saved['sha256'] == signature:
            normalized = [('x'+a[1:].upper(),'x'+b[1:].upper()) for a,b in saved['edges']]
            return [(a,b) for a,b in normalized if a not in blocked and b not in blocked],set(saved['coastal_provinces'])-blocked
    rgb = np.asarray(Image.open(image).convert('RGB'),dtype=np.uint32)
    colors = (rgb[:,:,0]<<16)|(rgb[:,:,1]<<8)|rgb[:,:,2]
    del rgb
    pairs = set()
    for start in range(0,colors.shape[0],256):
        data = colors[start:min(colors.shape[0],start+257)]
        for a,b in ((data[:,:-1],data[:,1:]),(data[:-1,:],data[1:,:])):
            mask = a != b
            x,y = a[mask].astype(np.uint64),b[mask].astype(np.uint64)
            values = (np.minimum(x,y)<<24)|np.maximum(x,y)
            pairs.update(int(v) for v in np.unique(values))
    # Horizontal map wrap is enabled by the installed default.map.
    x,y = colors[:,0].astype(np.uint64),colors[:,-1].astype(np.uint64)
    pairs.update(int(v) for v in np.unique((np.minimum(x,y)<<24)|np.maximum(x,y)) if (v>>24)!=(v&0xFFFFFF))
    land = {p.upper() for ps in owners.values() for p in ps}
    seas = {p.upper() for p in sequence(root(default_map.read_text(encoding='utf-8-sig')).fields()['sea_starts'])}
    coasts = set()
    edges = set()
    for value in pairs:
        a,b = f'x{value>>24:06X}',f'x{value&0xFFFFFF:06X}'
        if a.upper() in land and b.upper() in land:
            edges.add(tuple(sorted((a,b))))
        if a.upper() in land and b.upper() in seas: coasts.add(a)
        if b.upper() in land and a.upper() in seas: coasts.add(b)
    with adjacency.open(encoding='utf-8-sig',newline='') as stream:
        for r in csv.DictReader(stream,delimiter=';'):
            if r['From'] == '-1': continue
            a,b = 'x'+r['From'][1:].upper(),'x'+r['To'][1:].upper()
            edge = tuple(sorted((a,b)))
            if r['Type'] == 'impassable':
                edges.discard(edge)
            elif r['Type'] in ('sea','land') and a.upper() in land and b.upper() in land:
                edges.add(edge)
    result = sorted(edges)
    cache.parent.mkdir(parents=True,exist_ok=True)
    cache.write_text(json.dumps({'sha256':signature,'edges':result,'coastal_provinces':sorted(coasts)}),encoding='utf-8')
    return [(a,b) for a,b in result if a not in blocked and b not in blocked],coasts-blocked


def components(owners, edges, population):
    lookup = {p:(s,t) for s,ps in owners.items() for p,t in ps.items()}
    parent = {k:k for k in population}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    for a,b in edges:
        x,y = lookup.get(a),lookup.get(b)
        if x not in parent or y not in parent or x[1] != y[1]: continue
        a,b = find(x),find(y)
        if a != b: parent[max(a,b)] = min(a,b)
    groups = defaultdict(list)
    for k in sorted(parent): groups[find(k)].append(k[0])
    return {k:ss for k,ss in sorted(groups.items())}


def coastal(ledger,state,tag):
    f = ledger.target.states[state]
    if hasattr(ledger,'coastal_provinces'):
        return any(p in ledger.coastal_provinces and t==tag for p,t in ledger.owners[state].items())
    return 'naval_exit_id' in f and ledger.owners[state].get(f.get('port')) == tag


def provision(ledger,political,graph,managed_tags,baseline,policy):
    national = Counter()
    for (s,t),p in ledger.population.items(): national[t] += p
    reports = []
    for (anchor,tag),states in graph.items():
        if tag not in managed_tags: continue
        capital = political['countries'][tag]['capital']
        capital_component = capital in states
        ports = [s for s in states if coastal(ledger,s,tag)]
        # One port at each disconnected land component, including the capital end.
        port = max(ports,key=lambda s:(ledger.population[s,tag],s)) if ports else None
        if port and ledger.allowed('building_port',tag) and ((port,tag,'building_port') in ledger.rows or ledger.capped_room(port,tag,'building_port') > 0):
            n = max(1,ledger.rows.get((port,tag,'building_port'),{}).get('levels',0))
            ledger.put(port,tag,'building_port',n,'land_component_market_connection',ledger.pms('building_port',tag))
        connected = capital_component or bool(port and (port,tag,'building_port') in ledger.rows)
        reports.append({'country':tag,'states':states,'capital_component':capital_component,
                        'port_state':port,'has_local_port_connection':connected,
                        'reason':None if connected else 'landlocked_exclave_or_navigation_locked'})
    # Existing anchorages do not supply shipping. Activate an unlocked productive method.
    for (s,t,k),r in list(ledger.rows.items()):
        if t in managed_tags and k == 'building_port':
            if not coastal(ledger,s,t):
                ledger.put(s,t,k,0,'port_province_not_owned')
            else:
                ledger.put(s,t,k,r['levels'],'productive_shipping',ledger.pms(k,t))
    uk_levels = sum(r['levels'] for r in baseline['buildings'] if r['building'] == 'building_trade_center')
    for tag in sorted(managed_tags):
        states = [s for s,t in ledger.population if t == tag]
        desired = math.ceil(national[tag]/baseline['population']*uk_levels*policy['trade_scale'])
        if hasattr(ledger,'development'):
            desired = math.floor(national[tag]/baseline['population']*uk_levels*policy['trade_scale']*ledger.development.profiles[tag]['trade_reference_factor']+.5)
        existing = sum(r['levels'] for r in ledger.rows.values() if r['owner']==tag and r['building']=='building_trade_center')
        if hasattr(ledger,'development') and existing > desired:
            old = {s:ledger.rows.get((s,tag,'building_trade_center'),{}).get('levels',0) for s in states}
            for s,n in apportioned(old,desired).items():
                if old[s]: ledger.put(s,tag,'building_trade_center',n,'trade_capacity_matches_source_commercialization')
            existing = desired
        candidates = {s:ledger.population[s,tag]*(2 if coastal(ledger,s,tag) else 1) for s in states}
        if desired > existing:
            from economy_capacity import capped_allocation
            extras,_ = capped_allocation(candidates,desired-existing,{s:ledger.capped_room(s,tag,'building_trade_center') for s in states})
            for s,n in extras.items():
                if n: ledger.add(s,tag,'building_trade_center',n,'source_commercialization_trade_capacity')
        # Reserve merchant marine for overseas domestic traffic as well as trading.
        overseas_usage = sum(sum(ledger.target.infrastructure_usage(r['building'])*r['levels'] for r in ledger.local(s,tag))
                             for g in reports if g['country']==tag and not g['capital_component'] for s in g['states'])
        reserve = overseas_usage*policy['overseas_infrastructure_shipping_rate']*policy['shipping_distance_buffer']
        need = max(0,reserve-ledger.balance(tag)['merchant_marine'])
        candidates = sorted((s for s in states if coastal(ledger,s,tag)),key=lambda s:(-ledger.population[s,tag],s))
        for s in candidates:
            if need <= 0: break
            if not ledger.allowed('building_port',tag): continue
            pms = ledger.pms('building_port',tag)
            output = ledger.target.coefficients('building_port',pms,ledger.techs[tag])['outputs'].get('merchant_marine',0)
            if not output: continue
            n = min(math.ceil(need/output),ledger.capped_room(s,tag,'building_port'))
            ledger.add(s,tag,'building_port',n,'trade_and_overseas_shipping_capacity',pms)
            need -= n*output
        if need > .001:
            ledger.warnings.append({'country':tag,'reason':'merchant_marine_requires_foreign_transit_or_import','uncovered':need})
    # A port on an exclave is insufficient without a reachable port at the capital end.
    for tag in managed_tags:
        groups = [g for g in reports if g['country']==tag]
        capital_group = next((g for g in groups if g['capital_component']),None)
        if len(groups)>1 and (not capital_group or not capital_group['port_state']):
            for g in groups:
                if not g['capital_component']:
                    g['has_local_port_connection'] = False
                    g['reason'] = 'capital_component_has_no_owned_port_requires_transit_or_market_union'
    return reports
