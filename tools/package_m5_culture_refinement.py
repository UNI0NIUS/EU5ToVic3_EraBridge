"""Integrate the reviewed classification candidate onto the installed M5 package.

Only a new workspace package is written; installation uses the separately
guarded updater. Unresearched homelands are explicitly deferred.
"""
import argparse
import colorsys
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import numpy as np

from build_m2_prototype import objects, strings, patch, replace_body
from build_m3_world import block, entry, load_localization
from m3_world import digest
from pdx_text import root, Object
from package_m4_population_test import parse_pops, effective, rows
from verify_m4_culture_assets import validate_culture
from m5_culture_geography import COLOR, read_color, lab, majority
from m4_literacy import build as build_literacy, POPULATION_PATH, CODE_PATH, HOOK, EFFECT_PATH
from verify_m4_literacy import verify as verify_literacy
from verify_m5_culture_refinement import verify as verify_candidate

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
STATE='common/history/states/00_eu5_world.txt'
POPS='common/history/pops/00_eu5_world.txt'
RESIDENT='common/cultures/zz_eu5_resident_cultures.txt'
HOMELAND=re.compile(r'\badd_homeland\s*=\s*cu:([a-z0-9_]+)')
ALLOWED={'.metadata/metadata.json',RESIDENT,STATE,POPS,POPULATION_PATH,CODE_PATH,EFFECT_PATH,
    'common/on_actions/zz_eu5_m4_literacy.txt',
    'common/discrimination_traits/zz_eu5_resident_cultures.txt',
    'common/discrimination_trait_groups/zz_eu5_resident_languages.txt',
    'localization/english/eu5_resident_cultures_l_english.yml',
    'localization/simp_chinese/eu5_resident_cultures_l_simp_chinese.yml'}

def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def files(mod):return {p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}

def strip_imported_literacy(text):
    countries=[]
    for scope,obj in objects(root(text).fields()['POPULATION']):
        countries.append(block(scope,''.join(entry(k,v) for k,v in obj.entries() if not k.startswith('eu5_m4_literacy_'))))
    return block('POPULATION',''.join(countries))

def strip_imported_hook(text):
    hook=root(text).fields()['on_game_started'].fields()['on_actions']
    if strings(hook).count(HOOK)!=1:raise ValueError('Expected exactly one installed literacy hook')
    return patch(text,[replace_body(hook,re.sub(r'\b'+HOOK+r'\b','',hook.text()))])

def homeland_pairs(text):
    return {(s.removeprefix('s:'),c) for s,o in objects(root(text).fields()['STATES']) for c in HOMELAND.findall(o.text())}

def non_homeland_states(text):
    return {s:[(k,v.text().strip() if isinstance(v,Object) else v) for k,v in o.entries() if k!='add_homeland']
        for s,o in objects(root(text).fields()['STATES'])}

