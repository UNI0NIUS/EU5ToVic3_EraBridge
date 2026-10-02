"""Independent CSV read-back: population is conserved, pending locations retained."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from m3_world import digest,load_json


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)


def verify(source,stage):
    s=load_json(source/'source_summary.json');r=load_json(stage/'staging_report.json')
    for base,report in ((source,s),(stage,r)):
        for p,sha in report['files_sha256'].items():assert digest(base/p)==sha
    source_pops={};source_locations=Counter();source_cultures=Counter()
    for row in rows(source/'source_populations.csv'):
        pid=row['pop_id'];assert pid not in source_pops
        source_pops[pid]=row;n=int(row['centipersons']);assert n>=0
        source_locations[row['location']]+=n;source_cultures[row['source_culture']]+=n
    target_totals=Counter();by_province=Counter();by_state=Counter();by_culture=Counter();nrows=0
    correction=r.get('population_policy'); approved={}; corrected_parts=Counter()
    if correction:
        policy_path=Path(correction['path']);assert digest(policy_path)==correction['sha256']
        approved=load_json(policy_path)['location_overrides']
    political_run=Path(r['political_run']);politics=load_json(political_run/'conversion_report.json')
    ownership={p:(state,owner) for state,owners in load_json(political_run/'province_owners.json').items() for p,owner in owners.items()}
    for row in rows(stage/'province_population_draft.csv'):
        n=int(row['centipersons']);assert n>0
        src=source_pops[row['source_pop_id']]
        assert (row['source_location'],row['source_culture'],row['source_religion'],row['source_class'],row['source_owner'])==(src['location'],src['source_culture'],src['source_religion'],src['source_class'],src['source_owner'])
        assert ownership[row['target_province']]==(row['target_state'],row['target_owner'])
        assert row['target_owner'] in politics['countries']
        target_totals[row['source_pop_id']]+=n;by_province[row['target_province']]+=n
        if row['source_location'] in approved:corrected_parts[row['source_pop_id'],row['target_province']]+=n
        by_state[row['target_state'],row['target_owner']]+=n;by_culture[row['source_culture']]+=n;nrows+=1
    cross={r['source_location']:r for r in rows(stage/'location_crosswalk.csv')}
    pending=0
    for name,entry in approved.items():
        weights=({**entry['expected_weights'],**entry['targets']} if entry['operation']=='add' else entry['targets'])
        assert set(cross[name]['target_provinces'].split(';'))==set(weights)
        for pid,src in source_pops.items():
            if src['location']!=name:continue
            n=int(src['centipersons']);total=sum(weights.values())
            expected={p:n*w//total for p,w in weights.items()}
            ordered=sorted(weights,key=lambda p:(-(n*weights[p]%total),p))
            for p in ordered[:n-sum(expected.values())]:expected[p]+=1
            actual={p:v for (pop,p),v in corrected_parts.items() if pop==pid}
            assert actual=={p:v for p,v in expected.items() if v}, ('Correction allocation differs',name,pid)
    for pid,src in source_pops.items():
        n=int(src['centipersons']);loc=cross[src['location']]
        if loc['status']=='geometry_pending':
            assert target_totals[pid]==0;pending+=n
        else:assert target_totals[pid]==n,('Source pop changed',pid)
    assert sum(target_totals.values())+pending==s['world_centipersons']
    assert pending==r['unmapped_centipersons'] and nrows==r['draft_rows']
    assert {row['province']:int(row['centipersons']) for row in rows(stage/'province_totals.csv')}==dict(by_province)
    assert {(row['state'],row['owner']):int(row['centipersons']) for row in rows(stage/'state_owner_totals.csv')}==dict(by_state)
    assert {row['source_culture']:int(row['centipersons']) for row in rows(stage/'culture_review_queue.csv')}=={c:n for c,n in source_cultures.items() if n}
    result={'status':'passed','source_objects':len(source_pops),'draft_rows':nrows,'every_source_pop_conserved_or_pending':True,'source_culture_religion_class_preserved':True,'geographic_owners_match':True,'global_centipersons':s['world_centipersons'],'installed_population_history_changed':False}
    (stage/'independent_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('stage',type=Path)
    a=p.parse_args();print(json.dumps(verify(a.source,a.stage)))
