"""Build selectable worldwide population variants on the latest integrated mod.

The immutable original population is retained outside the mod. Switching modes
always restores it first, preserving unrelated changes from the latest package.
"""
import argparse
from collections import Counter
from datetime import datetime
import math
from pathlib import Path
import re
import shutil

from build_economy import expand_template_tech
from complete_economy import active_laws, csv_rows
from economy_model import Target, apportioned, definitions
from economy_population_calibration import calibrate, majority_signature
from extract_m3_politics import fields
from m3_world import digest
from package_m4_population_test import parse_pops
from package_m5_economic_modules import ROOT, GAME, BUILDINGS, read, write, files
from package_m5_population_calibration import find_ancestor, rewrite_populations, POPS, LITERACY
from pdx_text import root, Object
from verify_m4_literacy import parse_effects


def original_population_package(prior):
    """Resolve the immutable original, even after unrelated intervening updates."""
    cursor=prior
    while True:
        report=read(cursor/'package_report.json')
        if (cursor/'original_population.txt').exists():
            assert digest(cursor/'original_population.txt')==report['original_population_sha256'], 'Original population baseline changed'
            return cursor/'original_population.txt'
        if report.get('update_scope')=='m5_population_calibration':
            original=read(Path(report['prior_package'])/'package_report.json')
            return Path(original['mod_directory'])/POPS
        if not report.get('prior_package'):
            return Path(read(prior/'package_report.json')['mod_directory'])/POPS
        cursor=Path(report['prior_package'])


def apply_mode(mode, groups, employment, owner_jobs, elite, policy):
    if mode not in ('preserve','reserve_15'):raise ValueError('Unknown population mode: '+mode)
    p=dict(policy)
    if mode=='preserve':
        p['maximum_state_country_reduction_fraction']=0
        p['maximum_country_reduction_fraction']=0
    adjusted, rows=calibrate(groups,set(groups),employment,owner_jobs,elite,p)
    if mode=='preserve':assert adjusted==groups
    return adjusted,rows


