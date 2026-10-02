"""Source-population-based decentralized countries on explicitly unowned land."""
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from m3_world import base36, digest


def population_evidence(directory, source_sha):
    directory=Path(directory)
    summary=json.loads((directory/'source_summary.json').read_text(encoding='utf-8-sig'))
    if summary['source_sha256']!=source_sha:raise ValueError('Uncolonized population source mismatch')
    path=directory/'source_populations.csv'
    if digest(path)!=summary['files_sha256'][path.name]:raise ValueError('Population source ledger changed')
    location_path=directory/'source_locations.csv'
    if digest(location_path)!=summary['files_sha256'][location_path.name]:raise ValueError('Source location ledger changed')
    by_location=defaultdict(Counter)
    with path.open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            n=int(row['centipersons'])
            if n<0:raise ValueError('Negative source population')
            by_location[row['location']][row['source_culture'],row['source_religion']]+=n
    return by_location, {str(path.resolve()):digest(path),str(location_path.resolve()):digest(location_path),
                         str((directory/'source_summary.json').resolve()):digest(directory/'source_summary.json')}


def read_crosswalk(path, source, target):
    result={}
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            if row[source] in result and result[row[source]]!=row[target]:raise ValueError('Conflicting identity mapping')
            result[row[source]]=row[target]
    return result


def staged_evidence(stage, source_sha):
    stage=Path(stage);report=json.loads((stage/'staging_report.json').read_text(encoding='utf-8-sig'))
    if report['source_sha256']!=source_sha:raise ValueError('Reviewed population geography belongs to another save')
    path=stage/'province_population_draft.csv'
    if digest(path)!=report['files_sha256'][path.name]:raise ValueError('Reviewed population geography changed')
    populations=defaultdict(Counter);owners=defaultdict(set)
    with path.open(encoding='utf-8-sig',newline='') as stream:
        for r in csv.DictReader(stream):
            n=int(r['centipersons'])
            if n<0:raise ValueError('Negative staged population')
            if not n:continue
            populations[r['target_province']][r['source_culture'],r['source_religion']]+=n
            owners[r['target_province']].add(r['source_owner'])
    return populations,owners,{str(path.resolve()):digest(path),str((stage/'staging_report.json').resolve()):digest(stage/'staging_report.json')}


def prepare(world, population_source, culture_path, religion_path, policy_path, cache, population_stage=None):
    populations,inputs=population_evidence(population_source,world.profile['source_sha256'])
    policy=json.loads(Path(policy_path).read_text(encoding='utf-8-sig'))
    province_pops=province_owners=None
    if population_stage:
        province_pops,province_owners,stage_inputs=staged_evidence(population_stage,world.profile['source_sha256']);inputs.update(stage_inputs)
    report=plan(world,populations,read_crosswalk(culture_path,'source_culture','target_culture'),
                read_crosswalk(religion_path,'source_religion','target_religion'),policy,province_land_edges(world,cache),province_pops,province_owners)
    paths=[Path(policy_path),Path(culture_path),Path(religion_path),Path(__file__),
           world.game/'map_data/provinces.png',world.game/'map_data/default.map',world.game/'map_data/adjacencies.csv']
    paths.extend(sorted((world.game/'map_data/state_regions').glob('*.txt')))
    report.update(policy=policy,source_sha256=world.profile['source_sha256'],reviewed_population_geography=bool(population_stage),
                  input_sha256={**inputs,**{str(p.resolve()):digest(p) for p in paths}},runtime_verified=False)
    apply(world,report)
    return report


def restore(world, report):
    """Replay the reviewed political decision when demographic staging rebuilds geometry."""
    if report['source_sha256']!=world.profile['source_sha256']:raise ValueError('Uncolonized source changed')
    for path,sha in report['input_sha256'].items():
        if digest(Path(path))!=sha:raise ValueError('Uncolonized rule/input changed: '+path)
    apply(world,report)


def choose_tag(identity, reserved):
    # Three-character native tags, deterministic hashing with collision checks.
    start=int(hashlib.sha256(identity.encode()).hexdigest()[:12],16)%1296
    for offset in range(1296):
        tag='U'+base36((start+offset)%1296).zfill(2)
        if tag not in reserved:
            reserved.add(tag);return tag
    raise ValueError('No free decentralized country tags')


