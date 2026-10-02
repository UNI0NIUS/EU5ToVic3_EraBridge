"""Promote reviewed tribal geography onto the latest M5 without reverting modules.

Reallocate existing integer population by exact source province weights, preserve
the immutable original-population variant, and rebuild source literacy selectors.
All changes are built in a fresh workspace package before guarded installation.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
from pathlib import Path
import re
import shutil

from build_m2_prototype import objects, strings, patch, replace_body, state_owners, whole_entry
from build_m3_world import block, entry
from economy_model import apportioned, Target, building_rows, definitions
from package_m4_population_test import parse_pops, rows, effective
from package_m5_economic_modules import ROOT, GAME, read, write, files, canonical
from package_m5_population_options import original_population_package, apply_mode
from package_m5_population_calibration import find_ancestor
from package_m5_culture_refinement import strip_imported_literacy, strip_imported_hook
from m3_world import digest
from m4_literacy import build as build_literacy, EFFECT_PATH, HOOK_PATH, CODE_PATH, POPULATION_PATH
from pdx_text import root, Object

STATE='common/history/states/00_eu5_world.txt'
POPS='common/history/pops/00_eu5_world.txt'
COUNTRIES='common/history/countries/00_eu5_world.txt'
BUILDINGS='common/history/buildings/00_eu5_world.txt'
MILITARY='common/history/military_formations/00_eu5_world.txt'
DEFS='common/country_definitions/zz_eu5_world.txt'
FLAGS='common/flag_definitions/zz_eu5_world.txt'
COAS='common/coat_of_arms/coat_of_arms/zz_eu5_world.txt'
DIPLOMACY='common/history/diplomacy/00_eu5_subjects.txt'
ALLOWED={'.metadata/metadata.json',STATE,POPS,COUNTRIES,DEFS,FLAGS,COAS,
         EFFECT_PATH,HOOK_PATH,CODE_PATH,POPULATION_PATH,DIPLOMACY,
         'localization/english/eu5_world_l_english.yml',
         'localization/simp_chinese/eu5_world_l_simp_chinese.yml',
         'localization/replace/english/eu5_world_l_english.yml',
         'localization/replace/simp_chinese/eu5_world_l_simp_chinese.yml'}


def text(p):return Path(p).read_text(encoding='utf-8-sig')
def put(p,s):Path(p).write_text(s,encoding='utf-8-sig')
def container(p,key):return dict(objects(root(text(p)).fields()[key]))


def inherited_report(package):
    """Identity-only packages may omit unchanged demographic provenance."""
    latest=read(package/'package_report.json');result=dict(latest);cursor=latest
    keys={'political_run','demographic_run','population_mode','population_calibrated','source_population_conserved'}
    while keys-set(result):
        if not cursor.get('prior_package'):raise ValueError('Missing integrated provenance: '+str(keys-set(result)))
        cursor=read(Path(cursor['prior_package'])/'package_report.json')
        assert cursor['output_sha256'][POPS]==latest['output_sha256'][POPS],'Untracked demographic change'
        for k in keys-set(result):
            if k in cursor:result[k]=cursor[k]
    return result


def split_groups(groups, weights):
    """Conserve each old state/owner/identity integer count, including rounding."""
    result=Counter()
    for k,n in sorted(groups.items()):
        if k not in weights:
            result[k]+=n
            continue
        for owner,amount in apportioned(weights[k],n).items():
            if amount:result[k[0],owner,k[2],k[3]]+=amount
    assert sum(groups.values())==sum(result.values())
    before=Counter();after=Counter()
    for (s,t,c,r),n in groups.items():before[s,c,r]+=n
    for (s,t,c,r),n in result.items():after[s,c,r]+=n
    assert before==after
    return dict(result)


def render_pops(groups):
    states=defaultdict(lambda:defaultdict(list))
    for (s,t,c,r),n in sorted(groups.items()):
        if n:states[s][t].append(block('create_pop',f'culture = {c}\nreligion = {r}\nsize = {n}'))
    return block('POPS',''.join(block('s:'+s,''.join(block('region_state:'+t,''.join(parts)) for t,parts in owners.items())) for s,owners in states.items()))


def append_selected(mod,candidate,rel,selected,rewrites=None):
    current=text(mod/rel);known=root(current).fields()
    additions=[]
    for k,o in objects(root(text(candidate/rel))):
        if k not in selected:continue
        assert k not in known,'Definition collision: '+k
        body=o.text()
        if rewrites and k in rewrites:
            body,count=re.subn(r'cultures\s*=\s*\{[^}]*\}', 'cultures = { '+rewrites[k]+' }',body)
            assert count==1
        additions.append(block(k,body))
    assert len(additions)==len(selected),(rel,selected)
    put(mod/rel,current+'\n'+''.join(additions))


def promote_states(base,mod,newowners,newtags):
    raw=text(base/STATE);edits=[]
    for scope,o in objects(root(raw).fields()['STATES']):
        s=scope[2:];old={p.upper():t for p,t in state_owners(o,strict=False).items()}
        desired={p.upper():t for p,t in newowners[s].items()}
        if old==desired:continue
        templates={v.fields()['country'][2:]:v for k,v in o.entries() if k=='create_state'}
        owners=defaultdict(list)
        for p,t in sorted(newowners[s].items()):owners[t].append(p)
        output=[]
        for t,provinces in sorted(owners.items()):
            if t in templates:
                body=templates[t].text()
                body,count=re.subn(r'owned_provinces\s*=\s*\{[^}]*\}', 'owned_provinces = { '+' '.join(provinces)+' }',body);assert count==1
            else:
                assert t in newtags
                body=f'country = c:{t}\nowned_provinces = {{ '+ ' '.join(provinces)+' }\nstate_type = unincorporated\n'
            output.append(block('create_state',body))
        # Historical and migrant homelands are state-wide: population identities
        # and state totals do not change, so preserve every reviewed homeland.
        output.extend(entry(k,v) for k,v in o.entries() if k!='create_state')
        edits.append(replace_body(o,''.join(output)))
    put(mod/STATE,patch(raw,edits))


def terrain_assignments(empty,new,owners,mapping,locations,uninhabitable,edges):
    adjacent=defaultdict(set)
    for a,b in edges:adjacent[a].add(b);adjacent[b].add(a)
    flat={p:t for ps in owners.values() for p,t in ps.items()};changes=[]
    for s,ps in owners.items():
        for p,t in ps.items():
            if t not in empty:continue
            names=mapping.get(p,[])
            if not names or not all(n in uninhabitable and str(locations[n]['owner'])=='0' for n in names):
                raise ValueError('Empty fallback includes unresolved or owned land')
            neighbors={flat[q] for q in adjacent[p] if q in flat and flat[q] in new}
            if len(neighbors)!=1:raise ValueError('Ambiguous terrain inheritance')
            changes.append({'state':s,'province':p,'from':t,'to':neighbors.pop(),'source_locations':names,'reason':'unowned_uninhabitable_terrain_of_empty_vanilla_fallback_next_to_unique_new_tribe'})
    return changes


def absorb_empty_terrain(report,owners,candidate):
    """Remove empty vanilla remnants only with explicit unownable source terrain
    and one adjacent new tribe. Never attach unknown or source-owned land.
    """
    totals=Counter()
    for r in rows(candidate/'population-staging/province_population_draft.csv'):totals[r['target_owner']]+=int(r['centipersons'])
    empty={t for t,c in report['countries'].items() if c['source_id'] is None and not c.get('generated_uncolonized') and not totals[t]}
    # Template-only populations (for example Acre) remain meaningful residents.
    installed=read(ROOT/'.local/m5/installation-latest.json');prior=inherited_report(Path(installed['package']))
    for r in rows(Path(prior['demographic_run'])/'template_fallback/template_population_groups.csv'):
        if int(r['persons']):empty.discard(r['owner'])
    if not empty:return [],set()
    from m3_world import World
    w=World(GAME,Path('D:/Steam/steamapps/common/Europa Universalis V/game'),read(ROOT/'.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json'),read(ROOT/'.local/m3/politics-with-cultures.json'),read(ROOT/'config/personal/m3_world.json'),ROOT/'.local/m3/cache')
    from m3_uncolonized import province_land_edges
    w.owners=owners
    changes=terrain_assignments(empty,set(report['uncolonized_tribes']['countries']),owners,w.mapping,w.locations,w.uninhabitable,
                               province_land_edges(w,ROOT/'.local/m3/cache/tribal_land_edges.json'))
    for r in changes:owners[r['state']][r['province']]=r['to']
    assert not empty & {t for ps in owners.values() for t in ps.values()}
    for t in empty:del report['countries'][t]
    report['vanilla_fallback_subjects']=[e for e in report['vanilla_fallback_subjects'] if not {e['target_subject'],e['target_overlord']}&empty]
    report['empty_terrain_attachments']=changes
    return changes,empty


def build(candidate,output):
    install=read(ROOT/'.local/m5/installation-latest.json')
    assert install==read(ROOT/'.local/economy/installation-latest.json')
    prior=Path(install['package']);previous=inherited_report(prior);base=Path(previous['mod_directory'])
    baseline=files(base);assert baseline==previous['output_sha256']==files(Path(install['target']))
    report=read(candidate/'conversion_report.json');tribes=report['uncolonized_tribes'];tags=set(tribes['countries'])
    assert read(candidate/'independent_verification.json')['uncolonized_connected_components_verified']
    assert read(candidate/'population-staging/independent_verification.json')['geographic_owners_match']
    for p,h in tribes['input_sha256'].items():assert digest(p)==h,p
    for p,h in report['output_sha256'].items():assert digest(Path(report['mod_directory'])/p)==h,p
    stage_report=read(candidate/'population-staging/staging_report.json')
    for p,h in stage_report['files_sha256'].items():assert digest(candidate/'population-staging'/p)==h,p
    oldowners=read(Path(previous['political_run'])/'province_owners.json');newowners=read(candidate/'province_owners.json')
    expected={(r['state'],r['province'],r['from'],r['to']) for r in tribes['transfers']}
    actual={(s,p,t,newowners[s][p]) for s,ps in oldowners.items() for p,t in ps.items() if newowners[s][p]!=t}
    assert actual==expected
    terrain,retired=absorb_empty_terrain(report,newowners,candidate)
    output.mkdir(parents=True,exist_ok=False);mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    political=output/'political';political.mkdir();write(political/'province_owners.json',newowners)
    demographic=output/'demographic';old_dem=Path(previous['demographic_run'])
    for directory in ('demographics','template_fallback'):shutil.copytree(old_dem/directory,demographic/directory)
    shutil.copytree(candidate/'population-staging',demographic/'staging')
    dr=read(old_dem/'demographics/demographics_report.json')
    cultures={r['source_culture']:r['target_culture'] for r in rows(old_dem/'demographics/resident_culture_crosswalk.csv')}
    religions={r['source_religion']:r['target_religion'] for r in rows(old_dem/'demographics/resident_religion_crosswalk.csv')}
    migrants={(r['source'],s):r['target'] for r in dr['migrant_cultures']['cultures'] for s in r['states']}
    weights=defaultdict(Counter);source_groups=Counter();classes=Counter()
    for r in rows(demographic/'staging/province_population_draft.csv'):
        s,p,t=r['target_state'],r['target_province'],r['target_owner'];n=int(r['centipersons'])
        assert newowners[s][p]==t
        c=migrants.get((r['source_culture'],s),cultures[r['source_culture']]);faith=religions[r['source_religion']]
        weights[s,oldowners[s][p],c,faith][t]+=n
        source_groups[s,t,c,faith]+=n;classes[s,t,r['source_class']]+=n
    old_source={tuple(r[k] for k in ('state','owner','culture','religion')):int(r['centipersons']) for r in rows(old_dem/'demographics/resident_population_groups.csv')}
    assert {k:sum(v.values()) for k,v in weights.items()}==old_source,'Existing demographic identities/geography changed'
    original_path=original_population_package(prior);original=split_groups(parse_pops(original_path),weights)
    current=split_groups(parse_pops(base/POPS),weights)
    put(output/'original_population.txt',render_pops(original));put(mod/POPS,render_pops(current))
    with (demographic/'demographics/resident_population_groups.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        w=csv.writer(stream);w.writerow(['state','owner','culture','religion','centipersons','preview_integer_persons'])
        w.writerows([*k,n,original.get(k,0)] for k,n in sorted(source_groups.items()))
    dr.update(stage=str(demographic/'staging'),stage_report_sha256=digest(demographic/'staging/staging_report.json'),
              ownership_rebase_from=str(old_dem),ownership_rebase_candidate=str(candidate))
    write(demographic/'demographics/demographics_report.json',dr)
    # Archived demographic validations describe the old ownership; do not ship
    # them as validations of the rebased ledger.
    for name in ('independent_verification.json','population_history_preview.txt'):
        path=demographic/'demographics'/name
        if path.exists():path.unlink()
    put(demographic/'demographics/population_history_preview.txt',render_pops({k:original.get(k,0) for k in source_groups}))
    primary={}
    for t,country in tribes['countries'].items():
        choices=Counter()
        for (s,owner,c,r),n in source_groups.items():
            if owner==t:choices[c]+=n
        assert choices and sum(choices.values())>0
        primary[t]=min(choices,key=lambda c:(-choices[c],c))
        report['countries'][t]['culture']=primary[t];report['countries'][t]['cultures']=[primary[t]]
    promote_states(base,mod,newowners,tags)
    cm=Path(report['mod_directory'])
    append_selected(mod,cm,DEFS,tags,primary)
    append_selected(mod,cm,FLAGS,tags)
    append_selected(mod,cm,COAS,{'eu5_uncolonized_'+t for t in tags})
    for rel,key in ((COUNTRIES,'COUNTRIES'),(POPULATION_PATH,'POPULATION')):
        raw=text(mod/rel);obj=root(raw).fields()[key]
        raw=patch(raw,[(*whole_entry(k,v),'') for k,v in objects(obj) if k[2:] in retired])
        obj=root(raw).fields()[key]
        addition=''.join(block('c:'+t+(' ?' if key=='COUNTRIES' else ''),container(cm/rel,key)['c:'+t].text()) for t in sorted(tags))
        put(mod/rel,patch(raw,[replace_body(obj,obj.text()+addition)]))
    if retired:
        raw=text(mod/DIPLOMACY);obj=root(raw).fields()['DIPLOMACY'];edits=[]
        for k,o in objects(obj):
            assert k[2:] not in retired
            for op,v in objects(o):
                if v.fields().get('country','')[2:] in retired:edits.append((*whole_entry(op,v),''))
        put(mod/DIPLOMACY,patch(raw,edits))
    for rel in sorted(ALLOWED):
        if not rel.endswith('.yml'):continue
        selected=[]
        for line in text(cm/rel).splitlines():
            match=re.match(r'\s*([A-Z0-9]+)(?:_ADJ)?:\d',line)
            if match and match[1] in tags:selected.append(line)
        if not selected and '/replace/' in rel:continue
        assert len(selected)==2*len(tags),(rel,len(selected))
        put(mod/rel,text(base/rel)+'\n'+'\n'.join(selected)+'\n')
    # Rebuild the same source-weighted literacy with the new country scopes.
    literacy_base=output/'literacy-base';shutil.copytree(mod,literacy_base)
    put(literacy_base/POPULATION_PATH,strip_imported_literacy(text(mod/POPULATION_PATH)))
    put(literacy_base/CODE_PATH,strip_imported_hook(text(mod/CODE_PATH)))
    shutil.copy2(literacy_base/POPULATION_PATH,mod/POPULATION_PATH);shutil.copy2(literacy_base/CODE_PATH,mod/CODE_PATH)
    build_literacy(output,demographic,mod,GAME)
    for t,c in report['countries'].items():
        c['provinces']=sum(sum(v==t for v in ps.values()) for ps in newowners.values())
    report.update(mod_directory=str(mod),integration_prior_package=str(prior),integration_policy='Preserve latest M5 modules; source-weighted ownership split and one population-mode recalculation',
                  source_m3_template_validation=report['validation'])
    report['validation']={**report['validation'],'exported_countries':len(report['countries']),
                          'subject_edges':len(report['subjects'])+len(report['vanilla_fallback_subjects']),
                          'stage':'integrated_m5_see_package_verification_for_economic_population_totals'}
    write(political/'conversion_report.json',report)
    # Record fresh geography/capacity even when no productive asset needs moving.
    target=Target(GAME);state_defs={**target.states,**definitions(mod/'map_data/state_regions')}
    from build_economy import expand_template_tech
    from complete_economy import active_laws
    effects={k:o for k,o in objects(root(text(GAME/'common/scripted_effects/00_starting_inventions.txt')))}
    history=container(mod/COUNTRIES,'COUNTRIES');techs={t[2:]:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws={t[2:]:active_laws(o,target,report['countries'][t[2:]]) for t,o in history.items()}
    buildings=building_rows(mod/BUILDINGS);by_part=defaultdict(list)
    for r in buildings:
        assert r['owner'] in newowners[r['state']].values()
        by_part[r['state'],r['owner']].append(r)
    pops=Counter()
    for k,n in original.items():pops[k[:2]]+=n
    anchor=find_ancestor(prior,'employment.json');old_employment={(r['state'],r['country']):r for r in read(anchor/'employment.json')}
    ownership_path=find_ancestor(prior,'ownership.json')/'ownership.json';ownership=read(ownership_path)
    owner_jobs={(h['state'],h['country']):h['estimated_owner_jobs'] for h in ownership['owner_hosts']}
    employment=[]
    for (s,t),n in sorted(pops.items()):
        bs=by_part[s,t];formal=sum(r['levels']*(1000 if r['building']=='building_barrack' else target.coefficients(r['building'],r['pms'],techs[t])['jobs']) for r in bs)+owner_jobs.get((s,t),0)
        arable=apportioned(Counter(newowners[s].values()),int(state_defs[s].get('arable_land',0)))[t]
        commercial=old_employment.get((s,t),{}).get('commercial_arable_levels',0)
        if (s,t) in old_employment:assert formal==old_employment[s,t]['formal_job_capacity'],(s,t,formal,old_employment[s,t]['formal_job_capacity'])
        else:assert not bs and not owner_jobs.get((s,t))
        kind=state_defs[s].get('subsistence_building','building_subsistence_farm');pms=target.select(kind,techs[t],set(),laws[t]);jobs=target.coefficients(kind,pms,techs[t])['jobs']
        employment.append({'state':s,'country':t,'population':n,'estimated_workforce':round(n*.25),'formal_job_capacity':formal,
             'commercial_arable_levels':commercial,'new_arable_share':arable,'subsistence_jobs_per_level':jobs,
             'new_subsistence_job_capacity':max(0,arable-commercial)*jobs,'subsistence_methods':pms,
             'infrastructure':target.infrastructure(s,n,techs[t],bs)})
    policy=read(ROOT/'config/personal/economy_population_options.json');elite={}
    for h in ownership['owner_hosts']:
        s,t=h['state'],h['country'];minimum=0
        for label,kind,cls,profession,fraction in [('manor','building_manor_house','nobles','aristocrats',1),('finance','building_financial_district','burghers','capitalists',ownership['policy']['burgher_investor_fraction'])]:
            levels=h['referenced_owned_levels'].get(label,0)
            if not levels:continue
            pm=target.select(kind,techs[t],set(),laws[t]);required=levels*target.numeric(pm)['building_employment_'+profession+'_add']
            pool=classes[s,t,cls]/100*policy['workforce_share']*fraction
            minimum=max(minimum,required/pool if pool else 1)
        elite[s,t]=min(1,minimum)
    write(output/'original_employment.json',employment)
    current,calibration=apply_mode(previous['population_mode'],original,employment,owner_jobs,elite,policy)
    put(mod/POPS,render_pops(current));final_pops=Counter()
    for k,n in current.items():final_pops[k[:2]]+=n
    for r in employment:
        r['population']=final_pops[r['state'],r['country']];r['estimated_workforce']=round(r['population']*policy['workforce_share'])
        r['infrastructure']=target.infrastructure(r['state'],r['population'],techs[r['country']],by_part[r['state'],r['country']])
        r['full_staffing_worker_shortfall']=max(0,r['formal_job_capacity']-r['estimated_workforce'])
    write(output/'employment.json',employment);write(output/'population_calibration.json',{'policy':dict(policy,population_mode=previous['population_mode']),'states':calibration,'rebuilt_from_uncalibrated_original':True})
    shutil.copy2(ownership_path,output/'ownership.json')
    write(output/'ownership_changes.json',{'transfers':tribes['transfers'],'primary_cultures':primary,
        'integer_population_policy':'Largest remainder on immutable original; reapply selected population mode once using new ownership capacities',
        'terrain_attachments':terrain,'retired_empty_vanilla_fallbacks':sorted(retired),
        'zero_source_population_retained_parts':sorted((s,t) for s,ps in newowners.items() for t in set(ps.values()) if not pops[s,t]),
        'source_owner_audit':read(ROOT/'.local/m3/unowned-source-audit.json')})
    meta=read(mod/'.metadata/metadata.json');a,b,c,d=map(int,re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',install['version']).groups());meta['version']=f'{a}.{b}.{c+1}-m5-test{d+1}'
    write(mod/'.metadata/metadata.json',meta)
    from verify_m5_uncolonized import verify
    check=verify(output,base,mod,candidate,newowners,original,current,primary)
    from verify_m4_literacy import verify as verify_literacy
    literacy=verify_literacy(output,mod,literacy_base)
    hashes=files(mod);report['output_sha256']=hashes;write(political/'conversion_report.json',report)
    changed=sorted(p for p,h in hashes.items() if baseline.get(p)!=h)
    assert set(hashes)==set(baseline) and set(changed)<=ALLOWED,changed
    inputs=[Path(__file__),ROOT/'tools/verify_m5_uncolonized.py',ROOT/'tools/update_m5_integrated_test.ps1',ROOT/'config/personal/economy_population_options.json',ownership_path,anchor/'employment.json',candidate/'conversion_report.json',candidate/'province_owners.json',original_path,prior/'package_report.json',ROOT/'.local/m3/unowned-source-audit.json']
    package={'status':'uncolonized_static_verified_runtime_pending','update_scope':'m5_uncolonized','version':meta['version'],
         'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),'political_run':str(political),'demographic_run':str(demographic),
         'population_mode':previous['population_mode'],'population_calibrated':previous['population_calibrated'],
         'source_population_conserved':previous['source_population_conserved'],'original_population_sha256':digest(output/'original_population.txt'),
         'new_campaign_required':True,'changed_files':changed,'input_sha256':{str(p.resolve()):digest(p) for p in inputs},'output_sha256':hashes}
    write(output/'package_report.json',package)
    write(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':literacy,'uncolonized':check,
          'package_report_sha256':digest(output/'package_report.json'),
          'audit_sha256':{p.name:digest(p) for p in output.glob('*.json') if p.name not in ('package_report.json','verification.json')}})
    assert read(ROOT/'.local/m5/installation-latest.json')==install
    write(ROOT/'.local/m5/uncolonized-package-latest.json',{'package':str(output),'version':meta['version'],'verification':check})
    return {'package':str(output),'version':meta['version'],'verification':check}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();out=a.output or ROOT/'.local/economy/packages'/('m5-uncolonized-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    print(__import__('json').dumps(build(a.candidate.resolve(),out.resolve()),ensure_ascii=True,indent=2))
