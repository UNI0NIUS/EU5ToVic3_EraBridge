"""Repair stale terrain ownership on the current integrated M5 package."""
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
import csv,copy,re,shutil
from package_m5_uncolonized import (ROOT,GAME,STATE,POPS,COUNTRIES,BUILDINGS,MILITARY,
    read,write,files,digest,text,put,container,promote_states,split_groups,render_pops,
    original_population_package,find_ancestor,apply_mode,strip_imported_literacy,strip_imported_hook)
from build_m2_prototype import objects,whole_entry,patch,state_owners
from package_m4_population_test import rows,parse_pops
from economy_model import Target,definitions,building_rows,render_buildings,apportioned
from pdx_text import root
from m3_world import World
from m3_uncolonized import restore,province_land_edges
from m5_territory_replay import restore as restore_terrain
from m3_terrain_finalization import plan,apply
from m4_literacy import build as build_literacy,POPULATION_PATH,CODE_PATH,EFFECT_PATH,HOOK_PATH
from build_economy import expand_template_tech
from complete_economy import active_laws


def build(frontier=False):
    install=read(ROOT/'.local/m5/installation-latest.json');prior=Path(install['package']);previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    assert files(base)==previous['output_sha256']==files(Path(install['target']))
    oldpolitical=Path(previous['political_run']);report=read(oldpolitical/'conversion_report.json');oldowners=read(oldpolitical/'province_owners.json');old_dem=Path(previous['demographic_run'])
    assert not report.get('frontier_finalization') if frontier else not report.get('terrain_finalization'),'Political phase already finalized'
    w=World(GAME,Path('D:/Steam/steamapps/common/Europa Universalis V/game'),read(ROOT/'.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json'),read(ROOT/'.local/m3/politics-with-cultures.json'),read(ROOT/'config/personal/m3_world.json'),ROOT/'.local/m3/cache')
    w.geometry();w.politics_model();restore(w,report['uncolonized_tribes']);restore_terrain(w,report)
    if frontier:
        apply(w,report['terrain_finalization'])
        w.countries=copy.deepcopy(report['countries'])
    assert w.owners==oldowners
    votes=defaultdict(Counter);pop=Counter();tags={c['source_id']:t for t,c in report['countries'].items() if c['source_id']}
    for r in rows(old_dem/'staging/province_population_draft.csv'):
        n=int(r['centipersons']);pop[r['target_owner']]+=n
        if r['source_owner'] in tags:votes[r['target_province']][tags[r['source_owner']]]+=n
    if frontier:
        from m3_colonial_frontier import prepare
        decision=prepare(w,ROOT/'.local/m4/source-1780-population',old_dem/'staging',ROOT/'config/personal/m3_frontier_review.json')
    else:
        decision=plan(oldowners,report['map_repairs'],report['countries'],province_land_edges(w,ROOT/'.local/m3/cache/tribal_land_edges.json'),votes,pop)
        apply(w,decision)
    assert decision['changes'],'No political changes found'
    owners=w.owners;retired=set(decision['country_aliases'])
    output=ROOT/'.local/economy/packages'/(('m5-frontier-' if frontier else 'm5-terrain-')+datetime.now().strftime('%Y%m%d-%H%M%S-%f'));mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    political=output/'political';political.mkdir();write(political/'province_owners.json',owners)
    report['frontier_finalization' if frontier else 'terrain_finalization']=decision
    for t in retired:del report['countries'][t]
    for t,c in report['countries'].items():c['provinces']=sum(sum(v==t for v in ps.values()) for ps in owners.values())
    report['mod_directory']=str(mod);report['validation']['exported_countries']=len(report['countries'])
    write(political/'conversion_report.json',report)
    demographic=output/'demographic';demographic.mkdir()
    for directory in ('demographics','template_fallback'):shutil.copytree(old_dem/directory,demographic/directory)
    sr=read(old_dem/'staging/staging_report.json');reviews=read(sr['location_reviews']['path']);reviews['political_map_sha256']=digest(political/'province_owners.json')
    for name,correction in decision.get('population_corrections',{}).items():
        reviews['entries'][name]={'status':'mapped','targets':[{'province':correction['province'],'weight':1}],'note':correction['reason']}
    write(output/'location_reviews.rebased.json',reviews)
    from stage_m4_population import stage
    stage(political,ROOT/'.local/m4/source-1780-population',demographic/'staging',GAME,w.eu5,output/'location_reviews.rebased.json',Path(sr['population_policy']['path']))
    from verify_m4_population import verify as verify_population
    verify_population(ROOT/'.local/m4/source-1780-population',demographic/'staging')
    dr=read(old_dem/'demographics/demographics_report.json');cultures={r['source_culture']:r['target_culture'] for r in rows(old_dem/'demographics/resident_culture_crosswalk.csv')};religions={r['source_religion']:r['target_religion'] for r in rows(old_dem/'demographics/resident_religion_crosswalk.csv')}
    from build_m3_world import load_localization
    import json
    name_files=[];ethnic_names={}
    for lang in ('english','simp_chinese'):
        labels=load_localization(GAME/'localization'/lang);labels.update(load_localization(base/'localization'/lang))
        names={}
        for t,c in report['countries'].items():
            if not c.get('generated_uncolonized'):continue
            culture=cultures.get(c['source_culture'],c['culture']);label=labels[culture]
            names[t]=label;names[t+'_ADJ']=label;c['name_'+lang]=label
        rel=f'localization/{lang}/eu5_world_l_{lang}.yml';name_files.append(rel)
        raw=text(mod/rel)
        for key,label in names.items():
            raw,count=re.subn(r'(?m)^\s*'+re.escape(key)+r':\d*\s*"[^\n]*"\s*$',lambda m:' '+key+':0 '+json.dumps(label,ensure_ascii=False),raw)
            assert count==1,(lang,key)
        put(mod/rel,raw);ethnic_names[lang]={t:n for t,n in names.items() if not t.endswith('_ADJ')}
    migrants={(r['source'],s):r['target'] for r in dr['migrant_cultures']['cultures'] for s in r['states']}
    weights=defaultdict(Counter);source_groups=Counter();classes=Counter()
    for r in rows(demographic/'staging/province_population_draft.csv'):
        s,p,t=r['target_state'],r['target_province'],r['target_owner'];n=int(r['centipersons']);c=migrants.get((r['source_culture'],s),cultures[r['source_culture']]);faith=religions[r['source_religion']]
        weights[s,oldowners[s][p],c,faith][t]+=n;source_groups[s,t,c,faith]+=n;classes[s,t,r['source_class']]+=n
    original_path=original_population_package(prior);oldoriginal=parse_pops(original_path)
    if frontier:
        from m3_colonial_frontier import reallocate_original
        original=reallocate_original(oldoriginal,rows(old_dem/'staging/province_population_draft.csv'),owners,cultures,religions,migrants,decision['population_corrections'])
    else:original=split_groups(oldoriginal,weights)
    put(output/'original_population.txt',render_pops(original))
    with (demographic/'demographics/resident_population_groups.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['state','owner','culture','religion','centipersons','preview_integer_persons']);writer.writerows([*k,n,original.get(k,0)] for k,n in sorted(source_groups.items()))
    dr.update(stage=str(demographic/'staging'),stage_report_sha256=digest(demographic/'staging/staging_report.json'));write(demographic/'demographics/demographics_report.json',dr)
    for name in ('independent_verification.json','population_history_preview.txt'):
        path=demographic/'demographics'/name
        if path.exists():path.unlink()
    put(demographic/'demographics/population_history_preview.txt',render_pops({k:original.get(k,0) for k in source_groups}))
    promote_states(base,mod,owners,set(report['countries']))
    for rel,key in ((COUNTRIES,'COUNTRIES'),(POPULATION_PATH,'POPULATION')):
        raw=text(mod/rel);obj=root(raw).fields()[key]
        put(mod/rel,patch(raw,[(*whole_entry(k,v),'') for k,v in objects(obj) if k[2:] in retired]))
    buildings=building_rows(base/BUILDINGS);removed=[];kept=[]
    affected_parts={(r['state'],r['from']) for r in decision['changes']}
    populated_parts={k[:2] for k in original}
    for r in buildings:
        if r['owner'] not in owners[r['state']].values() or ((r['state'],r['owner']) in affected_parts and (r['state'],r['owner']) not in populated_parts):
            # The sole affected facility is a transport port created for the
            # old vanilla-Russia fallback. There is no source Russian territory
            # or population here to support that synthetic initialization.
            assert r['building']=='building_port' and not r['guards']
            assert not any(k[:2]==(r['state'],r['owner']) for k in original)
            removed.append(r)
        else:kept.append(r)
    raw=text(base/BUILDINGS);edits=[];removed_keys={(r['state'],r['owner'],r['building']) for r in removed}
    def remove_ports(obj,state=None,owner=None):
        for k,v in objects(obj):
            if k.startswith('s:'):remove_ports(v,k[2:],owner)
            elif k.startswith('region_state:'):remove_ports(v,state,k[13:])
            elif k=='create_building':
                kind=next(value for field,value in v.entries() if field=='building')
                if (state,owner,kind) in removed_keys:edits.append((*whole_entry(k,v),''))
            elif k!='limit':remove_ports(v,state,owner)
    remove_ports(root(raw));assert len(edits)==len(removed)
    put(mod/BUILDINGS,patch(raw,edits))
    target=Target(GAME);target.states.update(definitions(mod/'map_data/state_regions'))
    effects=dict(objects(root(text(GAME/'common/scripted_effects/00_starting_inventions.txt'))));history=container(mod/COUNTRIES,'COUNTRIES')
    techs={t[2:]:expand_template_tech(o,effects,target) for t,o in history.items()};laws={t[2:]:active_laws(o,target,report['countries'][t[2:]]) for t,o in history.items()}
    ownership_path=find_ancestor(prior,'ownership.json')/'ownership.json';ownership=read(ownership_path);owner_jobs={(h['state'],h['country']):h['estimated_owner_jobs'] for h in ownership['owner_hosts']}
    assert not any(t in retired for s,t in owner_jobs)
    bypart=defaultdict(list)
    for r in kept:bypart[r['state'],r['owner']].append(r)
    populations=Counter()
    for k,n in original.items():populations[k[:2]]+=n
    employment=[]
    for (s,t),n in sorted(populations.items()):
        bs=bypart[s,t];formal=sum(r['levels']*(1000 if r['building']=='building_barrack' else target.coefficients(r['building'],r['pms'],techs[t])['jobs']) for r in bs)+owner_jobs.get((s,t),0)
        arable=apportioned(Counter(owners[s].values()),int(target.states[s].get('arable_land',0)))[t]
        from extract_m3_politics import sequence
        farms=set(sequence(target.states[s].get('arable_resources')));commercial=sum(r['levels'] for r in bs if r['building'] in farms)
        kind=target.states[s].get('subsistence_building','building_subsistence_farm');pms=target.select(kind,techs[t],set(),laws[t]);jobs=target.coefficients(kind,pms,techs[t])['jobs']
        employment.append({'state':s,'country':t,'population':n,'formal_job_capacity':formal,'commercial_arable_levels':commercial,'new_arable_share':arable,'subsistence_jobs_per_level':jobs,'new_subsistence_job_capacity':max(0,arable-commercial)*jobs,'subsistence_methods':pms})
    policy=read(ROOT/'config/personal/economy_population_options.json');elite={}
    for h in ownership['owner_hosts']:
        s,t=h['state'],h['country'];minimum=0
        for label,kind,cls,profession,fraction in [('manor','building_manor_house','nobles','aristocrats',1),('finance','building_financial_district','burghers','capitalists',ownership['policy']['burgher_investor_fraction'])]:
            levels=h['referenced_owned_levels'].get(label,0)
            if not levels:continue
            pm=target.select(kind,techs[t],set(),laws[t]);required=levels*target.numeric(pm)['building_employment_'+profession+'_add'];pool=classes[s,t,cls]/100*policy['workforce_share']*fraction;minimum=max(minimum,required/pool if pool else 1)
        elite[s,t]=min(1,minimum)
    write(output/'original_employment.json',employment);current,calibration=apply_mode(previous['population_mode'],original,employment,owner_jobs,elite,policy)
    if frontier:
        affected_states={r['state'] for r in decision['changes']}|{r['state'] for r in decision['population_corrections'].values()}
        baseline_pops=parse_pops(base/POPS)
        # Prior identity-only updates deliberately preserve regional integer
        # totals. Avoid unrelated one-person rounding churn on this border fix.
        current={k:n for k,n in current.items() if k[0] in affected_states}
        current.update({k:n for k,n in baseline_pops.items() if k[0] not in affected_states})
        unchanged_totals=Counter()
        for k,n in current.items():unchanged_totals[k[:2]]+=n
        for r in calibration:
            if r['state'] in affected_states:continue
            actual=unchanged_totals[r['state'],r['country']];delta=actual-r['population_after']
            r.update(population_after=actual,removed_persons=r['population_before']-actual,
                     reduction_fraction=1-actual/r['population_before'],estimated_workforce_after=actual*policy['workforce_share'],
                     unchanged_geography_retained_existing_population=True)
            r['remaining_worker_gap_at_planning_staffing']-=delta*policy['workforce_share']
    put(mod/POPS,render_pops(current))
    finalpop=Counter()
    for k,n in current.items():finalpop[k[:2]]+=n
    for r in employment:r['population']=finalpop[r['state'],r['country']];r['estimated_workforce']=round(r['population']*policy['workforce_share'])
    write(output/'employment.json',employment);write(output/'population_calibration.json',{'policy':dict(policy,population_mode=previous['population_mode']),'states':calibration,'rebuilt_from_uncalibrated_original':True});shutil.copy2(ownership_path,output/'ownership.json')
    literacy_base=output/'literacy-base';shutil.copytree(mod,literacy_base)
    put(literacy_base/POPULATION_PATH,strip_imported_literacy(text(mod/POPULATION_PATH)));put(literacy_base/CODE_PATH,strip_imported_hook(text(mod/CODE_PATH)))
    shutil.copy2(literacy_base/POPULATION_PATH,mod/POPULATION_PATH);shutil.copy2(literacy_base/CODE_PATH,mod/CODE_PATH)
    build_literacy(output,demographic,mod,GAME)
    from verify_m4_literacy import verify as verify_literacy
    literacy=verify_literacy(output,mod,literacy_base)
    # Read back the installed-format country, population and asset references.
    actual={s[2:]:{('x'+p[1:].upper()):t for p,t in state_owners(o,strict=False).items()} for s,o in container(mod/STATE,'STATES').items()};assert actual==owners
    from m3_uncolonized import connected_groups
    generated={t:c for t,c in report['countries'].items() if c.get('generated_uncolonized')}
    island_exceptions={r['province'] for r in decision.get('reviewed_islands',[])}
    identity={p:generated[t]['culture'] for ps in owners.values() for p,t in ps.items() if t in generated and p not in island_exceptions}
    components={frozenset(ps) for ps in connected_groups(identity,province_land_edges(w,ROOT/'.local/m3/cache/tribal_land_edges.json'))}
    assert components=={frozenset(p for ps in owners.values() for p,owner in ps.items() if owner==t and p not in island_exceptions) for t in generated},'Disconnected tribal terrain'
    for r in decision.get('reviewed_islands',[]):assert owners[r['state']][r['province']]==r['to']
    for lang,names in ethnic_names.items():
        actual_names=load_localization(mod/'localization'/lang)
        for t,name in names.items():assert actual_names[t]==actual_names[t+'_ADJ']==name
    assert parse_pops(mod/POPS)==current and sum(original.values())==sum(oldoriginal.values())
    assert digest(mod/MILITARY)==digest(base/MILITARY)
    def walk(o,t):
        from pdx_text import Object
        for k,v in o.entries():
            if k=='state_region':assert t in owners[v[2:]].values(),(t,v)
            elif isinstance(v,Object):walk(v,t)
    for scope,o in container(mod/MILITARY,'MILITARY_FORMATIONS').items():walk(o,scope[2:])
    for r in kept:assert r['owner'] in owners[r['state']].values()
    for h in ownership['owner_hosts']:assert h['country'] in owners[h['state']].values()
    assert all(sum(n for (s,t,c,r),n in current.items() if t==tag)>0 for tag in report['countries'])
    old_build={(r['state'],r['owner'],r['building']):r for r in buildings};new_build={(r['state'],r['owner'],r['building']):r for r in building_rows(mod/BUILDINGS)}
    assert set(old_build)-set(new_build)=={(r['state'],r['owner'],r['building']) for r in removed}
    from package_m5_economic_modules import canonical
    for k,r in new_build.items():
        old=old_build[k]
        assert (r['levels'],r['pms'],r['guards'])==(old['levels'],old['pms'],old['guards'])
        assert canonical(root(r['body']))==canonical(root(old['body']))
    meta=read(mod/'.metadata/metadata.json');a,b,c,d=map(int,re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',install['version']).groups());meta['version']=f'{a}.{b}.{c+1}-m5-test{d+1}';write(mod/'.metadata/metadata.json',meta)
    hashes=files(mod);changed=sorted(p for p,h in hashes.items() if previous['output_sha256'][p]!=h)
    allowed={'.metadata/metadata.json',STATE,POPS,COUNTRIES,BUILDINGS,POPULATION_PATH,CODE_PATH,EFFECT_PATH,HOOK_PATH,*name_files}
    assert set(hashes)==set(previous['output_sha256']) and set(changed)<=allowed
    check={'status':'passed','stale_terrain_fixed':len(decision.get('anchor_refresh',[])),'russian_stale_provinces_fixed':sum(r['from']=='RUS' for r in decision.get('anchor_refresh',[])),
        'reviewed_source_owned_provinces':sum(r['reason']=='reviewed_source_owned_population' for r in decision.get('anchor_refresh',[])),
        'changed_provinces':len(decision['changes']),'unresolved_island_provinces':len(decision['unresolved']),'tribal_countries':sum(c.get('generated_uncolonized',False) for c in report['countries'].values()),'country_aliases':decision['country_aliases'],
        'province_owners_verified':True,'population_and_literacy_rebuilt':True,'population_mode_recomputed_once':True,'military_and_investor_references_verified':True,
        'unrelated_files_preserved':True,'removed_orphan_ports':len(removed),'ethnic_only_names':ethnic_names,'population':sum(current.values()),'runtime_verified':False}
    if frontier:check.update(active_charter_settlements=len(decision['country_aliases']),reviewed_islands=len(decision['reviewed_islands']),native_rechecks=sum(r['reason']=='corrected_geography_source_native_majority' for r in decision['changes']),population_corrections=decision['population_corrections'])
    write(output/'terrain_verification.json',check);write(output/'terrain_changes.json',decision);write(output/'removed_orphan_buildings.json',removed)
    report['output_sha256']=hashes;write(political/'conversion_report.json',report)
    inputs=[Path(__file__),ROOT/'tools/m3_terrain_finalization.py',ROOT/'tools/update_m5_integrated_test.ps1',prior/'package_report.json',oldpolitical/'province_owners.json',old_dem/'staging/province_population_draft.csv',original_path,ownership_path]
    if frontier:inputs.extend([ROOT/'tools/m3_colonial_frontier.py',ROOT/'config/personal/m3_frontier_review.json',ROOT/'tools/build_location_workstation.py'])
    package={'status':'terrain_finalization_verified_runtime_pending','update_scope':'m5_terrain_finalization','version':meta['version'],'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),
        'political_run':str(political),'demographic_run':str(demographic),'population_mode':previous['population_mode'],'population_calibrated':previous['population_calibrated'],'source_population_conserved':previous['source_population_conserved'],'original_population_sha256':digest(output/'original_population.txt'),
        'new_campaign_required':True,'changed_files':changed,'input_sha256':{str(p.resolve()):digest(p) for p in inputs},'output_sha256':hashes}
    write(output/'package_report.json',package);write(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':literacy,'terrain_finalization':check,'package_report_sha256':digest(output/'package_report.json'),
          'audit_sha256':{p.name:digest(p) for p in output.glob('*.json') if p.name not in ('package_report.json','verification.json')}})
    assert read(ROOT/'.local/m5/installation-latest.json')==install
    write(ROOT/'.local/m5/terrain-package-latest.json',{'package':str(output),'version':meta['version'],'verification':check});return {'package':str(output),'version':meta['version'],'verification':check}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--frontier',action='store_true')
    print(__import__('json').dumps(build(parser.parse_args().frontier),indent=2))
