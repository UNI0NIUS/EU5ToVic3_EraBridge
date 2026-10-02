"""Independent before/after readback: only approved culture categories may change."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from m3_world import load_json,digest
from m4_religions import definitions

ROOT=Path(__file__).resolve().parents[1]

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)

def verify(old,new):
    before=load_json(old/'demographics/demographics_report.json');after=load_json(new/'demographics/demographics_report.json')
    profile=load_json(Path(after['profile_path']))
    oc={r['source_culture']:r for r in rows(old/'demographics/resident_culture_crosswalk.csv')}
    nc={r['source_culture']:r for r in rows(new/'demographics/resident_culture_crosswalk.csv')}
    assert oc.keys()==nc.keys() and all(x['target_culture'] for x in nc.values())
    mapping={};changed=[]
    for source,a in oc.items():
        b=nc[source];assert a['centipersons']==b['centipersons']
        if a['target_culture']!=b['target_culture']:
            assert profile['culture_compaction'][source]['target']==b['target_culture']
            changed.append(source)
        previous=mapping.setdefault(a['target_culture'],b['target_culture'])
        assert previous==b['target_culture'],('Ambiguous old category split',source)
    new_migrants={r['target']:r for r in after['migrant_cultures']['cultures']}
    migrant_members=Counter()
    for c in before['migrant_cultures']['cultures']:
        matches=[r for r in new_migrants.values() if r['source']==c['source'] and set(c['states'])<=set(r['states'])]
        assert len(matches)==1
        target=matches[0]['target'];mapping[c['target']]=target;migrant_members[target]+=c['centipersons']
        assert c['language']==matches[0]['language'] and c['template']==matches[0]['template']
    assert dict(migrant_members)=={k:r['centipersons'] for k,r in new_migrants.items()}
    def populations(run):
        result={}
        for r in rows(run/'demographics/resident_population_groups.csv'):
            key=tuple(r[k] for k in ('state','owner','culture','religion'));assert key not in result
            result[key]=int(r['centipersons'])
        return result
    a=populations(old);b=populations(new);expected=Counter();old_totals=Counter();new_totals=Counter()
    for (state,owner,culture,religion),n in a.items():
        expected[state,owner,mapping[culture],religion]+=n;old_totals[state,owner,religion]+=n
    for (state,owner,culture,religion),n in b.items():new_totals[state,owner,religion]+=n
    assert dict(expected)==b and old_totals==new_totals
    assert sum(a.values())==sum(b.values())==after['world_centipersons']==before['world_centipersons']
    hashes={}
    for relative in ('location_reviews.snapshot.json','population_policy.snapshot.json','staging/province_population_draft.csv','staging/location_crosswalk.csv','staging/province_totals.csv','staging/state_owner_totals.csv','demographics/resident_religion_crosswalk.csv','template_fallback/population_history_preview.txt'):
        assert digest(old/relative)==digest(new/relative),relative;hashes[relative]=digest(new/relative)
    old_political=Path(load_json(old/'staging/staging_report.json')['political_run'])
    new_political=Path(load_json(new/'staging/staging_report.json')['political_run'])
    assert digest(old_political/'province_owners.json')==digest(new_political/'province_owners.json')
    op=load_json(old_political/'conversion_report.json');np=load_json(new_political/'conversion_report.json')
    for key in ('countries','custom_cultures','source_sha256'):assert op[key]==np[key],key
    for rel,sha in op['output_sha256'].items():
        if rel.replace('\\','/').startswith(('common/cultures/','common/discrimination_traits/','common/discrimination_trait_groups/','common/history/pops/','common/history/states/')):
            assert np['output_sha256'][rel]==sha,rel
    evidence={}
    for rel in ('staging/independent_verification.json','demographics/independent_verification.json','demographics/culture_asset_verification.json','template_fallback/independent_verification.json'):
        assert load_json(new/rel)['status']=='passed';evidence[rel]=digest(new/rel)
    emitted=definitions(new/'demographics/identity_assets/common/cultures')
    assert all('eu5_resident_'+c not in emitted for c in after['culture_compaction'])
    papuan=[c for c,d in profile['custom_resident_cultures'].items() if Path(d.get('asset_basis',{}).get('source_file','')).name=='papuan.txt']
    assert len(papuan)==103 and {nc[c]['target_culture'] for c in papuan}=={'melanesian'}
    result={'status':'passed','previous_run':str(old.resolve()),'run':str(new.resolve()),
        'target_cultures_before':len({k[2] for k in a}),'target_cultures_after':len({k[2] for k in b}),
        'population_groups_before':len(a),'population_groups_after':len(b),
        'resident_assets_before':len(before['custom_resident_cultures']['cultures']),'resident_assets_after':len(emitted),
        'migrant_assets_before':len(before['migrant_cultures']['cultures']),'migrant_assets_after':len(new_migrants),
        'source_cultures_traceable':len(nc),'additional_source_keys_remapped':len(changed),
        'papuan_source_keys':103,'papuan_output_categories':1,
        'world_centipersons':sum(b.values()),'whole_group_ledger_equals_approved_remap':True,
        'state_owner_religion_totals_unchanged':True,'political_borders_and_country_identities_unchanged':True,
        'political_baseline_before':str(old_political),'political_baseline_after':str(new_political),
        'unchanged_artifact_sha256':hashes,'independent_evidence_sha256':evidence,'culture_budget':after['culture_budget'],
        'verifier_sha256':digest(Path(__file__)),'performance_benchmarked_in_game':False,'deployment_ready':False}
    old_template=list(rows(old/'template_fallback/template_population_groups.csv'))
    new_template=list(rows(new/'template_fallback/template_population_groups.csv'))
    result['candidate_cultures_before']=len({k[2] for k in a}|{x['culture'] for x in old_template})
    result['candidate_cultures_after']=len({k[2] for k in b}|{x['culture'] for x in new_template})
    result['candidate_population_groups_after']=len(b)+len(new_template)
    candidate=load_json(new/'template_fallback/template_report.json')['candidate_culture_budget']
    assert result['candidate_cultures_after']==candidate['counts']['used_cultures']<=candidate['limits']['max_used_cultures']
    result['candidate_culture_budget']=candidate
    (new/'global_culture_compaction_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,default=ROOT/'.local/m4/runs/20261001-065707-148fbda9');p.add_argument('--after',type=Path)
    a=p.parse_args();print(json.dumps(verify(a.before,a.after or Path(load_json(ROOT/'.local/m4/demographics-latest.json')['run'])),ensure_ascii=True,indent=2))
