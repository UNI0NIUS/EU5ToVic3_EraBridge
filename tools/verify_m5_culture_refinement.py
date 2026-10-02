"""Independent source-object accounting and actual PDX readback for refinement."""
import argparse
import json
from collections import Counter
from pathlib import Path
from m3_world import digest, load_json
from m4_religions import definitions
from package_m4_population_test import parse_pops
from verify_m5_culture_research import rows, collapse


def verify(out, *, check_installation=True, write_evidence=True):
    root=Path(__file__).resolve().parents[1]
    manifest=load_json(out/'refinement_manifest.json');old=Path(manifest['baseline'])
    plan=load_json(out/'refinement_policy.snapshot.json')
    profile=load_json(out/'demographics_profile.snapshot.json')
    baseline_profile=load_json(old/'demographics_profile.snapshot.json')
    old_groups=[g for g in baseline_profile['global_culture_policy']['aggregates'] if len(g['members'])>1]
    expected_sources={s for g in old_groups for s in g['members']}
    member_counts=Counter(s for g in plan['partitions'] for s in g['members'])
    assert member_counts==Counter({s:1 for s in expected_sources}), 'Missing or duplicate partition member'
    assert plan['old_catchalls']==old_groups, 'Old catchall inventory changed'
    replacements={s:g['target'] for g in plan['partitions'] for s in g['members']}
    assert replacements==load_json(out/'explicit_source_replacements.json')
    before={r['source_culture']:r['target_culture'] for r in rows(old/'demographics/resident_culture_crosswalk.csv')}
    after={r['source_culture']:r['target_culture'] for r in rows(out/'demographics/resident_culture_crosswalk.csv')}
    expected_cross={s:replacements.get(s,t) for s,t in before.items()}
    assert after==expected_cross, 'Unexpected source identity mapping change'
    report=load_json(out/'demographics/demographics_report.json')
    old_report=load_json(old/'demographics/demographics_report.json')
    assert report['migrant_cultures']['cultures']==old_report['migrant_cultures']['cultures']
    assert digest(out/'demographics/resident_religion_crosswalk.csv')==digest(old/'demographics/resident_religion_crosswalk.csv')
    migrant={(r['source'],s):r['target'] for r in old_report['migrant_cultures']['cultures'] for s in r['states']}
    religion={r['source_religion']:r['target_religion'] for r in rows(old/'demographics/resident_religion_crosswalk.csv')}
    source={r['pop_id']:int(r['centipersons']) for r in rows(root/'.local/m4/source-1780-population/source_populations.csv')}
    allocated=Counter();expected=Counter();prior=Counter()
    for r in rows(old/'staging/province_population_draft.csv'):
        n=int(r['centipersons']);allocated[r['source_pop_id']]+=n
        s,o,c,rel=r['target_state'],r['target_owner'],r['source_culture'],religion[r['source_religion']]
        expected[s,o,migrant.get((c,s),expected_cross[c]),rel]+=n
        prior[s,o,migrant.get((c,s),before[c]),rel]+=n
    assert not (allocated.keys()-source.keys())
    assert all(allocated[pid]==n for pid,n in source.items()), 'Source object lost or duplicated'
    actual=Counter()
    for r in rows(out/'demographics/resident_population_groups.csv'):
        k=tuple(r[f] for f in ('state','owner','culture','religion'))
        assert k not in actual,'Duplicate output population group'
        actual[k]=int(r['centipersons'])
    assert actual==expected, 'Independent source partition mismatch'
    assert collapse(expected)==collapse(prior), 'State, owner, or religion population changed'
    integer={k:n//100 for k,n in expected.items()}
    remainder=(sum(expected.values())+50)//100-sum(integer.values())
    for k in sorted(expected,key=lambda k:(-(expected[k]%100),k))[:remainder]:integer[k]+=1
    parsed=parse_pops(out/'demographics/population_history_preview.txt')
    assert parsed=={k:n for k,n in integer.items() if n}, 'Actual POP text mismatch'
    for rel in ['location_reviews.snapshot.json','population_policy.snapshot.json','staging/province_population_draft.csv']:
        assert digest(out/rel)==digest(old/rel), 'Geometry / review snapshot changed'
    records=load_json(out/'culture_refinement_register.json')
    assets=report['custom_resident_cultures']['cultures']
    assert not any(r['fully_historically_reviewed'] for r in records)
    for r in assets:
        assert not r['aggregate_language'], 'Synthetic catchall language survived'
        assert all('诸族' not in label and 'other peoples' not in label.lower() for label in r['labels'].values()), 'Catchall display label survived'
    for group in old_groups:
        assert len({after[s] for s in group['members']})>1, 'Old catchall was merely renamed'
    for item in plan['partitions']:
        if len(item['members'])>1:
            assert item['status']=='named_composite_gameplay_design' and item['sources'] and item['basis']
    traits=definitions(out/'demographics/identity_assets/common/discrimination_traits')
    groups=definitions(out/'demographics/identity_assets/common/discrimination_trait_groups')
    assert not any(k.startswith('eu5_aggregate_') for k in traits|groups), 'Residual trait remains'
    measured=sum(g['type']=='language' for g in groups.values())
    assert measured==report['culture_budget']['counts']['resident_language_groups'], 'Underreported language groups'
    for source_key in ('ikoot_culture','ijaw','nuristani_culture','hadza_culture','sandawe_culture','willetpoos_culture'):
        entry=next(a for a in assets if a['source']==source_key)
        assert entry['language'].startswith('eu5_reviewed_language_')
    assert not manifest['deployment_ready'] and not manifest['homelands_emitted']
    installation_pointer=root/'.local/m5/installation-latest.json'
    # Integrators may rebase onto a newer verified installation; geography,
    # demographics, reviews and every other protected input must still match.
    assert all(digest(Path(p))==sha for p,sha in manifest['protected_sha256'].items()
        if check_installation or Path(p).resolve()!=installation_pointer.resolve()), 'Live protected input changed'
    catalog_total=sum(int(r['centipersons']) for r in records)
    old_catalog=list(rows(old/'template_fallback/candidate_culture_catalog.csv'))
    assert catalog_total==sum(int(r['centipersons']) for r in old_catalog), 'Template population total changed'
    result={'status':'passed_refinement_candidate_not_installed','removed_catchalls':len(old_groups),
        'affected_source_identities':len(expected_sources),'named_composites':sum(len(g['members'])>1 for g in plan['partitions']),
        'used_cultures_including_template':len(records),'source_population_objects':len(source),
        'zero_population_objects_in_source_ledger':sum(n==0 for n in source.values()),
        'source_world_centipersons':sum(source.values()),'whole_source_people_read_back':sum(parsed.values()),
        'template_people':(catalog_total-sum(source.values()))//100,
        'all_source_objects_fully_allocated':True,'exact_state_owner_religion_conservation':True,
        'political_geometry_unchanged':True,'migrants_unchanged':True,'reviews_unchanged':True,
        'unchanged_source_mappings':sum(after[s]==before[s] for s in before if s not in expected_sources),
        'source_population_groups':len(expected),'source_budget_counts':report['culture_budget']['counts'],
        'candidate_budget_counts':load_json(out/'template_fallback/template_report.json')['candidate_culture_budget']['counts'],
        'fully_historically_reviewed_assets':0,'deployment_ready':False,
        'installation_snapshot_required_to_match':check_installation,
        'output_sha256':{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='independent_refinement_verification.json'}}
    if write_evidence:
        (out/'independent_refinement_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k!='output_sha256'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path)
    print(json.dumps(verify(p.parse_args().run),ensure_ascii=True))
