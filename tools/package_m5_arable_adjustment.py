"""Final arable-only overlay; run after productive-building/ownership conversion.

Uses original capacities and an immutable original employment ledger, so applying
the same policy twice does not compound land. All building history is preserved.
"""
from collections import Counter
from datetime import datetime
import math
from pathlib import Path
import re
import shutil

from complete_economy import csv_rows
from economy_arable_adjustment import profiles, plan
from economy_capacity import write_land
from economy_model import Target, apportioned, definitions
from extract_m3_politics import fields
from package_m5_economic_modules import ROOT, GAME, BUILDINGS, read, write, files, canonical
from m3_world import digest
from pdx_text import root, Object

GEO=Path('D:/Steam/steamapps/common/Europa Universalis V/game/in_game/map_data/location_templates.txt')


def adjusted_employment(rows, changes, owners):
    output=[]
    for r in rows:
        r=dict(r);s,t=r['state'],r['country']
        if s in changes:
            land=apportioned(Counter(owners[s].values()),changes[s])[t]
            r['new_arable_share']=land
            r['new_subsistence_job_capacity']=max(0,land-r['commercial_arable_levels'])*r['subsistence_jobs_per_level']
            r['capacity_gap_full_staffing']=max(0,r['estimated_workforce']-r['formal_job_capacity']-r['new_subsistence_job_capacity'])
            r['capacity_gap_safety_staffing']=max(0,math.ceil(r['population']*.25-r['formal_job_capacity']*r['formal_staffing_credit']-r['new_subsistence_job_capacity']))
            r['unmet_arable_demand']=max(0,r['required_arable_share']-land)
        r['geography_policy']='bounded_historical_arable_correction'
        output.append(r)
    return output


