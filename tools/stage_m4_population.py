"""Auditable provisional province allocation; never writes game population history."""
import argparse
from collections import Counter,defaultdict
import csv
import json
from pathlib import Path

from pdx_text import root
from build_m2_prototype import objects,allocate,strings
from build_m3_world import load_localization
from m3_cultures import resolve_culture
from m3_world import World,load_json,digest,fields
from location_reviews import validate_document
from m4_location_overrides import apply_overrides

ROOT=Path(__file__).resolve().parents[1]


def stage(run,source,out,game,eu5,location_reviews=None,population_policy=None):
    if out.exists():raise ValueError('Refusing to overwrite population staging')
    report=load_json(run/'conversion_report.json');summary=load_json(source/'source_summary.json')
    profile_path=ROOT/'config/personal/m3_world.json';profile=load_json(profile_path)
    assert digest(profile_path)==report['profile_sha256']
    assert summary['source_sha256']==report['source_sha256']
    for name,sha in summary['files_sha256'].items():assert digest(source/name)==sha
    audit=load_json(ROOT/'.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json')
    politics=load_json(ROOT/'.local/m3/politics-with-cultures.json')
    w=World(game,eu5,audit,politics,profile,ROOT/'.local/m3/cache');w.geometry();w.politics_model()
    if report.get('uncolonized_tribes'):
        from m3_uncolonized import restore
        restore(w,report['uncolonized_tribes'])
    if report.get('empty_terrain_attachments'):
        from m5_territory_replay import restore as restore_terrain
        restore_terrain(w,report)
    if report.get('terrain_finalization'):
        from m3_terrain_finalization import apply as finalize_terrain
        finalize_terrain(w,report['terrain_finalization'])
    if report.get('frontier_finalization'):
        from m3_colonial_frontier import apply as finalize_frontier
        finalize_frontier(w,report['frontier_finalization'])
    assert w.owners==load_json(run/'province_owners.json')
    valid={k for p in (game/'common/cultures').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    valid.update(c['target'] for c in report['custom_cultures'])
    source_defs={k:fields(o) for p in (eu5/'in_game/common/cultures').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    localization=load_localization(eu5/'main_menu/localization/simp_chinese')
    resolutions={}; by_language=defaultdict(set)
    for c in source_defs:
        try:
            target,method=resolve_culture(c,profile,valid)
            resolutions[c]=(target,method)
            by_language[source_defs[c].get('language')].add(target)
        except ValueError:pass
    inverse=defaultdict(set)
    for p,names in w.mapping.items():
        if p in w.province_state:
            for n in set(names):inverse[n].add(p)
    province_owner={p:(s,t) for s,owners in w.owners.items() for p,t in owners.items()}
    reviewed_weights={}
    if location_reviews:
        source_rows=[]
        with (source/'source_locations.csv').open(encoding='utf-8-sig',newline='') as f:
            source_rows=list(csv.DictReader(f))
        pending_names={r['location'] for r in source_rows if int(r['centipersons'])>0 and not inverse[r['location']]}
        decisions=validate_document(load_json(location_reviews),summary['source_sha256'],digest(run/'province_owners.json'),pending_names,set(province_owner))
        for name,row in decisions.items():
            if row['status']=='mapped':
                reviewed_weights[name]={t['province']:t['weight'] for t in row['targets']}
                inverse[name]=set(reviewed_weights[name])
    workstation_count=len(reviewed_weights)
    corrections=[]
    if population_policy:
        policy=load_json(population_policy)
        assert policy['schema']==1
        with (source/'source_locations.csv').open(encoding='utf-8-sig',newline='') as f:
            source_names={r['location'] for r in csv.DictReader(f)}
        corrections=apply_overrides(inverse,reviewed_weights,policy['location_overrides'],source_names,set(province_owner))
    out.mkdir(parents=True)
    culture_totals=Counter(); allocated=pending=unreviewed=rows=0
    per_province=Counter();per_state_owner=Counter();missing=Counter(); incoming_by_loc=Counter(); transfers=Counter()
    with (source/'source_populations.csv').open(encoding='utf-8-sig',newline='') as f, (out/'province_population_draft.csv').open('w',encoding='utf-8-sig',newline='') as g:
        writer=csv.writer(g);writer.writerow(['source_location','source_pop_id','source_owner','target_province','target_state','target_owner','source_culture','target_culture','source_religion','source_class','centipersons','mapping_status'])
        for row in csv.DictReader(f):
            n=int(row['centipersons']);culture_totals[row['source_culture']]+=n
            if not n:continue
            targets=inverse[row['location']]
            resolved=resolutions.get(row['source_culture'])
            if not targets:
                pending+=n;missing[row['location']]+=n;continue
            # An initial geometric draft, not a claim of observed within-location
            # density. Equal shares are explicit and conserve every centiperson.
            parts=allocate(n,reviewed_weights.get(row['location'],{p:1 for p in targets}))
            for p,amount in parts.items():
                if not amount:continue
                state,owner=province_owner[p]
                writer.writerow([row['location'],row['pop_id'],row['source_owner'],p,state,owner,row['source_culture'],resolved[0] if resolved else '',row['source_religion'],row['source_class'],amount,'reviewed' if resolved else 'culture_review_pending'])
                rows+=1;allocated+=amount;per_province[p]+=amount;per_state_owner[state,owner]+=amount
                incoming_by_loc[row['location']]+=amount
                if not resolved:unreviewed+=amount
                if report['countries'][owner]['source_id']!=row['source_owner']:transfers[row['source_owner'],owner]+=amount
    assert allocated+pending==summary['world_centipersons']
    assert dict(culture_totals)==summary['culture_centipersons']
    with (source/'source_locations.csv').open(encoding='utf-8-sig',newline='') as f,(out/'location_crosswalk.csv').open('w',encoding='utf-8-sig',newline='') as g:
        writer=csv.writer(g);writer.writerow(['source_location','source_owner','source_centipersons','allocated_centipersons','pending_centipersons','target_provinces','status'])
        for row in csv.DictReader(f):
            name=row['location'];n=int(row['centipersons'])
            assert incoming_by_loc[name]+missing[name]==n
            writer.writerow([name,row['source_owner'],n,incoming_by_loc[name],missing[name],';'.join(sorted(inverse[name])),'no_population' if not n else ('geometry_pending' if missing[name] else 'linked')])
    with (out/'culture_review_queue.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.writer(f);writer.writerow(['source_culture','name','centipersons','source_language','source_groups','approved_target','method','same_language_candidates_for_review'])
        for culture,n in culture_totals.most_common():
            if not n:continue
            sf=source_defs.get(culture,{});target,method=resolutions.get(culture,('','review_pending'))
            groups=strings(sf['culture_groups']) if 'culture_groups' in sf else []
            writer.writerow([culture,localization.get(culture,culture),n,sf.get('language',''),';'.join(groups),target,method,'' if target else ';'.join(sorted(by_language.get(sf.get('language'),set())))])
    def write_rows(name,header,rows):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(header);writer.writerows(rows)
    write_rows('province_totals.csv',['province','state','owner','centipersons'],((p,*province_owner[p],n) for p,n in sorted(per_province.items())))
    write_rows('state_owner_totals.csv',['state','owner','centipersons'],((*k,v) for k,v in sorted(per_state_owner.items())))
    write_rows('geographic_owner_transfers.csv',['source_owner','target_owner','centipersons'],((*k,v) for k,v in transfers.most_common()))
    result={'schema':1,'status':'draft_review_required_not_installed','source_sha256':summary['source_sha256'],
            'political_run':str(run.resolve()),'profile_sha256':digest(profile_path),'mapping_sha256':w.mapping_sha256,
            'allocation_rule':'Reviewed location weights where supplied; otherwise equal shares per deduplicated source-location link. Largest remainder in centipersons; not a density estimate.',
            'location_reviews':{'path':str(location_reviews.resolve()),'sha256':digest(location_reviews),'applied_locations':workstation_count} if location_reviews else None,
            'population_policy':{'path':str(population_policy.resolve()),'sha256':digest(population_policy),'location_corrections':corrections} if population_policy else None,
            'world_centipersons':summary['world_centipersons'],'allocated_centipersons':allocated,'unmapped_centipersons':pending,
            'locations_without_geometry':len(missing),'linked_target_provinces':len(per_province),'draft_rows':rows,
            'active_source_cultures':sum(n>0 for n in culture_totals.values()),
            'reviewed_active_cultures':sum(n>0 and c in resolutions for c,n in culture_totals.items()),
            'mapped_population_with_pending_culture_centipersons':unreviewed,
            'checks':{'global_population_conserved':True,'every_location_conserved':True,'source_culture_totals_match':True,'political_map_unchanged':True},
            'limitations':['Unmapped locations retained in queue, not dropped or teleported.','One-to-many allocation weights require geographic review.','Source estate/class is retained; not mapped to V3 professions.','No V3 population, homeland, economic or discrimination history replaced by this draft.']}
    result['files_sha256']={p.name:digest(p) for p in out.glob('*.csv')}
    (out/'staging_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('files_sha256','limitations','checks')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    p.add_argument('--eu5',type=Path,default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--location-reviews',type=Path,help='Validated population-only mappings from the local workstation')
    p.add_argument('--population-policy',type=Path,help='Explicit conversation-approved corrections; never writes workstation reviews')
    a=p.parse_args();print(json.dumps(stage(a.run,a.source,a.out,a.game,a.eu5,a.location_reviews,a.population_policy)))