def colors(mod,source,demographic):
    prior=effective(source,'common/cultures')
    current=effective(mod,'common/cultures')
    resident={c:o for c,o in objects(root((mod/RESIDENT).read_text(encoding='utf-8-sig')))}
    inventory=read(demographic/'refinement_policy.snapshot.json')
    changed={g['target'] for g in inventory['partitions'] if g['target'].startswith('eu5_resident_')}
    original={c:read_color(o.text()) for p in (source/'common/cultures').glob('*.txt') for c,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    existing={}
    for base in (GAME,mod):
        for p in (base/'common/cultures').glob('*.txt'):
            for c,o in objects(root(p.read_text(encoding='utf-8-sig'))):
                if c not in changed:existing[c]=original.get(c,read_color(o.text()))
    totals={r['culture']:int(r['centipersons']) for r in rows(demographic/'template_fallback/candidate_culture_catalog.csv')}
    candidates=np.array([colorsys.hsv_to_rgb(h/192,s,v) for h in range(192) for s in (.35,.48,.61,.74,.87,1) for v in (.42,.54,.66,.78,.90,1)])
    labs=lab(candidates);occupied=lab(list(existing.values()))
    distance=np.full(len(candidates),np.inf)
    for point in occupied:distance=np.minimum(distance,np.linalg.norm(labs-point,axis=1))
    audit={};assigned={}
    for c in sorted(changed,key=lambda c:(-totals.get(c,0),c)):
        pref=read_color(resident[c].text());valid=distance>=8.002
        if not valid.any():raise ValueError('Color separation exhausted; no silent relaxation')
        score=np.where(valid,-np.linalg.norm(labs-lab(pref),axis=1),-np.inf)
        i=int(score.argmax());rgb=[round(float(v),5) for v in candidates[i]];point=lab(rgb)
        audit[c]={'rgb':rgb,'minimum_delta_e_at_assignment':float(distance[i]),'basis':'display distinction only'}
        assigned[c]=rgb;distance=np.minimum(distance,np.linalg.norm(labs-point,axis=1))
    text=(mod/RESIDENT).read_text(encoding='utf-8-sig');edits=[]
    for c,o in objects(root(text)):
        rgb=assigned.get(c,original.get(c))
        if rgb is None:raise ValueError('Unaccounted resident color')
        body,n=COLOR.subn('color = { '+' '.join(f'{v:.5f}' for v in rgb)+' }',o.text());assert n==1
        edits.append(replace_body(o,body))
    (mod/RESIDENT).write_text(patch(text,edits),encoding='utf-8-sig')
    return audit

def homelands(mod,source,demographic):
    plan=read(demographic/'refinement_policy.snapshot.json');research=read(demographic/'research.snapshot.json')
    old_keys={'eu5_resident_'+g['representative'] for g in plan['old_catchalls']}
    d=read(demographic/'demographics/demographics_report.json')
    migrant={r['target'] for r in d['migrant_cultures']['cultures']}
    pop=parse_pops(mod/POPS);counts=Counter();total=Counter()
    for (s,o,c,r),n in pop.items():counts[s,c]+=n;total[s]+=n
    additions=set();evidence=[]
    for (s,c),n in counts.items():
        if c in migrant and majority(n,total[s]):
            additions.add((s,c));evidence.append({'state':s,'culture':c,'basis':'strict_whole_state_majority','persons':n,'whole_state_persons':total[s]})
    links=defaultdict(set)
    for r in rows(demographic/'staging/province_population_draft.csv'):links[r['source_location']].add(r['target_state'])
    for source_key,item in research['identities'].items():
        h=item['homeland']
        if h['status']!='candidate_core':continue
        for location,states in h['anchors'].items():assert links[location]==set(states)
        for s in h['states']:
            c='eu5_resident_'+source_key;additions.add((s,c))
            evidence.append({'state':s,'culture':c,'basis':'historically_documented_core','detail':h,
                'sources':[research['sources'][k]['url'] for k in item['sources']]})
    oldtext=(source/STATE).read_text(encoding='utf-8-sig');oldpairs=homeland_pairs(oldtext)
    removed={p for p in oldpairs if p[1] in old_keys|migrant}
    expected=(oldpairs-removed)|additions
    edits=[]
    for scope,o in objects(root(oldtext).fields()['STATES']):
        s=scope.removeprefix('s:')
        body=HOMELAND.sub(lambda m:'' if m[1] in old_keys|migrant else m[0],o.text())
        existing=set(HOMELAND.findall(body))
        body+=''.join('\nadd_homeland = cu:'+c+'\n' for state,c in sorted(additions) if state==s and c not in existing)
        edits.append(replace_body(o,body))
    output=patch(oldtext,edits);(mod/STATE).write_text(output,encoding='utf-8-sig')
    assert homeland_pairs(output)==expected
    targets={g['target'] for g in plan['partitions'] if g['target'].startswith('eu5_resident_')}
    deferred=sorted(targets-{c for s,c in expected})
    return {'policy':'Preserve unaffected homelands; remove old residual-category claims; only documented historical cores for changed identities. Migrants require strictly over half of whole state.',
        'removed_legacy_pairs':sorted(removed),'added_pairs':sorted(additions),'expected_pairs':sorted(expected),
        'evidence':evidence,'deferred_changed_cultures':deferred,'all_historical_assets_reviewed':False}

def verify(package):
    report=read(package/'package_report.json');mod=Path(report['mod_directory']);base=Path(report['prior_package'])
    prior=read(base/'package_report.json');source=Path(prior['mod_directory']);d=Path(report['demographic_run'])
    assert files(mod)==report['output_sha256']
    for p,sha in report['input_sha256'].items():assert digest(Path(p))==sha,p
    assert set(report['output_sha256'])==set(prior['output_sha256']), 'Unexpected added or removed file'
    changed={p for p,sha in prior['output_sha256'].items() if digest(mod/p)!=sha}
    assert changed<=ALLOWED and sorted(changed)==report['changed_files']
    expected={}
    for r in rows(d/'demographics/resident_population_groups.csv'):
        n=int(r['preview_integer_persons'])
        if n:expected[tuple(r[k] for k in ('state','owner','culture','religion'))]=n
    for r in rows(d/'template_fallback/template_population_groups.csv'):
        key=tuple(r[k] for k in ('state','owner','culture','religion'));assert key not in expected
        expected[key]=int(r['persons'])
    actual=parse_pops(mod/POPS);assert actual==expected
    assert sum(actual.values())==sum(parse_pops(source/POPS).values())
    assert {k[:2] for k in actual}=={k[:2] for k in parse_pops(source/POPS)}
    cultures=effective(mod,'common/cultures');traits=effective(mod,'common/discrimination_traits')
    groups=effective(mod,'common/discrimination_trait_groups');religions=effective(mod,'common/religions')
    locs={lang:{} for lang in ('english','simp_chinese')}
    for lang in locs:
        for directory in (GAME/'localization'/lang,mod/'localization'/lang,mod/'localization/replace'/lang):locs[lang].update(load_localization(directory))
    for c in {k[2] for k in actual}:validate_culture(c,cultures[c],traits,groups,religions,locs)
    assert all(k[3] in religions for k in actual)
    assert not any(k.startswith('eu5_aggregate_') for k in traits|groups)
    for p in mod.rglob('*.txt'):
        # Exact tokens: skip discrimination-trait identifiers sharing the prefix.
        for token in re.findall(r'\beu5_resident_[a-z0-9_]+\b',p.read_text(encoding='utf-8-sig')):
            if token.startswith(('eu5_resident_heritage_','eu5_resident_language_')):continue
            assert token in cultures,('Stale culture reference',str(p),token)
    for category in ('identity_assets','migrant_assets'):
        for p in (d/'demographics'/category).rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(d/'demographics'/category).as_posix()
            if rel=='common/cultures/zz_eu5_migrant_cultures.txt':
                assert digest(mod/rel)==digest(source/rel) # keep installed colors
            elif rel==RESIDENT:
                a={k:COLOR.sub('',o.text()).strip() for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
                b={k:COLOR.sub('',o.text()).strip() for k,o in objects(root((mod/rel).read_text(encoding='utf-8-sig')))}
                assert a==b
            else:assert digest(mod/rel)==digest(p),rel
    geo=read(package/'culture_refinement_geography.json')
    before=(source/STATE).read_text(encoding='utf-8-sig');after=(mod/STATE).read_text(encoding='utf-8-sig')
    assert non_homeland_states(before)==non_homeland_states(after),'Political state structure changed'
    assert homeland_pairs(after)=={tuple(p) for p in geo['homelands']['expected_pairs']}
    migrant={r['target'] for r in read(d/'demographics/demographics_report.json')['migrant_cultures']['cultures']}
    counts=Counter();totals=Counter()
    for (s,o,c,r),n in actual.items():counts[s,c]+=n;totals[s]+=n
    assert {(s,c) for (s,c),n in counts.items() if c in migrant and n*2>totals[s]}=={(s,c) for s,c in homeland_pairs(after) if c in migrant}
    rgb={c:read_color(o.text()) for basepath in (GAME,mod) for p in (basepath/'common/cultures').glob('*.txt') for c,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    new=geo['colors'];minimum=float('inf')
    for c,rec in new.items():
        assert rgb[c]==rec['rgb']
        delta=float(np.linalg.norm(lab([v for k,v in rgb.items() if k!=c])-lab(rgb[c]),axis=1).min())
        assert delta>=8,('Colors too similar',c,delta)
        minimum=min(minimum,delta)
    # Prove temporary hook normalization removed only our imported operations.
    normalized=package/'literacy_base'
    assert (normalized/POPULATION_PATH).read_text(encoding='utf-8-sig')==strip_imported_literacy((source/POPULATION_PATH).read_text(encoding='utf-8-sig'))
    assert (normalized/CODE_PATH).read_text(encoding='utf-8-sig')==strip_imported_hook((source/CODE_PATH).read_text(encoding='utf-8-sig'))
    literacy=verify_literacy(package,mod,normalized)
    assert strings(root((mod/CODE_PATH).read_text(encoding='utf-8-sig')).fields()['on_game_started'].fields()['on_actions']).count(HOOK)==1
    oldmeta=read(source/'.metadata/metadata.json');meta=read(mod/'.metadata/metadata.json')
    for k in ('id','name','game_custom_data','supported_game_version'):assert meta[k]==oldmeta[k]
    result={'status':'passed_static_runtime_pending','literacy':literacy,
        'culture_refinement':{'status':'passed','source_and_template_population_exact':True,
            'all_culture_references_resolved':True,'political_economy_flags_unchanged':True,
            'state_non_homeland_structure_unchanged':True,'migrant_strict_majority_verified':True,
            'world_integer_persons':sum(actual.values()),'nonzero_population_groups':len(actual),
            'nonzero_population_cultures':len({k[2] for k in actual}),'effective_culture_definitions':len(cultures),
            'recolored_cultures':len(new),'minimum_color_delta_e':minimum,
            'historical_homelands_deferred':len(geo['homelands']['deferred_changed_cultures']),
            'fully_historically_reviewed':False,'runtime_verified':False},
        'changed_files':sorted(changed),'package_report_sha256':digest(package/'package_report.json')}
    write(package/'verification.json',result)
    return result

def build():
    installation=read(ROOT/'.local/m5/installation-latest.json');base=Path(installation['package'])
    prior=read(base/'package_report.json');source=Path(prior['mod_directory'])
    assert files(source)==prior['output_sha256']
    assert files(Path(installation['target']))==prior['output_sha256'],'Installed files diverged'
    demographic=Path(read(ROOT/'.local/m5/culture-refinement-latest.json')['run'])
    candidate_check=verify_candidate(demographic,check_installation=False,write_evidence=False)
    out=ROOT/'.local/economy/packages'/('m5-culture-refinement-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(source,mod)
    write(out/'candidate_population_verification.json',candidate_check)
    for category in ('identity_assets','migrant_assets'):
        assets=demographic/'demographics'/category
        for p in assets.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(assets)
            if rel.as_posix()=='common/cultures/zz_eu5_migrant_cultures.txt':continue
            assert (mod/rel).is_file(),'New asset file requires a separate install policy'
            shutil.copy2(p,mod/rel)
    text='\n'.join(root((demographic/rel).read_text(encoding='utf-8-sig')).fields()['POPS'].text() for rel in ('demographics/population_history_preview.txt','template_fallback/population_history_preview.txt'))
    (mod/POPS).write_text(block('POPS',text),encoding='utf-8-sig')
    color_audit=colors(mod,source,demographic)
    geography=homelands(mod,source,demographic)
    write(out/'culture_refinement_geography.json',{'colors':color_audit,'homelands':geography})
    for rel,clean in ((POPULATION_PATH,strip_imported_literacy),(CODE_PATH,strip_imported_hook)):
        text=clean((source/rel).read_text(encoding='utf-8-sig'))
        path=out/'literacy_base'/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig')
        (mod/rel).write_text(text,encoding='utf-8-sig')
    build_literacy(out,demographic,mod,GAME)
    meta=read(mod/'.metadata/metadata.json')
    version=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',meta['version'])
    if not version:raise ValueError('Unexpected installed M5 version format')
    meta['version']=f'0.5.{int(version[1])+1}-m5-test{int(version[2])+1}'
    meta['short_description']='M5 culture refinement: 590 categories, rebuilt source literacy and colors. Documented homeland cores only for changed cultures; further historical review pending. New campaign required.'
    write(mod/'.metadata/metadata.json',meta)
    hashes=files(mod);changed=sorted(k for k,v in hashes.items() if v!=prior['output_sha256'].get(k))
    inputs=[base/'package_report.json',demographic/'independent_refinement_verification.json',
        demographic/'refinement_policy.snapshot.json',demographic/'research.snapshot.json',
        demographic/'demographics/independent_verification.json',out/'culture_refinement_geography.json',
        out/'literacy_base'/POPULATION_PATH,out/'literacy_base'/CODE_PATH,
        out/'candidate_population_verification.json',ROOT/'tools/verify_m5_culture_refinement.py',Path(__file__)]
    report={'status':'culture_refinement_static_candidate','update_scope':'m5_culture_refinement',
        'version':meta['version'],'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(base),
        'demographic_run':str(demographic),'political_run':prior['political_run'],
        'new_campaign_required':True,'full_conversion_ready':False,'changed_files':changed,
        'input_sha256':{str(p):digest(p) for p in inputs},'output_sha256':hashes}
    write(out/'package_report.json',report)
    result=verify(out)
    write(ROOT/'.local/m5/culture-refinement-package-latest.json',{'package':str(out),'version':meta['version'],'status':result['status']})
    print(json.dumps({'package':str(out),'version':meta['version'],**result['culture_refinement']},ensure_ascii=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify',type=Path);args=parser.parse_args()
    if args.verify:print(json.dumps(verify(args.verify),ensure_ascii=True))
    else:build()