def build():
    installation=read(ROOT/'.local/economy/installation-latest.json')
    prior=Path(installation['package']);previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    assert files(base)==previous['output_sha256']
    assert files(Path(installation['target']))==previous['output_sha256']
    # The input ledger must describe the same productive buildings as installed.
    anchor=prior
    while not (anchor/'employment.json').exists():anchor=Path(read(anchor/'package_report.json')['prior_package'])
    anchor_report=read(anchor/'package_report.json')
    assert anchor_report['output_sha256'][BUILDINGS]==previous['output_sha256'][BUILDINGS], 'Regenerate employment for changed productive buildings'
    original_ledger=anchor/('original_employment.json' if (anchor/'original_employment.json').exists() else 'employment.json')
    employment=read(original_ledger)
    policy_path=ROOT/'config/personal/economy_arable_adjustment.json';policy=read(policy_path)
    source_path=ROOT/'.local/economy/source-1780-v2.json'
    stage=Path(previous['demographic_run'])/'staging/province_population_draft.csv'
    owners_path=Path(previous['political_run'])/'province_owners.json';owners=read(owners_path)
    target=Target(GAME)
    assert set(policy['historical_overrides'])|set(policy['restricted_state_ceiling'])<=target.states.keys()
    evidence=profiles(read(source_path),csv_rows(stage),GEO,policy)
    changes,rows=plan(target,owners,employment,evidence)
    updated=adjusted_employment(employment,changes,owners)
    out=ROOT/'.local/economy/packages'/('m5-arable-adjustment-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(base,mod)
    # Explicit original+correction land resets any prior application instead of
    # adding another increment. write_land leaves all resource blocks untouched.
    desired={s:int(f['arable_land']) for s,f in target.states.items() if 'arable_land' in f}
    desired.update(changes)
    land_files=write_land(target,base,mod,desired)
    actual=definitions(mod/'map_data/state_regions')
    before=definitions(base/'map_data/state_regions')
    for s,v in actual.items():
        if s in desired:assert int(v['arable_land'])==desired[s]
        old=before.get(s,target.states[s])
        def nonland(f):return {k:canonical(v) if isinstance(v,Object) else v for k,v in f.items() if k!='arable_land'}
        assert nonland(v)==nonland(old), 'Non-arable geography changed: '+s
    assert all(r['original_arable']<=r['new_arable']<=r['bounded_ceiling']<=math.floor(r['original_arable']*1.5) for r in rows)
    assert plan(target,owners,employment,evidence)[0]==changes
    old_lookup={(r['state'],r['country']):r for r in employment}
    for r in updated:
        old=old_lookup[r['state'],r['country']]
        assert r['new_arable_share']>=old['new_arable_share']
        assert r['capacity_gap_safety_staffing']<=old['capacity_gap_safety_staffing']
    meta=read(mod/'.metadata/metadata.json')
    match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',previous['version']);assert match
    major,minor,patch,test=map(int,match.groups());meta['version']=f'{major}.{minor}.{patch+1}-m5-test{test+1}'
    write(mod/'.metadata/metadata.json',meta)
    output=files(mod);changed=sorted(p for p,h in output.items() if previous['output_sha256'].get(p)!=h)
    assert set(output)==set(previous['output_sha256'])
    assert set(changed)<={'.metadata/metadata.json',*land_files}
    countries={}
    for t in sorted({r['country'] for r in employment}):
        old=[r for r in employment if r['country']==t];new=[r for r in updated if r['country']==t]
        countries[t]={'arable_before':sum(r['new_arable_share'] for r in old),'arable_after':sum(r['new_arable_share'] for r in new),
            'safety_gap_before':sum(r['capacity_gap_safety_staffing'] for r in old),'safety_gap_after':sum(r['capacity_gap_safety_staffing'] for r in new)}
        countries[t]['additional_usable_worker_capacity']=countries[t]['safety_gap_before']-countries[t]['safety_gap_after']
    check={'status':'passed','only_arable_and_metadata_changed':True,'resources_buildings_population_unchanged':True,
        'within_historical_geographic_ceiling':True,'split_state_original_shares_preserved':True,'idempotent_from_original':True,
        'changed_states':len(changes),'extra_arable':sum(r['extra_arable'] for r in rows),
        'mapped_original_arable':sum(r['original_arable'] for r in rows),'runtime_verified':False}
    for name,value in [('arable_verification.json',check),('arable_adjustments.json',rows),('province_arable_evidence.json',evidence),
        ('original_employment.json',employment),('employment.json',updated),('country_subsistence_capacity.json',countries),('arable_policy.snapshot.json',policy)]:write(out/name,value)
    text=[f"耕地修正版 {meta['version']}",f"{len(changes)} 州增加 {check['extra_arable']} 点耕地；矿藏、建筑等级、人口分布保持原值。",
        '规则：原版耕地为基数，逐省地形气候、原存档开发度和作物/灌溉证据限制增幅；历史个案单独记录。',
        '一般地区按规则只增少量；全局硬上限 +50%，不是统一增加50%。失业需求不能提高上限。',
        '新增耕地开局留给自给农业；不直接修改人口职业，不增加商业农场。具体百分比是游戏性设定，非史料统计。',
        '意大利：预计额外可用岗位 '+str(round(countries['ITA']['additional_usable_worker_capacity']))+'；波西米亚 '+str(round(countries['BOH']['additional_usable_worker_capacity']))+'。',
        '以上为按25%劳动力、75%正规岗位安全折算的容量，不等于实测新增就业；没有以消除全部失业为目标无限扩地。',
        '需新开局；旧存档的州耕地不会由历史文件自动重建。政府开支建筑不变，新增自给农和庄园初始化、物价、税收仍需运行验证。',
        '复现：先完成生产建筑和所有权转换，再运行 tools/package_m5_arable_adjustment.py。重复运行不会叠加耕地。']
    (out/'说明.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
    inputs=[Path(__file__),ROOT/'tools/economy_arable_adjustment.py',ROOT/'tools/update_m5_integrated_test.ps1',policy_path,source_path,GEO,stage,owners_path,original_ledger,prior/'package_report.json']
    inputs.extend(sorted((GAME/'map_data/state_regions').glob('*.txt')))
    report={'status':'arable_adjustment_static_verified_runtime_pending','update_scope':'m5_arable_adjustment','version':meta['version'],'mod_name':meta['name'],
        'mod_directory':str(mod),'prior_package':str(prior),'political_run':previous['political_run'],'demographic_run':previous['demographic_run'],
        'employment_anchor':str(anchor),'new_campaign_required':True,'changed_files':changed,'input_sha256':{str(p):digest(p) for p in inputs},'output_sha256':output}
    write(out/'package_report.json',report)
    write(out/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],'arable_adjustment':check,
        'package_report_sha256':digest(out/'package_report.json'),'audit_sha256':{p.name:digest(p) for p in out.glob('*.json') if p.name!='package_report.json'}})
    print(__import__('json').dumps({'package':str(out),'verification':check,'ITA':countries['ITA'],'BOH':countries['BOH']},ensure_ascii=False))


if __name__=='__main__':build()
