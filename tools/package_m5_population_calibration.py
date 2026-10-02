"""Build a reversible, population-only calibration on the latest integrated mod."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import math
from pathlib import Path
import re
import shutil

from build_economy import expand_template_tech
from build_m2_prototype import objects, patch, replace_body
from complete_economy import active_laws, csv_rows
from economy_model import Target
from economy_population_calibration import calibrate, majority_signature
from extract_m3_politics import fields
from package_m4_population_test import parse_pops
from package_m5_economic_modules import ROOT,GAME,BUILDINGS,read,write,files
from m3_world import digest
from pdx_text import Object,root
from verify_m4_literacy import parse_effects

POPS='common/history/pops/00_eu5_world.txt'
LITERACY='common/scripted_effects/zz_eu5_m4_literacy.txt'


def find_ancestor(start, filename):
    p=start
    while not (p/filename).exists():p=Path(read(p/'package_report.json')['prior_package'])
    return p


def rewrite_populations(text, expected):
    changes=[]
    for state,obj in objects(root(text).fields()['POPS']):
        for owner,body in objects(obj):
            for op,pop in objects(body):
                assert op=='create_pop';f=fields(pop)
                key=state[2:],owner.removeprefix('region_state:'),f['culture'],f['religion']
                if int(f['size'])==expected[key]:continue
                body,count=re.subn(r'(?m)^(\s*size\s*=\s*)\d+',lambda m:m[1]+str(expected[key]),pop.text())
                assert count==1
                changes.append(replace_body(pop,body))
    return patch(text,changes)


def build():
    installation=read(ROOT/'.local/economy/installation-latest.json');prior=Path(installation['package'])
    previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    assert files(base)==previous['output_sha256'];assert files(Path(installation['target']))==previous['output_sha256']
    # Never compound reductions, even if an unrelated package followed this one.
    check=prior
    while True:
        r=read(check/'package_report.json')
        if r.get('update_scope')=='m5_population_calibration':raise ValueError('Population already calibrated; rebuild from original pre-calibration package instead of compounding cuts')
        if not r.get('prior_package'):break
        check=Path(r['prior_package'])
    employment_path=find_ancestor(prior,'employment.json')/'employment.json'
    employment=read(employment_path)
    employment_report=read(employment_path.parent/'package_report.json')
    assert employment_report['output_sha256'][BUILDINGS]==previous['output_sha256'][BUILDINGS]
    owner_package=find_ancestor(prior,'ownership.json');ownership=read(owner_package/'ownership.json')
    policy_path=ROOT/'config/personal/economy_population_calibration.json';policy=read(policy_path)
    demographic_run=previous.get('demographic_run',employment_report['demographic_run'])
    political_run=previous.get('political_run',employment_report['political_run'])
    demographic=Path(demographic_run);stage=demographic/'staging/province_population_draft.csv'
    resident=demographic/'demographics/resident_population_groups.csv'
    groups=parse_pops(base/POPS)
    eligible={tuple(r[k] for k in ('state','owner','culture','religion')) for r in csv_rows(resident) if int(r['preview_integer_persons'])>0}
    classes=Counter()
    for r in csv_rows(stage):classes[r['target_state'],r['target_owner'],r['source_class']]+=int(r['centipersons'])/100
    owner_jobs={(h['state'],h['country']):h['estimated_owner_jobs'] for h in ownership['owner_hosts']}
    target=Target(GAME)
    mapping_path=Path(political_run)/'conversion_report.json';mapping=read(mapping_path)
    history={k[2:]:v for k,v in fields(root((base/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects={k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    techs={t:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws={t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()}
    elite={};elite_audit=[]
    for h in ownership['owner_hosts']:
        s,t=h['state'],h['country'];minimum=0
        for label,kind,cls,profession,fraction in [('manor','building_manor_house','nobles','aristocrats',1),('finance','building_financial_district','burghers','capitalists',ownership['policy']['burgher_investor_fraction'])]:
            levels=h['referenced_owned_levels'].get(label,0)
            if not levels:continue
            pms=target.select(kind,techs[t],set(),laws[t])
            per_level=target.numeric(pms)['building_employment_'+profession+'_add']
            pool=classes[s,t,cls]*policy['workforce_share']*fraction
            required=levels*per_level
            minimum=max(minimum,required/pool if pool else 1)
            elite_audit.append({'state':s,'country':t,'class':cls,'original_eligible_workers':pool,'required_owner_workers':required})
        elite[s,t]=min(1,minimum)
    adjusted,rows=calibrate(groups,eligible,employment,owner_jobs,elite,policy)
    part_before=Counter();part_after=Counter();national_before=Counter();national_after=Counter()
    for k,n in groups.items():part_before[k[:2]]+=n;national_before[k[1]]+=n
    for k,n in adjusted.items():part_after[k[:2]]+=n;national_after[k[1]]+=n
    for r in elite_audit:
        pair=r['state'],r['country'];ratio=part_after[pair]/part_before[pair]
        r['conservative_eligible_workers_after']=r['original_eligible_workers']*ratio
        if part_after[pair]<part_before[pair]:assert r['conservative_eligible_workers_after']+1e-5>=r['required_owner_workers']
    rates=parse_effects(base/LITERACY)
    assert eligible<=rates.keys()
    # Keep the source fractional literacy of each identity. National averages
    # are recomputed because states receive different population reductions.
    literacy={}
    for t in sorted(national_before):
        keys=[k for k in eligible if k[1]==t]
        if not keys:continue
        def average(g):return float(sum(rates[k]*g[k] for k in keys)/sum(g[k] for k in keys)*100)
        literacy[t]={'source_group_weighted_percent_before':average(groups),'source_group_weighted_percent_after':average(adjusted)}
    out=ROOT/'.local/economy/packages'/('m5-population-calibration-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(base,mod)
    old_text=(base/POPS).read_text(encoding='utf-8-sig')
    new_text=rewrite_populations(old_text,adjusted);(mod/POPS).write_text(new_text,encoding='utf-8-sig')
    assert parse_pops(mod/POPS)==adjusted
    assert re.sub(r'(?m)^(\s*size\s*=\s*)\d+',r'\1SIZE',old_text)==re.sub(r'(?m)^(\s*size\s*=\s*)\d+',r'\1SIZE',new_text)
    assert parse_effects(mod/LITERACY)==rates
    assert majority_signature(groups)==majority_signature(adjusted)
    assert majority_signature(groups,True)==majority_signature(adjusted,True)
    countries={t:{'before':national_before[t],'after':national_after[t],'removed':national_before[t]-national_after[t],
        'reduction_fraction':1-national_after[t]/national_before[t]} for t in sorted(national_before)}
    updated=[];lookup={(r['state'],r['country']):r for r in rows}
    for r in employment:
        r=dict(r);pair=r['state'],r['country'];a=lookup[pair];r['population']=a['population_after']
        r['estimated_workforce']=round(r['population']*policy['workforce_share'])
        r['capacity_gap_full_staffing']=max(0,r['estimated_workforce']-r['formal_job_capacity']-r['new_subsistence_job_capacity'])
        r['capacity_gap_safety_staffing']=math.ceil(a['remaining_worker_gap_at_planning_staffing'])
        r['population_calibration']={'before':a['population_before'],'removed':a['removed_persons'],'workforce_reserve_fraction':policy['workforce_reserve_fraction']}
        updated.append(r)
    meta=read(mod/'.metadata/metadata.json');version=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',previous['version']);assert version
    major,minor,patchnum,test=map(int,version.groups());meta['version']=f'{major}.{minor}.{patchnum+1}-m5-test{test+1}'
    meta['short_description']='Integrated EU5 world with one-time bounded population calibration (15% workforce reserve); new campaign required.'
    write(mod/'.metadata/metadata.json',meta)
    output=files(mod);changed=sorted(p for p,h in output.items() if previous['output_sha256'].get(p)!=h)
    assert set(output)==set(previous['output_sha256']) and set(changed)=={POPS,'.metadata/metadata.json'}
    verification={'status':'passed','population_before':sum(groups.values()),'population_after':sum(adjusted.values()),
        'removed_persons':sum(groups.values())-sum(adjusted.values()),'changed_state_country_parts':sum(r['removed_persons']>0 for r in rows),
        'changed_countries':sum(r['removed']>0 for r in countries.values()),'only_population_sizes_and_metadata_changed':True,
        'all_identity_groups_preserved':True,'culture_religion_majority_status_preserved':True,'literacy_rates_unchanged':True,
        'template_fallback_population_preserved':True,'state_country_caps_verified':True,'reserve_floor_verified':True,
        'elite_staffing_pools_preserved':True,'double_calibration_rejected':True,'runtime_verified':False}
    artifacts={'population_calibration.json':{'policy':policy,'summary':verification,'states':rows,'countries':countries},
        'population_policy.snapshot.json':policy,'elite_staffing.json':elite_audit,'literacy_population_reweighting.json':literacy,
        'employment.json':updated,'original_employment.json':employment,
        'population_group_changes.json':[{'state':k[0],'country':k[1],'culture':k[2],'religion':k[3],'before':n,'after':adjusted[k]} for k,n in groups.items() if n!=adjusted[k]]}
    for name,value in artifacts.items():write(out/name,value)
    summary=[f"人口校准版 {meta['version']}",f"世界人口：{sum(groups.values()):,} → {sum(adjusted.values()):,}，减少 {verification['removed_persons']:,}。",
        '保留规划岗位容量外15%的劳动力余量；每州国别份额最多削减20%，每国最多削减15%。',
        '岗位口径：正规生产岗位75%，庄园/金融区岗位100%，可用自给岗位100%；劳动力按总人口25%估算。',
        '只缩减开局人口群的总人数，不单删劳工、不迁移人口、不改文化宗教身份；家属与劳动力由游戏初始化同比生成。',
        '各人口群的识字率保持原值；国家平均识字率会因地区权重变化而变化。所有原有人口群至少保留1人。',
        '保留本地庄园/金融区所需的精英人口，并保护州及州国别份额的文化和宗教绝对多数状态。',
        '原始EU5人口台账不修改。此校准已不追求与EU5总人口完全相等；不能再把原始人口完全守恒作为验收标准。',
        '建筑、耕地、军队、法律与外交均保持原值。税基减少可能使财政变差；仍需新开局验证就业、物价和预算。',
        '本阶段应最后应用。后续重建必须使用校准后人口和该包台账，或从校准前的原始人口重新计算，禁止连续重复削减。']
    for t in ['ITA','BOH']:summary.append(t+'：'+str(countries[t]))
    (out/'说明.txt').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    inputs=[Path(__file__),ROOT/'tools/economy_population_calibration.py',ROOT/'tools/update_m5_integrated_test.ps1',policy_path,employment_path,owner_package/'ownership.json',stage,resident,mapping_path,prior/'package_report.json']
    inputs.extend(sorted((GAME/'common/production_methods').glob('*.txt')))
    report={'status':'population_calibration_static_verified_runtime_pending','update_scope':'m5_population_calibration','version':meta['version'],
        'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),'political_run':political_run,'demographic_run':demographic_run,
        'population_calibrated':True,'source_population_conserved':False,'population_baseline_package':str(prior),'new_campaign_required':True,
        'changed_files':changed,'input_sha256':{str(p):digest(p) for p in inputs},'output_sha256':output}
    write(out/'package_report.json',report)
    write(out/'verification.json',{'status':'passed_static_runtime_pending','population_calibration':verification,
        'literacy':{'status':'passed','all_original_identity_selectors_and_fractional_rates_preserved':True,'national_weighted_rates_recomputed':True,
            'source_absolute_literate_persons_conserved':False,'runtime_verified':False},
        'package_report_sha256':digest(out/'package_report.json'),'audit_sha256':{p.name:digest(p) for p in out.glob('*.json') if p.name!='package_report.json'}})
    print(__import__('json').dumps({'package':str(out),'verification':verification,'ITA':countries['ITA'],'BOH':countries['BOH']},ensure_ascii=False))


if __name__=='__main__':build()