def province_land_edges(world, cache):
    from economy_market import land_edges
    land_edges(world.game,cache,world.owners)  # Validate or rebuild the map-hashed raster cache.
    saved=json.loads(Path(cache).read_text(encoding='utf-8'))
    # Political territorial continuity includes owned impassable terrain. The
    # economic helper's passability filter would invent hundreds of tiny states.
    land=set(world.province_state)
    edges=[('x'+a[1:].upper(),'x'+b[1:].upper()) for a,b in saved['edges']]
    edges=[(a,b) for a,b in edges if a in land and b in land]
    # Economic transport connectivity includes straits; ethnic land continuity
    # deliberately does not. Reuse the raster cache but remove explicit sea links.
    sea=set()
    with (world.game/'map_data/adjacencies.csv').open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream,delimiter=';'):
            if row['From']!='-1' and row['Type']=='sea':
                sea.add(tuple(sorted(('x'+row['From'][1:].upper(),'x'+row['To'][1:].upper()))))
    return [(a,b) for a,b in edges if tuple(sorted((a,b))) not in sea]


def connected_groups(identities, edges):
    parent={p:p for p in identities}
    def find(p):
        while parent[p]!=p:
            parent[p]=parent[parent[p]];p=parent[p]
        return p
    for a,b in sorted(edges):
        if a not in parent or b not in parent or identities[a]!=identities[b]:continue
        x,y=find(a),find(b)
        if x!=y:parent[max(x,y)]=min(x,y)
    groups=defaultdict(list)
    for p in sorted(parent):groups[find(p)].append(p)
    return list(groups.values())


def plan(world, populations, culture_map, religion_map, policy, edges, province_populations=None, province_source_owners=None):
    if policy.get('schema')!=1 or policy.get('country_type')!='decentralized':
        raise ValueError('Unsupported uncolonized policy')
    for k,v in {'grouping':'connected_land_component_of_mapped_primary_culture','primary_culture':'largest_source_population_before_culture_mapping',
                'tie_break':'source_culture_key','missing_evidence':'retain_and_report'}.items():
        if policy.get(k)!=v:raise ValueError('Unsupported uncolonized rule: '+k)
    if not policy.get('enabled'):return {'countries':{},'transfers':[],'unresolved':[],'excluded':[]}
    unowned=set(policy['unowned_source_owners'])
    inverse=defaultdict(set)
    for p,names in world.mapping.items():
        if p in world.province_state:
            for n in set(names):inverse[n].add(p)
    eligible={};excluded=[];unresolved=[]
    for state,owners in sorted(world.owners.items()):
        for p,old in sorted(owners.items()):
            names=set(world.mapping.get(p,[]))
            habitable=sorted(names-world.uninhabitable)
            if not habitable:continue
            if any(n not in world.locations for n in habitable):raise ValueError('Unknown source location')
            if not all(str(world.locations[n]['owner']) in unowned for n in habitable):
                if any(str(world.locations[n]['owner']) in unowned for n in habitable):
                    excluded.append({'state':state,'province':p,'reason':'mixed_owned_and_unowned_anchors'})
                continue
            if province_source_owners is not None and set(province_source_owners.get(p,set()))-unowned:
                excluded.append({'state':state,'province':p,'reason':'reviewed_population_includes_source_owned_locations'});continue
            cultures=defaultdict(Fraction);religions=defaultdict(Fraction)
            parts=([(province_populations.get(p,{}),1)] if province_populations is not None else
                   [(populations.get(name,{}),len(inverse[name])) for name in habitable])
            for population,denominator in parts:
                for (culture,religion),n in population.items():
                    weight=Fraction(n,denominator)
                    cultures[culture]+=weight;religions[culture,religion]+=weight
            positive={c:n for c,n in cultures.items() if n>0}
            if not positive:
                unresolved.append({'state':state,'province':p,'reason':'no_source_population_evidence'});continue
            dominant=min(positive,key=lambda c:(-positive[c],c));target=culture_map.get(dominant)
            faith=min((r for c,r in religions if c==dominant),key=lambda r:(-religions[dominant,r],r))
            if not target or not religion_map.get(faith):
                unresolved.append({'state':state,'province':p,'source_culture':dominant,
                                   'source_religion':faith,'reason':'unresolved_identity_mapping'});continue
            eligible[p]={'state':state,'from':old,'names':habitable,'culture':target,'source_culture':dominant,
                         'cultures':positive,'religions':religions,
                         'tied_primary_cultures':sorted(c for c,n in positive.items() if n==positive[dominant])}
    for r in getattr(world,'fallbacks',[]):
        if r['rule']=='unmapped_vanilla':
            unresolved.append({'state':r['state'],'province':r['province'],'reason':'no_source_link_uncolonized_status_unknown'})
    countries={};transfers=[];reserved=set(world.country_defs)|set(world.countries)
    for provinces in connected_groups({p:r['culture'] for p,r in eligible.items()},edges):
        target=eligible[provinces[0]]['culture'];positive=defaultdict(Fraction);religions=defaultdict(Fraction);states=defaultdict(Fraction)
        for p in provinces:
            r=eligible[p]
            for c,n in r['cultures'].items():positive[c]+=n;states[r['state']]+=n
            for (c,faith),n in r['religions'].items():
                if culture_map.get(c)==target:religions[faith]+=n
        dominant=min((c for c in positive if culture_map.get(c)==target),key=lambda c:(-positive[c],c))
        faith=min(religions,key=lambda r:(-religions[r],r));religion=religion_map.get(faith)
        if not religion:
            unresolved.extend({'state':eligible[p]['state'],'province':p,'reason':'unresolved_component_religion'} for p in provinces);continue
        capital=min(states,key=lambda s:(-states[s],s))
        tag=choose_tag(target+':'+','.join(provinces),reserved)
        countries[tag]={'source_id':None,'tag':tag,'country_type':'decentralized','capital':capital,'states':sorted(states),
                        'source_culture':dominant,'culture':target,'cultures':[target],'religion':religion,
                        'source_religion':faith,'type_reason':'source_uncolonized_population_plurality',
                        'generated_uncolonized':True,'provinces':len(provinces),'capital_exact':False,
                        'source_culture_centipersons':{c:str(n) for c,n in sorted(positive.items())},
                        'primary_share':float(sum(n for c,n in positive.items() if culture_map.get(c)==target)/sum(positive.values())),
                        'allocation_note':'Province source plurality followed by mapped-culture land connectivity. '+('Reviewed province population geography; exact centipersons.' if province_populations is not None else 'Equal shares per deduplicated source-location link; exact fractional centipersons.')}
        for p in provinces:
            r=eligible[p]
            transfers.append({'state':r['state'],'province':p,'from':r['from'],'to':tag,'source_locations':r['names'],
                              'source_primary_culture':r['source_culture'],'target_primary_culture':target,
                              'tied_primary_cultures':r['tied_primary_cultures'] if len(r['tied_primary_cultures'])>1 else []})
    return {'countries':countries,'transfers':transfers,'unresolved':unresolved,'excluded':excluded}


