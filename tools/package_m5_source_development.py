"""Source-driven industrial uplift and developed agricultural land, latest-world overlay."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime
import math
from pathlib import Path
import re
import shutil

from complete_economy import csv_rows
from economy_arable_adjustment import profiles as land_profiles, plan as land_plan
from economy_capacity import write_land, carry_land, Ledger
from economy_development import manufacturing_kinds
from economy_model import building_rows, render_buildings, Target, definitions
from economy_ownership import OwnershipPlanner, province_evidence, vanilla_reference
from economy_source_development import source_evidence, factory_targets, bounded_import_need, same_economic_world
from economy_supply_chain import safe_delta, net_delta, planning_coefficients, planning_balance, household_plan, audit as supply_audit
from m3_world import digest
from package_m4_population_test import parse_pops
from package_m5_arable_adjustment import GEO, adjusted_employment
from package_m5_economic_modules import ROOT,GAME,BUILDINGS,read,write,files,canonical
from package_m5_historical_homelands import population_metadata
from package_m5_population_calibration import find_ancestor, POPS
from package_m5_population_options import original_population_package
from package_m5_supply_chain import load_current, infrastructure

EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')


def try_add(ledger,s,t,kind,wanted,policy,reason):
    """Add supported production, pairing rail capacity where inputs/labor permit."""
    if wanted<=0 or not ledger.allowed(kind,t):return 0
    old=ledger.rows.get((s,t,kind));pms=old['pms'] if old else ledger.pms(kind,t)
    # Current source stock remains intact; only the incremental proposal is screened.
    wanted=min(wanted,ledger.capped_room(s,t,kind,pms))
    target=ledger.target;rows=ledger.local(s,t)
    available=target.infrastructure(s,ledger.population[s,t],ledger.techs[t],rows)
    used=sum(target.infrastructure_usage(r['building'])*r['levels'] for r in rows)
    used+=sum(target.infrastructure_usage({'manor':'building_manor_house','finance':'building_financial_district'}[k])*n for k,n in ledger.owner_levels.get((s,t),{}).items())
    original_gap=max(0,used-available)
    worker_room=max(0,ledger.population[s,t]*ledger.config['workforce_share']-ledger.jobs(s,t))
    c=planning_coefficients(ledger,kind,pms,t)
    owner_reserve=policy['owner_workforce_reserve_per_level']
    owner_infra=max(target.infrastructure_usage('building_manor_house'),target.infrastructure_usage('building_financial_district'))
    railpms=ledger.rows.get((s,t,'building_railway'),{}).get('pms') or ledger.pms('building_railway',t)
    canrail=ledger.allowed('building_railway',t)
    railc=planning_coefficients(ledger,'building_railway',railpms,t)
    railgain=target.infrastructure(s,ledger.population[s,t],ledger.techs[t],rows+[{'building':'building_railway','levels':1,'pms':railpms}])-available-target.infrastructure_usage('building_railway')
    balance=planning_balance(ledger,t)
    for n in range(wanted,0,-1):
        short=max(0,used+n*(target.infrastructure_usage(kind)+owner_infra)-available-original_gap)
        rails=math.ceil(short/railgain) if short and canrail and railgain>0 else 0
        if short and not rails:continue
        if n*(c['jobs']+owner_reserve)+rails*railc['jobs']>worker_room:continue
        delta=net_delta({'inputs':{},'outputs':{}},c,n)
        delta.update(net_delta({'inputs':{},'outputs':{}},railc,rails))
        # Treat upstream suppliers and downstream factories as one expansion
        # package. Otherwise a pre-existing import gap would reject consumers
        # even after their entire incremental input was produced by new suppliers.
        reference=ledger.source_expansion_reference[t]
        combined=Counter({g:balance[g]-reference[g] for g in balance.keys()|reference.keys()})
        combined.update(delta)
        if not safe_delta(ledger,t,combined,reference):
            if reason!='local_source_development_industry_uplift':continue
            after=reference.copy();after.update(combined)
            _,old_household=household_plan(ledger,t,reference);_,new_household=household_plan(ledger,t,after)
            if any(new_household['shortfalls'][g]>old_household['shortfalls'][g]+1e-6 for g in old_household['shortfalls']):continue
            extra_gross=ledger.source_added_output_value[t]+sum(v*target.prices[g] for g,v in c['outputs'].items())*n
            if not bounded_import_need(reference,after,ledger.source_input_reference[t],target.prices,extra_gross,policy):continue
        ledger.add(s,t,kind,n,reason,pms)
        ledger.source_added_output_value[t]+=sum(v*target.prices[g] for g,v in c['outputs'].items())*n
        if rails:ledger.add(s,t,'building_railway',rails,'incremental_industry_transport_support',railpms)
        return n
    return 0


def build(source_path=None,rules_path=None):
    install,prior,report,base,ledger,tags,capacity_policy=load_current()
    rules_path=rules_path or ROOT/'config/personal/economy_source_development.json';rules=read(rules_path)
    original=original_population_package(prior);rawgroups=parse_pops(original)
    rawpop=Counter()
    for k,n in rawgroups.items():rawpop[k[:2]]+=n
    assert set(rawpop)==set(ledger.population)
    current_pop=dict(ledger.population);ledger.population=rawpop
    source_path=source_path or ROOT/'.local/economy/source-1780-v2.json';source=read(source_path)
    mapping=read(Path(report['political_run'])/'conversion_report.json')
    assert source['source_sha256']==mapping['source_sha256']
    stage_path=Path(report['demographic_run'])/'staging/province_population_draft.csv'
    # Reuse the already approved plan when its economic inputs are identical.
    # Re-solving from the expanded stock can otherwise reopen supplier/rail
    # headroom and spend the same import allowance in a different order.
    cursor=prior
    while True:
        completed=read(cursor/'package_report.json')
        if completed.get('update_scope')=='m5_source_development':
            inputs=completed['input_sha256']
            original_hashes={h for p,h in inputs.items() if Path(p).name=='original_population.txt'}
            if (read(cursor/'policy.snapshot.json')==rules and same_economic_world(completed['output_sha256'],report['output_sha256'])
                and inputs.get(str(source_path))==digest(source_path) and inputs.get(str(stage_path))==digest(stage_path)
                and digest(original) in original_hashes):
                print(__import__('json').dumps({'status':'already_applied_unchanged_economic_inputs','approved_plan':str(cursor),
                    'current_package':str(prior),'manufacturing_levels_added':0,'arable_added':0},ensure_ascii=False))
                return
            break
        if not completed.get('prior_package'):break
        cursor=Path(completed['prior_package'])
    stage=list(csv_rows(stage_path));mapping_policy=read(ROOT/'config/personal/economy.json')
    evidence,weights,links=source_evidence(source,stage,EU5,mapping_policy,rules['industry'])
    # Preserve a stable pre-uplift baseline across repeat runs and unrelated updates.
    cursor=prior;baseline_path=base/BUILDINGS
    while True:
        if (cursor/'source_development_baseline_buildings.txt').exists():
            baseline_path=cursor/'source_development_baseline_buildings.txt';break
        p=read(cursor/'package_report.json')
        if not p.get('prior_package'):break
        cursor=Path(p['prior_package'])
    initial=deepcopy(list(ledger.rows.values()));baseline_rows=building_rows(baseline_path)
    manufacturing=manufacturing_kinds(ledger.target)
    targets,industrial_evidence=factory_targets(baseline_rows,evidence,weights,ledger.techs,rules['industry'],manufacturing)
    ledger.supply_chain_policy=capacity_policy['supply_chain']
    before_flows=supply_audit(ledger,tags);before_infra=infrastructure(ledger)
    reference_ledger=Ledger(ledger.target,baseline_rows,rawpop,ledger.techs,ledger.laws,ledger.owners,ledger.british_pms,ledger.config)
    reference_ledger.supply_chain_policy=capacity_policy['supply_chain']
    ledger.source_expansion_reference={t:planning_balance(reference_ledger,t) for t in tags}
    ledger.source_input_reference=defaultdict(Counter);ledger.source_added_output_value=Counter()
    for r in baseline_rows:
        for g,n in planning_coefficients(ledger,r['building'],r['pms'],r['owner'])['inputs'].items():
            ledger.source_input_reference[r['owner']][g]+=n*r['levels']
    baseline_levels={(r['state'],r['owner'],r['building']):r['levels'] for r in baseline_rows}
    for r in initial:
        extra=max(0,r['levels']-baseline_levels.get((r['state'],r['owner'],r['building']),0))
        ledger.source_added_output_value[r['owner']]+=extra*sum(v*ledger.target.prices[g] for g,v in ledger.coefficients(r)['outputs'].items())
    # Resources may support the extra factories, but neither deposits nor farms expand.
    resource_kinds={k for row in ledger.target.states.values() for k in __import__('extract_m3_politics').fields(row.get('capped_resources'))}
    for iteration in range(rules['industry']['passes']):
        start=len(ledger.changes)
        extra_inputs=defaultdict(Counter)
        for (s,t,k),n in targets.items():
            remaining=n-ledger.rows.get((s,t,k),{}).get('levels',0)
            if remaining<=0:continue
            methods=ledger.rows.get((s,t,k),{}).get('pms') or ledger.pms(k,t)
            c=planning_coefficients(ledger,k,methods,t)
            for g,v in c['inputs'].items():extra_inputs[t][g]+=max(0,v-c['outputs'].get(g,0))*remaining
        for t,inputs in sorted(extra_inputs.items()):
            for good,demand in sorted(inputs.items()):
                need=max(0,demand-max(0,planning_balance(ledger,t)[good]))
                if not need:continue
                for kind in capacity_policy['input_support']['goods'].get(good,[]):
                    if kind not in resource_kinds:continue
                    choices=sorted((s for s,tag in ledger.population if tag==t and ledger.rows.get((s,t,kind))),
                                   key=lambda s:(-ledger.rows[s,t,kind]['levels'],s))
                    for s in choices:
                        row=ledger.rows[s,t,kind];c=ledger.coefficients(row)
                        output=c['outputs'].get(good,0)-c['inputs'].get(good,0)
                        if output<=0:continue
                        n=try_add(ledger,s,t,kind,math.ceil(need/output),rules['industry'],'source_industry_incremental_raw_material_support')
                        need=max(0,need-n*output)
                        if not need:break
        for (s,t,k),n in sorted(targets.items(),key=lambda kv:(kv[0][2] not in ('building_tooling_workshop','building_steel_mill','building_motor_industry'),kv[0])):
            if t not in tags:continue
            old=ledger.rows.get((s,t,k),{}).get('levels',0)
            try_add(ledger,s,t,k,n-old,rules['industry'],'local_source_development_industry_uplift')
        print(f'Industry pass {iteration+1}: {len(ledger.changes)-start} changes',flush=True)
        if len(ledger.changes)==start:break
    provinces=province_evidence(stage,source)
    ledger.ownership=OwnershipPlanner(ledger,provinces,tags,capacity_policy['ownership'],vanilla_reference(ledger.target,capacity_policy['ownership']))
    ledger.ownership.apply();ownership=ledger.ownership.audit()
    ledger.owner_levels={(h['state'],h['country']):h['referenced_owned_levels'] for h in ownership['owner_hosts']}
    # Audit all inhabited world parts, including generated tribes and fallback residents.
    _,employment=carry_land(ledger,Counter(),set(ledger.techs))
    vanilla=Target(GAME);land_policy=read(ROOT/'config/personal/economy_arable_adjustment.json')
    land_policy.update(rules['arable']);geo=land_profiles(source,stage,GEO,land_policy)
    changes,land_evidence=land_plan(vanilla,ledger.owners,employment,geo)
    # Existing reviewed geographic adjustments remain a floor; no repeated multiplication.
    desired={s:max(int(f.get('arable_land',0)),changes.get(s,int(vanilla.states[s].get('arable_land',0)))) for s,f in ledger.target.states.items() if 'arable_land' in f}
    for s,n in desired.items():ledger.target.states[s]['arable_land']=str(n)
    employment=adjusted_employment(employment,desired,ledger.owners)
    for r in employment:
        s,t=r['state'],r['country'];r['population']=current_pop[s,t];r['estimated_workforce']=round(current_pop[s,t]*.25)
        owner=ledger.ownership_jobs.get((s,t),0)
        r['capacity_gap_full_staffing']=max(0,r['estimated_workforce']-r['formal_job_capacity']-r['new_subsistence_job_capacity'])
        r['capacity_gap_safety_staffing']=max(0,math.ceil(r['population']*.25-(r['formal_job_capacity']-owner)*.75-owner-r['new_subsistence_job_capacity']))
    out=ROOT/'.local/economy/packages'/('m5-source-development-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(base,mod)
    shutil.copy2(baseline_path,out/'source_development_baseline_buildings.txt')
    (mod/BUILDINGS).write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    land_files=write_land(ledger.target,base,mod,desired)
    actual=building_rows(mod/BUILDINGS);ledger.ownership.verify(actual)
    before_states={**vanilla.states,**definitions(base/'map_data/state_regions')}
    actual_states={**vanilla.states,**definitions(mod/'map_data/state_regions')}
    for s,f in actual_states.items():
        def nonland(v):return {k:canonical(x) if hasattr(x,'entries') else x for k,x in v.items() if k!='arable_land'}
        assert nonland(f)==nonland(before_states[s]),'Non-arable geography changed: '+s
        if s in desired:assert int(f['arable_land'])==desired[s]
    after_infra=infrastructure(ledger);old_infra={(v['state'],v['country']):v for v in before_infra}
    assert all(v['gap']<=old_infra[v['state'],v['country']]['gap']+1e-5 for v in after_infra),'New infrastructure overload'
    assert not any(h['safety_staffing_excess_jobs']>1e-5 for h in ownership['owner_hosts']),'New owner workforce overload'
    old_lookup={(r['state'],r['owner'],r['building']):r for r in initial}
    for r in actual:
        key=r['state'],r['owner'],r['building'];old=old_lookup.get(key)
        if old:assert r['levels']>=old['levels']
        if r['building'] not in manufacturing|resource_kinds|{'building_railway'}:
            assert old and r['levels']==old['levels'] and r['pms']==old['pms']
            if __import__('economy_ownership').sector(ledger.target,r['building']) is None:
                assert canonical(__import__('pdx_text').root(r['body']))==canonical(__import__('pdx_text').root(old['body']))
        if not old or r['levels']!=old['levels']:
            assert ledger.allowed(r['building'],r['owner'])
            assert all(ledger.target.available(pm,ledger.techs[r['owner']],ledger.laws[r['owner']]) for pm in r['pms'])
    after_flows=supply_audit(ledger,tags)
    import_increases=[]
    for t,b in before_flows.items():
        a=after_flows[t]
        for g,n in a['domestic_input_gaps_with_scenario'].items():
            delta=max(0,n-b['domestic_input_gaps_with_scenario'].get(g,0))
            assert delta<=ledger.source_input_reference[t][g]*rules['industry']['maximum_extra_input_import_fraction']+1e-5,(t,g,delta)
            if delta:import_increases.append({'country':t,'good':g,'extra_domestic_gap':delta,'baseline_input':ledger.source_input_reference[t][g]})
    meta=read(mod/'.metadata/metadata.json');v=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',report['version']);assert v
    a,b,c,d=map(int,v.groups());meta['version']=f'{a}.{b}.{c+1}-m5-test{d+1}';write(mod/'.metadata/metadata.json',meta)
    output=files(mod);changed=sorted(p for p,h in output.items() if report['output_sha256'].get(p)!=h)
    assert set(output)==set(report['output_sha256']) and set(changed)<={BUILDINGS,'.metadata/metadata.json',*land_files}
    assert output[POPS]==report['output_sha256'][POPS]
    compare={}
    for t in sorted(tags):
        old=sum(r['levels'] for r in initial if r['owner']==t and r['building'] in manufacturing)
        new=sum(r['levels'] for r in actual if r['owner']==t and r['building'] in manufacturing)
        compare[t]={'name':mapping['countries'][t].get('name_simp_chinese',t),'manufacturing_before':old,'manufacturing_after':new,'added':new-old}
    previous_states={**vanilla.states,**definitions(base/'map_data/state_regions')}
    land_compare=[{'state':s,'before':int(previous_states[s].get('arable_land',0)),
                   'after':n,'vanilla':int(vanilla.states[s].get('arable_land',0))} for s,n in desired.items() if n!=int(previous_states[s].get('arable_land',0))]
    check={'status':'passed','all_country_rules_dynamic':True,'no_mineral_capacity_change':True,'no_new_commercial_farms':True,
           'military_and_unrelated_files_unchanged':True,'extra_import_dependence_within_policy':True,'original_population_unchanged':True,
           'no_new_infrastructure_or_owner_workforce_overload':True,
           'manufacturing_levels_added':sum(v['added'] for v in compare.values()),'land_states_changed':len(land_compare),
           'arable_added':sum(r['after']-r['before'] for r in land_compare),'runtime_verified':False}
    for name,value in [('source_development_verification.json',check),('country_industry_comparison.json',compare),('industry_evidence.json',industrial_evidence),
          ('factory_targets.json',[{'state':s,'country':t,'building':k,'target_levels':n,'actual_levels':ledger.rows.get((s,t,k),{}).get('levels',0)} for (s,t,k),n in sorted(targets.items())]),
          ('land_comparison.json',land_compare),('land_evidence.json',land_evidence),('policy.snapshot.json',rules),('employment.json',employment),('ownership.json',ownership),
          ('ownership_provinces.json',list(provinces.values())),('changes.json',ledger.changes),('supply_chain.json',{'before':before_flows,'after':after_flows}),
          ('extra_import_needs.json',import_increases),('infrastructure.json',{'before':before_infra,'after':after_infra})]:write(out/name,value)
    inputs=[Path(__file__),ROOT/'tools/economy_source_development.py',ROOT/'tools/economy_arable_adjustment.py',ROOT/'tools/economy_supply_chain.py',ROOT/'tools/economy_ownership.py',ROOT/'tools/update_m5_integrated_test.ps1',rules_path,
            ROOT/'config/personal/economy_arable_adjustment.json',ROOT/'config/personal/economy_capacity.json',source_path,stage_path,original,baseline_path,prior/'package_report.json']
    new={'status':'source_development_static_verified_runtime_pending','update_scope':'m5_source_development','version':meta['version'],'mod_name':meta['name'],
         'mod_directory':str(mod),'prior_package':str(prior),'political_run':report['political_run'],'demographic_run':report['demographic_run'],
         'new_campaign_required':True,'changed_files':changed,'output_sha256':output,'input_sha256':{str(p):digest(p) for p in inputs},
         **population_metadata(prior,output[POPS])}
    write(out/'package_report.json',new)
    write(out/'verification.json',{'status':'passed_static_runtime_pending','source_development':check,'literacy':read(prior/'verification.json')['literacy'],
        'package_report_sha256':digest(out/'package_report.json'),'audit_sha256':{p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('package_report.json','verification.json')}})
    assert read(ROOT/'.local/economy/installation-latest.json')==install,'Installed baseline changed during build'
    print(__import__('json').dumps({'package':str(out),'verification':check,'examples':{t:compare[t] for t in ['ITA','BOH','E84'] if t in compare},'sumatra_land':[r for r in land_compare if r['state'] in ('STATE_ACEH','STATE_NORTH_SUMATRA','STATE_SOUTH_SUMATRA')]},ensure_ascii=False))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,help='Extracted EU5 economy JSON matching the current political/demographic conversion')
    parser.add_argument('--config',type=Path,help='Source development rule configuration')
    args=parser.parse_args();build(args.source,args.config)
