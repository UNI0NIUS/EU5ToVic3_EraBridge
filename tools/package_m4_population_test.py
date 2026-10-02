"""Build a standalone, reversible M4 test mod on the verified political baseline.

Only writes a fresh workspace package. Installation is a separate verified copy;
this does not certify economic balance, homelands, or runtime acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime
import csv
import json
from pathlib import Path
import shutil
import uuid

from build_m2_prototype import objects
from build_m3_world import block,load_localization
from m3_world import digest,fields,load_json
from pdx_text import root
from verify_m4_culture_assets import validate_culture

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
NAME='EU5 M4 - World 1780 - Culture and Population TEST'
FOLDER='eu5_m4_population_test'
VERSION='0.4.2-test3'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)

def parse_pops(path):
    result={}
    containers=list(objects(root(path.read_text(encoding='utf-8-sig'))))
    if len(containers)!=1 or containers[0][0]!='POPS':raise ValueError('Expected one POPS container')
    for state,obj in objects(containers[0][1]):
        if not state.startswith('s:'):raise ValueError('Invalid pop state')
        for owner,body in objects(obj):
            if not owner.startswith('region_state:'):raise ValueError('Invalid pop owner')
            for op,pop in objects(body):
                if op!='create_pop':raise ValueError('Unexpected pop history operation')
                f=fields(pop);key=(state[2:],owner[len('region_state:'):],f['culture'],f['religion'])
                amount=int(f['size'])
                if amount<=0:raise ValueError('Non-positive output population')
                if key in result:raise ValueError('Duplicate population group')
                result[key]=amount
    return result

def effective(mod,directory):
    files={p.name:p for base in (GAME,mod) for p in sorted((base/directory).glob('*.txt'))}
    result={}
    for p in files.values():
        for k,o in objects(root(p.read_text(encoding='utf-8-sig'))):
            if k in result:raise ValueError('Duplicate effective definition: '+k)
            result[k]=fields(o)
    return result

def verify(package):
    r=load_json(package/'package_report.json');mod=package/FOLDER
    demographic=Path(r['demographic_run']);political=Path(r['political_run'])
    base=load_json(political/'conversion_report.json')
    if digest(political/'conversion_report.json')!=r['political_report_sha256']:raise ValueError('Political baseline changed')
    for path,sha in r['input_sha256'].items():
        if digest(Path(path))!=sha:raise ValueError('Package input changed: '+path)
    actual_paths={p.relative_to(mod).as_posix() for p in mod.rglob('*') if p.is_file()}
    if actual_paths!=set(r['output_sha256']):raise ValueError('Unexpected/missing package files')
    for rel,sha in r['output_sha256'].items():
        if digest(mod/rel)!=sha:raise ValueError('Package output changed: '+rel)
    changed={'.metadata/metadata.json','common/history/pops/00_eu5_world.txt'}
    if r.get('literacy'):
        changed.update(('common/history/population/00_eu5_world.txt','common/on_actions/00_code_on_actions.txt'))
    for rel,sha in base['output_sha256'].items():
        normalized=rel.replace('\\','/')
        if normalized not in changed and digest(mod/normalized)!=sha:raise ValueError('Unrelated political/economic change: '+rel)
    expected={}
    for x in rows(demographic/'demographics/resident_population_groups.csv'):
        n=int(x['preview_integer_persons'])
        if n:expected[x['state'],x['owner'],x['culture'],x['religion']]=n
    for x in rows(demographic/'template_fallback/template_population_groups.csv'):
        key=tuple(x[k] for k in ('state','owner','culture','religion'))
        if key in expected:raise ValueError('Source/template population overlap')
        expected[key]=int(x['persons'])
    popfiles=list((mod/'common/history/pops').glob('*.txt'))
    if len(popfiles)!=1:raise ValueError('Old/template population history still present')
    actual=parse_pops(popfiles[0])
    if actual!=expected:raise ValueError('Installed population history differs from verified ledgers')
    owners=load_json(political/'province_owners.json')
    expected_parts={(s,t) for s,ps in owners.items() for t in ps.values()}
    if {k[:2] for k in actual}!=expected_parts:raise ValueError('A political state part lacks population')
    cultures=effective(mod,'common/cultures');traits=effective(mod,'common/discrimination_traits')
    traitgroups=effective(mod,'common/discrimination_trait_groups');religions=effective(mod,'common/religions')
    locs={lang:{} for lang in ('english','simp_chinese')}
    for lang in locs:
        for directory in (GAME/'localization'/lang,mod/'localization'/lang,mod/'localization/replace'/lang):locs[lang].update(load_localization(directory))
    for culture in {k[2] for k in actual}:validate_culture(culture,cultures[culture],traits,traitgroups,religions,locs)
    if any(k[3] not in religions for k in actual):raise ValueError('Undefined resident religion')
    meta=load_json(mod/'.metadata/metadata.json');original=load_json(Path(base['mod_directory'])/'.metadata/metadata.json')
    if meta['game_custom_data']!=original['game_custom_data']:raise ValueError('History exclusion settings changed')
    if 'common/history/pops' not in meta['game_custom_data']['replace_paths']:raise ValueError('Vanilla population would also load')
    if meta['id']==original['id'] or meta['name']!=NAME:raise ValueError('Test mod identity is not separate')
    for group in ('identity_assets','migrant_assets'):
        asset=demographic/'demographics'/group
        for p in asset.rglob('*'):
            if p.is_file() and digest(mod/p.relative_to(asset))!=digest(p):raise ValueError('Identity asset differs from verified candidate')
    budget=load_json(demographic/'template_fallback/template_report.json')['candidate_culture_budget']
    if len({k[2] for k in actual})>budget['limits']['max_used_cultures']:raise ValueError('Culture budget exceeded')
    totals=Counter()
    for (_,owner,_,_),n in actual.items():totals[owner]+=n
    literacy=None
    if r.get('literacy'):
        from verify_m4_literacy import verify as verify_literacy
        literacy=verify_literacy(package,mod,Path(base['mod_directory']))
    result={'status':'passed','version':r['version'],'mod_name':NAME,'output_files':len(actual_paths),
        'source_and_template_population_match_exactly':True,'old_and_vanilla_population_excluded':True,
        'all_political_state_parts_populated':True,'state_owner_parts':len(expected_parts),
        'political_borders_identity_hre_and_economic_files_unchanged':True,
        'world_integer_persons':sum(actual.values()),'population_groups':len(actual),'used_cultures':len({k[2] for k in actual}),
        'effective_culture_definitions':len(cultures),'used_religions':len({k[3] for k in actual}),
        'country_population':dict(sorted(totals.items())),'runtime_test':'pending','full_conversion_ready':False,
        'literacy':literacy,
        'package_report_sha256':digest(package/'package_report.json')}
    (package/'independent_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def build():
    current=load_json(ROOT/'.local/m4/demographics-latest.json');demographic=Path(current['run'])
    latest=load_json(ROOT/'.local/m3/latest.json');political=Path(latest['run'])
    stage=load_json(demographic/'staging/staging_report.json')
    if Path(stage['political_run']).resolve()!=political.resolve():raise ValueError('Refresh demographics onto latest political baseline first')
    for rel in ('staging/independent_verification.json','demographics/independent_verification.json','template_fallback/independent_verification.json'):
        if load_json(demographic/rel)['status']!='passed':raise ValueError('Unverified demographic candidate')
    if any(current[k] for k in ('pending_geometry_persons','pending_culture_persons','pending_religion_persons')):raise ValueError('Unallocated source population remains')
    d=load_json(demographic/'demographics/demographics_report.json')
    for rel,sha in d['files_sha256'].items():
        if digest(demographic/'demographics'/rel)!=sha:raise ValueError('Demographic asset drift: '+rel)
    base=load_json(political/'conversion_report.json');original=Path(base['mod_directory'])
    if load_json(political/'independent_verification.json')['status']!='passed':raise ValueError('Unverified political baseline')
    package=ROOT/'.local/m4/test-packages'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);package.mkdir(parents=True)
    mod=package/FOLDER;mod.mkdir()
    for rel,sha in base['output_sha256'].items():
        src=original/rel
        if digest(src)!=sha:raise ValueError('Political output drift: '+rel)
        dest=mod/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    popdir=mod/'common/history/pops'
    if {p.name for p in popdir.iterdir()}!={'00_eu5_world.txt'}:raise ValueError('Unexpected baseline pop files')
    popbody=''
    for source in (demographic/'demographics/population_history_preview.txt',demographic/'template_fallback/population_history_preview.txt'):
        f=fields(root(source.read_text(encoding='utf-8-sig')));popbody+=f['POPS'].text()+'\n'
    (popdir/'00_eu5_world.txt').write_text('# Experimental M4: verified resident identities and population; V3 economic templates remain.\n'+block('POPS',popbody),encoding='utf-8-sig')
    for group in ('identity_assets','migrant_assets'):
        assets=demographic/'demographics'/group
        for p in assets.rglob('*'):
            if p.is_file():
                target=mod/p.relative_to(assets)
                if target.exists():raise ValueError('Unexpected identity asset collision')
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    from extract_m4_literacy import extract as extract_literacy
    from m4_literacy import build as build_literacy
    extract_literacy()
    literacy=build_literacy(package,demographic,mod,GAME)
    metadata=load_json(mod/'.metadata/metadata.json')
    metadata.update({'name':NAME,'id':'eu5-personal-m4-population-test','version':VERSION,
        'short_description':'400 cultures, source population and literacy; political '+latest['version']+'. Economic templates remain. New campaign required.'})
    (mod/'.metadata/metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    inputs={str(p):digest(p) for p in (demographic/'demographics/demographics_report.json',demographic/'template_fallback/template_report.json',demographic/'staging/staging_report.json',demographic/'location_reviews.snapshot.json',demographic/'demographics_profile.snapshot.json')}
    inputs.update({str(demographic/rel):digest(demographic/rel) for rel in ('staging/independent_verification.json','demographics/independent_verification.json','template_fallback/independent_verification.json','demographics/resident_population_groups.csv','template_fallback/template_population_groups.csv')})
    r={'schema':1,'status':'experimental_package_not_installed','version':VERSION,'mod_name':NAME,'folder':FOLDER,
        'mod_directory':str(mod),'political_version':latest['version'],'political_run':str(political),'political_report_sha256':digest(political/'conversion_report.json'),
        'demographic_run':str(demographic),'original_installed_mod':latest['installed_mod'],'input_sha256':inputs,
        'output_sha256':{p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()},
        'literacy':literacy,
        'limitations':['Economic buildings, wealth and military initialization remain political-baseline templates; literacy now uses source population weights.',
        'Source occupations, wealth and slavery status are not converted in this identity/population test.',
        'Homelands remain baseline data; custom culture homelands and acceptance balance are unfinished.',
        'No runtime/load/save/performance claim. Requires a new 1836 sandbox campaign; old saves retain their population.',
        'User-deferred x800111 remains unresolved; existing owner still has other provinces.'],
        'full_conversion_ready':False,'runtime_test':'pending','builder_sha256':digest(Path(__file__))}
    (package/'package_report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    verification=verify(package)
    pointer={'package':str(package),'version':VERSION,'status':'verified_test_package_not_installed','used_cultures':verification['used_cultures'],'world_integer_persons':verification['world_integer_persons']}
    (ROOT/'.local/m4/test-package-latest.json').write_text(json.dumps(pointer,ensure_ascii=False,indent=2),encoding='utf-8')
    return pointer

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify',type=Path);a=p.parse_args()
    result=verify(a.verify) if a.verify else build()
    print(json.dumps({k:v for k,v in result.items() if k!='country_population'},ensure_ascii=True))