def apply(world, report):
    """Apply before export/transfers/population/economy, never to an installed save."""
    if set(report['countries']) & (set(world.country_defs)|set(world.countries)):
        raise ValueError('Generated tribal tag collision')
    seen=set()
    for r in report['transfers']:
        p=r['province']
        if p in seen:raise ValueError('Duplicate uncolonized transfer')
        seen.add(p)
        if r['to'] not in report['countries'] or report['countries'][r['to']]['country_type']!='decentralized':
            raise ValueError('Invalid generated tribal owner')
        anchors=set(world.mapping.get(p,[]))-world.uninhabitable
        unowned=set(report.get('policy',{}).get('unowned_source_owners',['0']))
        if not anchors or any(str(world.locations[n]['owner']) not in unowned for n in anchors):
            raise ValueError('Transfer is not proven source-unowned: '+p)
        if world.owners[r['state']][r['province']]!=r['from']:raise ValueError('Uncolonized ownership baseline changed')
    for r in report['transfers']:world.owners[r['state']][r['province']]=r['to']
    # A local native template supplies decentralized technology/laws, never the
    # colonizer's administration. Identity and name are supplied independently.
    from m3_world import fields
    from build_m2_prototype import strings
    natives={t:fields(o) for t,o in world.country_defs.items() if fields(o).get('country_type')=='decentralized'}
    for tag,c in report['countries'].items():
        prior=Counter(world.original[r['state']].get(r['province']) for r in report['transfers'] if r['to']==tag)
        same=[t for t,f in natives.items() if c['culture'] in strings(f.get('cultures'))]
        choices=same or [t for t in prior if t in natives] or sorted(natives)
        if not choices:raise ValueError('No decentralized initialization template')
        template=min(choices,key=lambda t:(-prior[t],t))
        world.countries[tag]={**c,'template':template}
    live=Counter(t for owners in world.owners.values() for t in owners.values())
    removed=[]
    for tag,c in list(world.countries.items()):
        if not live[tag]:
            if c['source_id'] is not None:raise ValueError('Source-owned country lost all territory')
            removed.append(tag);del world.countries[tag]
        else:
            c['provinces']=live[tag]
            if c['capital'] not in world.owners or tag not in world.owners[c['capital']].values():
                states=Counter({s:sum(t==tag for t in ps.values()) for s,ps in world.owners.items()})
                c['capital']=min((s for s,n in states.items() if n),key=lambda s:(-states[s],s));c['capital_exact']=False
    report['removed_empty_fallback_countries']=removed
    world.substates={s:Counter(ps.values()) for s,ps in world.owners.items()}
    world.transfers={}
    for s,old in world.original.items():
        for t in set(old.values()):
            overlap=Counter(world.owners[s][p] for p,v in old.items() if v==t and p in world.owners[s])
            if not overlap:raise ValueError('Template state has no population destination')
            world.transfers[s,t]=overlap
    world.uncolonized_report=report
