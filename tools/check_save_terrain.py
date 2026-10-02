"""Run the generic terrain planner on an audited source save (no mod installation)."""
import argparse,csv,json
from decimal import Decimal
from collections import Counter,defaultdict
from pathlib import Path
from types import SimpleNamespace
from pdx_text import root
from build_m2_prototype import objects,strings
from m3_world import fields,province,digest
from m3_uncolonized import province_land_edges
from terrain_connectivity import source_seeds,complete,require_export_ready


def check(a):
    read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
    if a.save:
        from source_geography_ledger import extract
        a.cultures=a.out/'source_evidence.json';culture=extract(a.save,a.audit,a.cultures)
    else:culture=read(a.cultures)
    audit=read(a.audit)
    assert culture['audit_sha256']==digest(a.audit) and culture['source_date']==audit['date']
    states={k[2:] for k,o in objects(root((a.game/'common/history/states/00_states.txt').read_text(encoding='utf-8-sig')).fields()['STATES'])}
    province_states={}
    for path in sorted((a.game/'map_data/state_regions').glob('*.txt')):
        for s,o in objects(root(path.read_text(encoding='utf-8-sig'))):
            if s in states:
                for p in strings(fields(o)['provinces']):province_states[province(p)]=s
    mapping=defaultdict(set)
    for key,link in objects(root(a.mapping.read_text(encoding='utf-8-sig')).fields()['0.0.0']):
        if key=='link':
            names={v for k,v in link.entries() if k=='eu5'}
            for k,v in link.entries():
                if k=='vic3':mapping[province(v)].update(names)
    default=root((a.eu5/'in_game/map_data/default.map').read_text(encoding='utf-8-sig')).fields()
    uninhabitable={n for k in ['sea_zones','lakes','impassable_mountains','non_ownable'] for n in strings(default[k])}
    source={l['name']:l for l in audit['locations']}
    assert set(culture['location_cultures'])<=source.keys()
    for name,location in source.items():
        counts=culture['location_cultures'].get(name,{})
        assert all(isinstance(n,int) and n>=0 for n in counts.values())
        assert sum(counts.values())==int(Decimal(location['population_persons'])*100),'Population evidence mismatch: '+name
    review_count=0;location_weights={}
    if a.geography_reviews:
        geo=read(a.geography_reviews)
        assert geo['source_map_sha256']==digest(a.eu5/'in_game/map_data/locations.png')
        assert geo['target_map_sha256']==digest(a.game/'map_data/provinces.png')
        assert not any(k in geo for k in ['owners','countries','source_sha256']), 'Geography must not encode campaign ownership'
        reviewed=set(geo['locations'])
        for p in mapping:mapping[p]-=reviewed
        for name,row in geo['locations'].items():
            if name not in source:raise ValueError('Reviewed source location is absent from this save: '+name)
            for target in row['targets']:
                if target['province'] not in province_states:raise ValueError('Reviewed geography is not target land')
                mapping[target['province']].add(name)
            location_weights[name]={t['province']:t['weight'] for t in row['targets']}
        review_count=len(reviewed)
    seeds,natives,no_pop=source_seeds(province_states,mapping,source,uninhabitable,culture['location_cultures'],location_weights=location_weights)
    terrain_review_missing=[];terrain_review_count=0
    if getattr(a,'terrain_reviews',None):
        from terrain_reviews import validate_document,apply_references
        entries=validate_document(read(a.terrain_reviews),digest(a.eu5/'in_game/map_data/locations.png'),
                                  digest(a.game/'map_data/provinces.png'),province_states,source)
        terrain_review_missing=apply_references(entries,province_states,source,uninhabitable,culture['location_cultures'],seeds,natives)
        terrain_review_count=sum(r['status']=='mapped' for r in entries.values())
    world=SimpleNamespace(game=a.game,owners={s:{p:'land' for p,ss in province_states.items() if ss==s} for s in states},province_state=province_states)
    edges=province_land_edges(world,a.cache)
    plan=complete(province_states,edges,seeds,natives)
    from native_country_tags import allocate
    reserved={k for path in (a.game/'common/country_definitions').glob('*.txt') for k,o in objects(root(path.read_text(encoding='utf-8-sig')))}
    # Conservatively reserve the entire legacy converted-source namespace.
    alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';reserved.update('E'+x+y for x in alphabet for y in alphabet)
    tags=allocate([r['owner'] for r in plan['native_components']],reserved)
    anchored_states={province_states[p] for p in seeds}
    no_anchor_states=states-anchored_states
    recovered_states=[s for s in sorted(no_anchor_states) if all(p in plan['provinces'] for p,ss in province_states.items() if ss==s)]
    inverse=defaultdict(set)
    for p,names in mapping.items():
        if p in province_states:
            for n in names:inverse[n].add(p)
    unmapped_populated=[{'location':n,'owner':l['owner'],'persons':l['population_persons']} for n,l in source.items()
                        if float(l['population_persons'])>0 and not inverse[n]]
    result={'source_date':audit['date'],'source_sha256':culture['source_sha256'],**plan['summary'],
            'source_unowned_habitable_locations':sum(not l['owner'] and n not in uninhabitable for n,l in source.items()),
            'source_unowned_habitable_without_population':sum(not l['owner'] and n not in uninhabitable and not sum(culture['location_cultures'].get(n,{}).values()) for n,l in source.items()),
            'seed_counts':dict(Counter(r['kind'] for r in seeds.values())),
            'states_without_direct_seeds':sorted(no_anchor_states),'whole_states_recovered_through_land':recovered_states,
            'unmapped_populated_source_locations':len(unmapped_populated),
            'terrain_export_ready':plan['export_ready'],'full_conversion_ready':False,
            'reusable_geography_reviews':review_count,'native_tags_allocated':len(tags),'native_tag_prefixes':dict(Counter(t[0] for t in tags.values())),
            'terrain_reference_reviews':terrain_review_count,'terrain_references_without_current_evidence':len(terrain_review_missing),
            'campaign_specific_reviews_used':False,'native_identity_basis':'exact source-culture keys; V3 culture export is a separate phase',
            'limits':['Terrain planning only; no complete 1337 V3 mod generated.','Unresolved components block terrain export; no Russia/vanilla fallback.',
                      'No 1780-specific political, population or island decisions are reused.'],
            'input_sha256':{str(p):digest(p) for p in [a.audit,a.cultures,a.mapping,a.game/'map_data/provinces.png',a.eu5/'in_game/map_data/default.map',Path(__file__),Path(__file__).with_name('terrain_connectivity.py'),Path(__file__).with_name('native_country_tags.py'),Path(__file__).with_name('source_geography_ledger.py')]}}
    a.out.mkdir(parents=True,exist_ok=True)
    if a.geography_reviews:result['input_sha256'][str(a.geography_reviews)]=digest(a.geography_reviews)
    if getattr(a,'terrain_reviews',None):result['input_sha256'][str(a.terrain_reviews)]=digest(a.terrain_reviews)
    geometry_inputs=[a.game/'map_data/adjacencies.csv',a.game/'map_data/default.map',a.game/'common/history/states/00_states.txt',*sorted((a.game/'map_data/state_regions').glob('*.txt'))]
    result['input_sha256'].update({str(p):digest(p) for p in geometry_inputs})
    for name,data in [('summary.json',result),('plan.json',plan),('seeds.json',seeds),('native_tags.json',tags),('unmapped_populated_sources.json',unmapped_populated),('source_empty_evidence.json',no_pop),('terrain_reviews_without_evidence.json',terrain_review_missing)]:
        (a.out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    with (a.out/'unresolved_terrain.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['component','state','province','reason'])
        for component in plan['unresolved_components']:
            for p in component['provinces']:writer.writerow([component['component'],province_states[p],p,component['reason']])
    if a.require_complete:require_export_ready(plan)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--cultures',type=Path);group.add_argument('--save',type=Path,help='Decoded save; extract and independently cross-check its own population evidence')
    p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Victoria 3/game'));p.add_argument('--eu5',type=Path,default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--mapping',type=Path,default=Path('EU5ToVic3/Data_Files/configurables/province_mappings.txt'));p.add_argument('--cache',type=Path,default=Path('.local/m3/cache/tribal_land_edges.json'));p.add_argument('--require-complete',action='store_true');p.add_argument('--geography-reviews',type=Path)
    p.add_argument('--terrain-reviews',type=Path,help='Workstation terrain references; dynamically resolve this save without transferring population')
    a=p.parse_args();print(json.dumps(check(a),ensure_ascii=False,indent=2))