def build(modes, config_path):
    policy=read(config_path)
    if modes==['configured']:modes=[policy['population_mode']]
    if not set(modes)<=set(policy['available_population_modes']):raise ValueError('Invalid mode selection')
    install=read(ROOT/'.local/economy/installation-latest.json');prior=Path(install['package'])
    previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    assert files(base)==previous['output_sha256']==files(Path(install['target']))
    original_path=original_population_package(prior);groups=parse_pops(original_path)
    current=parse_pops(base/POPS)
    assert set(current)==set(groups), 'Population identities changed; regenerate original ledger for latest demographics'
    anchor=find_ancestor(prior,'employment.json');anchor_report=read(anchor/'package_report.json')
    assert anchor_report['output_sha256'][BUILDINGS]==previous['output_sha256'][BUILDINGS], 'Employment ledger is stale'
    employment=read(anchor/'employment.json');old_rows={(r['state'],r['country']):r for r in employment}
    political=Path(previous.get('political_run',anchor_report['political_run']))
    demographic=Path(previous.get('demographic_run',anchor_report['demographic_run']))
    mapping_path=political/'conversion_report.json';mapping=read(mapping_path)
    owners_path=political/'province_owners.json';owners=read(owners_path)
    ownership_path=find_ancestor(prior,'ownership.json')/'ownership.json';ownership=read(ownership_path)
    owner_jobs={(h['state'],h['country']):h['estimated_owner_jobs'] for h in ownership['owner_hosts']}
    target=Target(GAME)
    state_defs={**target.states,**definitions(base/'map_data/state_regions')}
    history={k[2:]:v for k,v in fields(root((base/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects={k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    techs={t:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws={t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()}
    population=Counter()
    for k,n in groups.items():population[k[:2]]+=n
    employment=[];fallback_parts=[]
    for (s,t),n in sorted(population.items()):
        if (s,t) in old_rows:
            r=dict(old_rows[s,t])
            r.pop('population_calibration',None)
        else:
            # Fallback countries have no productive buildings in this campaign;
            # fail rather than silently omit any in a future package.
            from economy_model import building_rows
            assert not any(v['state']==s and v['owner']==t for v in building_rows(base/BUILDINGS)), 'Fallback employment requires a fresh building audit'
            land=apportioned(Counter(owners[s].values()),int(state_defs[s].get('arable_land',0)))[t]
            kind=state_defs[s].get('subsistence_building','building_subsistence_farm')
            pms=target.select(kind,techs[t],set(),laws[t])
            jobs=target.coefficients(kind,pms,techs[t])['jobs']
            r={'state':s,'country':t,'formal_job_capacity':0,'commercial_arable_levels':0,
               'subsistence_jobs_per_level':jobs,'new_arable_share':land,'new_subsistence_job_capacity':land*jobs,
               'subsistence_methods':pms,'coverage_origin':'vanilla_fallback_now_included'}
            fallback_parts.append((s,t))
        r['population']=n;r['estimated_workforce']=round(n*policy['workforce_share'])
        employment.append(r)
    assert set(old_rows)<=set(population)
    classes=Counter();stage=demographic/'staging/province_population_draft.csv'
    for r in csv_rows(stage):classes[r['target_state'],r['target_owner'],r['source_class']]+=int(r['centipersons'])/100
    elite={};elite_audit=[]
    for h in ownership['owner_hosts']:
        s,t=h['state'],h['country'];minimum=0
        for label,kind,cls,profession,fraction in [('manor','building_manor_house','nobles','aristocrats',1),('finance','building_financial_district','burghers','capitalists',ownership['policy']['burgher_investor_fraction'])]:
            levels=h['referenced_owned_levels'].get(label,0)
            if not levels:continue
            pm=target.select(kind,techs[t],set(),laws[t]);required=levels*target.numeric(pm)['building_employment_'+profession+'_add']
            pool=classes[s,t,cls]*policy['workforce_share']*fraction
            minimum=max(minimum,required/pool if pool else 1)
            elite_audit.append({'state':s,'country':t,'class':cls,'original_eligible_workers':pool,'required_owner_workers':required})
        elite[s,t]=min(1,minimum)
    rates=parse_effects(base/LITERACY)
    # The original rates effect includes source identities; fallback identities
    # retain the untouched native initialization from population history.
    assert set(rates)<=set(groups)
    paths=[];now=datetime.now().strftime('%Y%m%d-%H%M%S')
    for mode in modes:
        adjusted,rows=apply_mode(mode,groups,employment,owner_jobs,elite,policy)
        out=ROOT/'.local/economy/packages'/f'm5-population-options-{now}-{mode}'
        mod=out/'eu5_economy_test';shutil.copytree(base,mod)
        (out/'original_population.txt').write_text(original_path.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
        old_text=(base/POPS).read_text(encoding='utf-8-sig')
        new_text=rewrite_populations(old_text,adjusted);(mod/POPS).write_text(new_text,encoding='utf-8-sig')
        assert parse_pops(mod/POPS)==adjusted
        assert re.sub(r'(?m)^(\s*size\s*=\s*)\d+',r'\1SIZE',old_text)==re.sub(r'(?m)^(\s*size\s*=\s*)\d+',r'\1SIZE',new_text)
        assert parse_effects(mod/LITERACY)==rates
        before=Counter();after=Counter()
        for k,n in groups.items():before[k[1]]+=n
        for k,n in adjusted.items():after[k[1]]+=n
        countries={t:{'before':before[t],'after':after[t],'removed':before[t]-after[t]} for t in sorted(before)}
        lookup={(r['state'],r['country']):r for r in rows};updated=[]
        for r in employment:
            r=dict(r);a=lookup[r['state'],r['country']];r['population']=a['population_after']
            r['estimated_workforce']=round(r['population']*policy['workforce_share'])
            r['capacity_gap_full_staffing']=max(0,r['estimated_workforce']-r['formal_job_capacity']-r['new_subsistence_job_capacity'])
            r['capacity_gap_safety_staffing']=math.ceil(a['remaining_worker_gap_at_planning_staffing']);updated.append(r)
        literacy={}
        for t in countries:
            keys=[k for k in rates if k[1]==t]
            if keys:
                literacy[t]={label:float(sum(rates[k]*g[k] for k in keys)/sum(g[k] for k in keys)*100) for label,g in [('before',groups),('after',adjusted)]}
        meta=read(mod/'.metadata/metadata.json');v=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',previous['version']);assert v
        major,minor,patch,test=map(int,v.groups());meta['version']=f'{major}.{minor}.{patch+1}-m5-test{test+1}'
        meta['name']='EU5 M5 - World 1780 - '+('Original Population' if mode=='preserve' else '15 Percent Reserve')
        meta['id']='eu5-personal-population-'+mode.replace('_','-')
        meta['short_description']='Worldwide population mode: '+mode+'. New campaign required. Enable only one population variant.'
        write(mod/'.metadata/metadata.json',meta)
        output=files(mod);changed=sorted(p for p,h in output.items() if previous['output_sha256'].get(p)!=h)
        assert set(output)==set(previous['output_sha256']) and set(changed)<={POPS,'.metadata/metadata.json'}
        check={'status':'passed','mode':mode,'population_before':sum(groups.values()),'population_after':sum(adjusted.values()),
               'removed_persons':sum(groups.values())-sum(adjusted.values()),'world_countries':len(countries),'world_state_country_parts':len(rows),
               'newly_covered_fallback_parts':len(fallback_parts),'only_population_sizes_and_metadata_changed':True,
               'all_world_population_groups_processed':True,'all_identity_groups_preserved':set(groups)==set(adjusted),
               'original_population_exact':adjusted==groups,'culture_religion_majority_status_preserved':majority_signature(groups)==majority_signature(adjusted) and majority_signature(groups,True)==majority_signature(adjusted,True),
               'no_compounding_original_baseline_used':True,'runtime_verified':False}
        assert apply_mode(mode,groups,employment,owner_jobs,elite,policy)[0]==adjusted
        write(out/'population_calibration.json',{'policy':policy,'summary':check,'states':rows,'countries':countries})
        write(out/'population_policy.snapshot.json',dict(policy,population_mode=mode))
        write(out/'employment.json',updated);write(out/'original_employment.json',employment)
        write(out/'elite_staffing.json',elite_audit);write(out/'literacy_population_reweighting.json',literacy)
        inputs=[Path(__file__),ROOT/'tools/economy_population_calibration.py',ROOT/'tools/update_m5_integrated_test.ps1',config_path,original_path,anchor/'employment.json',ownership_path,mapping_path,owners_path,stage,prior/'package_report.json']
        report={'status':'population_options_static_verified_runtime_pending','update_scope':'m5_population_options','version':meta['version'],
                'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),'political_run':str(political),'demographic_run':str(demographic),
                'population_mode':mode,'population_calibrated':mode=='reserve_15','original_population_sha256':digest(out/'original_population.txt'),
                'source_population_conserved':mode=='preserve','new_campaign_required':True,'changed_files':changed,
                'input_sha256':{str(p):digest(p) for p in inputs},'output_sha256':output}
        write(out/'package_report.json',report)
        write(out/'verification.json',{'status':'passed_static_runtime_pending','population_options':check,
              'literacy':{'status':'passed','all_original_identity_rates_preserved':True,'runtime_verified':False},
              'package_report_sha256':digest(out/'package_report.json'),
              'audit_sha256':{p.name:digest(p) for p in out.glob('*.json') if p.name!='package_report.json'},
              'original_population_sha256':digest(out/'original_population.txt')})
        (out/'说明.txt').write_text(('保留原人口' if mode=='preserve' else '全球15%劳动力余量优化')+'\n'+
            f"世界人口：{sum(groups.values()):,} → {sum(adjusted.values()):,}\n覆盖 {len(countries)} 国、{len(rows)} 个州内国别份额。\n"+
            '15%指岗位容量之外的劳动力余量；每州国别最多减20%、每国最多减15%，保护文化宗教多数与所有者岗位。\n'+
            '两版只在人口规模和显示名称上不同；必须新开局。不要同时启用。\n'+
            '切换或重建均从未删减人口重新计算，不会连续扣减。原版回退人口也纳入全球检查。\n',encoding='utf-8')
        paths.append(out)
        print(__import__('json').dumps({'package':str(out),'verification':check},ensure_ascii=False))
    write(ROOT/'.local/economy/population-variants-latest.json',{'prior_package':str(prior),'packages':{read(p/'package_report.json')['population_mode']:str(p) for p in paths}})
    return paths


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--population-mode',choices=['preserve','reserve_15','both','configured'],default='configured')
    p.add_argument('--config',type=Path,default=ROOT/'config/personal/economy_population_options.json')
    a=p.parse_args();build(['preserve','reserve_15'] if a.population_mode=='both' else [a.population_mode],a.config)
