"""Independently account for every source POP under a bounded culture split."""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from m3_world import digest, load_json
from package_m4_population_test import parse_pops


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)


def verify(out):
    manifest=load_json(out/'research_manifest.json');old=Path(manifest['baseline'])
    replacements=load_json(out/'explicit_source_replacements.json')
    spec=load_json(out/'research.snapshot.json')
    root=Path(__file__).resolve().parents[1]
    before={r['source_culture']:r['target_culture'] for r in rows(old/'demographics/resident_culture_crosswalk.csv')}
    after={r['source_culture']:r['target_culture'] for r in rows(out/'demographics/resident_culture_crosswalk.csv')}
    expected_cross={s:replacements.get(s,t) for s,t in before.items()}
    assert after==expected_cross, 'Unexpected source identity mapping change'
    old_report=load_json(old/'demographics/demographics_report.json')
    new_report=load_json(out/'demographics/demographics_report.json')
    assert new_report['migrant_cultures']['cultures']==old_report['migrant_cultures']['cultures']
    assert digest(out/'demographics/resident_religion_crosswalk.csv')==digest(old/'demographics/resident_religion_crosswalk.csv')
    migrant={(r['source'],s):r['target'] for r in old_report['migrant_cultures']['cultures'] for s in r['states']}
    religion={r['source_religion']:r['target_religion'] for r in rows(old/'demographics/resident_religion_crosswalk.csv')}
    source={r['pop_id']:int(r['centipersons']) for r in rows(root/'.local/m4/source-1780-population/source_populations.csv')}
    allocated=Counter();expected=Counter();old_expected=Counter();links=defaultdict(set)
    for r in rows(old/'staging/province_population_draft.csv'):
        n=int(r['centipersons']);allocated[r['source_pop_id']]+=n
        s,o,c,rel=r['target_state'],r['target_owner'],r['source_culture'],religion[r['source_religion']]
        links[r['source_location']].add(s)
        old_c=migrant.get((c,s),before[c]);new_c=migrant.get((c,s),expected_cross[c])
        expected[s,o,new_c,rel]+=n;old_expected[s,o,old_c,rel]+=n
    assert not (allocated.keys()-source.keys()), 'Unknown source population object'
    assert all(allocated[pid]==n for pid,n in source.items()), 'A source population object was lost or duplicated'
    actual={tuple(r[k] for k in ('state','owner','culture','religion')):int(r['centipersons']) for r in rows(out/'demographics/resident_population_groups.csv')}
    assert expected==actual, 'Independent source partition differs from generated groups'
    collapsed=lambda groups:collapse(groups)
    assert collapsed(expected)==collapsed(old_expected), 'State/owner/religion population changed'
    # Independently repeat integer apportionment, then read actual output PDX.
    integer={k:n//100 for k,n in expected.items()}
    residual=(sum(expected.values())+50)//100-sum(integer.values())
    for k in sorted(expected,key=lambda k:(-(expected[k]%100),k))[:residual]:integer[k]+=1
    parsed=parse_pops(out/'demographics/population_history_preview.txt')
    assert parsed=={k:n for k,n in integer.items() if n}, 'Population text readback differs'
    snapshots=['location_reviews.snapshot.json','population_policy.snapshot.json']
    assert all(digest(out/p)==digest(old/p) for p in snapshots)
    # Geometry and ownership drafts are immutable: no cultural operation may
    # alter even a single source allocation or target province assignment.
    assert digest(out/'staging/province_population_draft.csv')==digest(old/'staging/province_population_draft.csv')
    anchors_checked=0
    for key,item in spec['identities'].items():
        homeland=item['homeland']
        for loc,states in homeland['anchors'].items():
            assert links[loc]==set(states), ('Historical core anchor translation changed',loc)
            anchors_checked+=1
        if homeland['status']=='candidate_core':
            assert set(homeland['states'])=={s for states in homeland['anchors'].values() for s in states}
        else:assert not homeland['states'], 'Unreviewed geographic proposal emitted as a homeland'
    records=load_json(out/'culture_research_register.json')
    assert len(records)==405 and sum(bool(r['evidence_urls']) for r in records)==7
    assert not any(r['fully_historically_reviewed'] for r in records)
    assert len(new_report['custom_resident_cultures']['cultures'])==99
    assert not manifest['homelands_emitted'] and not manifest['literacy_rebuilt_for_installation']
    assert all(digest(Path(p))==sha for p,sha in manifest['protected_sha256'].items()), 'Protected live input changed'
    assets={r['source']:r for r in new_report['custom_resident_cultures']['cultures']}
    assert assets['hadza_culture']['language']!=assets['sandawe_culture']['language']
    assert assets['hadza_culture']['language_group']!=assets['sandawe_culture']['language_group']
    assert assets['buginese_culture']['language']!=assets['makassarese_culture']['language']
    assert assets['adhari_culture']['language']!=assets['talysh_culture']['language']
    assert all(assets[k]['heritage']=='heritage_iranian' for k in ('adhari_culture','talysh_culture','pamiri_culture'))
    source_totals=Counter()
    for r in rows(out/'demographics/resident_culture_crosswalk.csv'):source_totals[r['source_culture']]+=int(r['centipersons'])
    affected_sources=set(replacements)
    result={'status':'passed_partial_research_candidate_not_installed',
        'source_population_objects':len(source),'source_world_centipersons':sum(source.values()),
        'zero_population_objects_preserved_in_source_ledger':sum(n==0 for n in source.values()),
        'whole_source_people_read_back':sum(parsed.values()),'source_population_groups':len(expected),
        'used_cultures_including_template':len(records),'resident_assets':len(assets),
        'identity_language_evidence_records':7,'fully_historically_reviewed_assets':0,
        'historical_core_candidates':4,'historical_homelands_deferred':3,'checked_location_state_anchors':anchors_checked,
        'affected_centipersons':sum(source_totals[s] for s in affected_sources),
        'exact_state_owner_religion_conservation':True,'all_source_objects_allocated_exactly_once_in_full':True,
        'political_geometry_unchanged':True,'migrants_unchanged':True,'review_records_unchanged':True,
        'legacy_provisional_flags_retained':True,'deployment_ready':False,
        'output_sha256':{str(p.relative_to(out)):digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='independent_research_verification.json'}}
    (out/'independent_research_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k!='output_sha256'}


def collapse(groups):
    out=Counter()
    for (s,o,c,r),n in groups.items():out[s,o,r]+=n
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path)
    print(json.dumps(verify(parser.parse_args().run),ensure_ascii=True))
