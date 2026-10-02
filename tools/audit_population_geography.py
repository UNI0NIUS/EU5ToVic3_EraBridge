"""Compare identical V3 state geography; diagnose population and split-state inflation.

The review overlay preserves current politics/population and applies only geography
limits. It is deliberately NOT installed and is not an equilibrium/famine test.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
from economy_model import Target, apportioned, building_rows, definitions, render_buildings
from economy_capacity import Ledger, carry_land, write_land
from economy_geography import constrain_existing, local_limit
from extract_m3_politics import fields
from pdx_text import Object, root
from build_m3_world import load_localization
from build_economy import expand_template_tech
from complete_economy import active_laws

ROOT=Path(__file__).resolve().parents[1]
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def csv_rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)


def population_history(directory):
    result=Counter()
    for path in sorted(Path(directory).glob('*.txt')):
        for state,obj in fields(root(path.read_text(encoding='utf-8-sig')))['POPS'].entries():
            for owner,part in obj.entries():
                for key,pop in part.entries():
                    if key!='create_pop':raise ValueError('Unsupported population operation: '+key)
                    result[state.removeprefix('s:'),owner.removeprefix('region_state:')]+=int(fields(pop)['size'])
    return result


def build(game,installed,prior,demographic,political,output):
    if output.exists():raise ValueError('Refusing to overwrite audit')
    output.mkdir(parents=True)
    target=Target(game);owners=load(political/'province_owners.json')
    country_defs=load(political/'conversion_report.json')['countries']
    tags={t for t,c in country_defs.items() if c['source_id'] is not None}
    original=population_history(game/'common/history/pops');current=population_history(installed/'common/history/pops')
    before,after=Counter(),Counter()
    for (s,t),n in original.items():before[s]+=n
    for (s,t),n in current.items():after[s]+=n
    installed_states=definitions(installed/'map_data/state_regions')
    previous_states=definitions(prior/'overlay/map_data/state_regions')
    assert all(fields(installed_states.get(s,f).get('capped_resources'))==fields(previous_states.get(s,f).get('capped_resources')) and
               installed_states.get(s,f).get('arable_land')==previous_states.get(s,f).get('arable_land') for s,f in target.states.items())
    locale=load_localization(game/'localization/simp_chinese');locale.update(load_localization(installed/'localization/simp_chinese'))
    loc=lambda s:locale.get(s,s)
    classes=Counter();source_places=defaultdict(Counter);staged=Counter()
    for r in csv_rows(demographic/'staging/province_population_draft.csv'):
        s,t=r['target_state'],r['target_owner'];n=int(r['centipersons'])
        staged[s]+=n;classes[s,t,r['source_class']]+=n/100;source_places[s][r['source_location']]+=n/100
    template=Counter()
    for r in csv_rows(demographic/'template_fallback/template_population_groups.csv'):template[r['state']]+=int(r['persons'])
    stage_report=load(demographic/'staging/staging_report.json')
    assert sum(staged.values())==stage_report['world_centipersons']==stage_report['allocated_centipersons']
    # Independently reconcile installed integer population against demographic output.
    expected=Counter()
    for r in csv_rows(demographic/'demographics/resident_population_groups.csv'):expected[r['state'],r['owner']]+=int(r['preview_integer_persons'])
    for r in csv_rows(demographic/'template_fallback/template_population_groups.csv'):expected[r['state'],r['owner']]+=int(r['persons'])
    assert expected==current,'Installed population differs from demographic output'
    history={k[2:]:o for k,o in fields(root((installed/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects={k:o for k,o in root((game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(o,Object)}
    techs={t:expand_template_tech(o,effects,target) for t,o in history.items()}
    target.global_technologies=set().union(*techs.values())
    laws={t:active_laws(o,target,country_defs[t]) for t,o in history.items()}
    british=defaultdict(set)
    for r in load(ROOT/'.local/economy/run-006/british_baseline.json')['buildings']:british[r['building']].update(r['pms'])
    config=load(ROOT/'config/personal/economy_capacity.json')['employment']
    assert config['geography_policy']=='vanilla_capacity'
    rows=building_rows(installed/'common/history/buildings/00_eu5_world.txt')
    ledger=Ledger(target,rows,current,techs,laws,owners,british,config)
    ledger.source_classes=classes
    for r in load(prior/'employment.json'):
        ledger.source_paid_agriculture[r['state'],r['country']]=r['source_paid_agriculture_person_equivalents']
    ledger.isolated_states={(s,r['country']) for r in load(prior/'market_connections.json') if not r['has_local_port_connection'] for s in r['states']}
    adjustments=constrain_existing(ledger)
    land,employment=carry_land(ledger,classes,tags)
    assert not land
    overlay=output/'review_overlay'
    # Reset only capacity fields in the current installed state files, retaining other edits.
    baseline_land={s:int(f.get('arable_land',0)) for s,f in target.states.items() if 'arable_land' in f}
    reset_resources={s:True for s,f in target.states.items() if fields(installed_states.get(s,f).get('capped_resources'))!=fields(f.get('capped_resources'))}
    write_land(target,installed,overlay,baseline_land,reset_resources)
    path=overlay/'common/history/buildings/00_eu5_world.txt';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    readback=building_rows(path)
    assert {(r['state'],r['owner'],r['building']):r['levels'] for r in readback}=={k:r['levels'] for k,r in ledger.rows.items()}
    for s,t in current:
        local=ledger.local(s,t)
        assert sum(r['levels'] for r in local if r['building'] in ledger.arable_kinds)<=apportioned(Counter(owners[s].values()),int(target.states[s].get('arable_land',0))).get(t,0)
        for r in local:
            limit=local_limit(ledger,s,t,r['building'])
            assert limit is None or r['building'] in ledger.arable_kinds or r['levels']<=limit
    for s,f in definitions(overlay/'map_data/state_regions').items():
        assert int(f.get('arable_land',0))==int(target.states[s].get('arable_land',0))
        assert fields(f.get('capped_resources'))==fields(target.states[s].get('capped_resources'))
    prior_employment=defaultdict(list);employment_by_state=defaultdict(list)
    for r in load(prior/'employment.json'):prior_employment[r['state']].append(r)
    for r in employment:employment_by_state[r['state']].append(r)
    adjustments_by_state=defaultdict(list)
    for r in adjustments:adjustments_by_state[r['state']].append(r)
    old_resource_details=load(ROOT/'outputs/economy-land-resource-20261002/comparison.json')['resources']
    resources_by_state=defaultdict(list)
    current_built=Counter();review_built=Counter()
    for r in rows:current_built[r['state'],r['building']]+=r['levels']
    for r in readback:review_built[r['state'],r['building']]+=r['levels']
    for r in old_resource_details:
        s=r['state'];k=r['resource'];basecap=int(fields(target.states[s].get('capped_resources')).get(k,0))
        assert r['before']==basecap and r['after']==int(fields(installed_states[s].get('capped_resources')).get(k,0))
        aggregate=max(basecap,sum(x['requested'] for x in r['allocations']))
        resources_by_state[s].append({'resource':k,'name':loc(k),'original':basecap,'previous':r['after'],'revised':basecap,
            'aggregate_demand_without_fragment_multiplier':aggregate,'split_amplification':max(0,r['after']-aggregate),
            'current_built':current_built[s,k],'review_built':review_built[s,k]})
    parts=[];territory_reference=Counter()
    for s in owners:
        allocated=apportioned(Counter(owners[s].values()),before[s])
        for t,n in allocated.items():
            territory_reference[t]+=n
            if (s,t) in current:parts.append({'state':s,'name':loc(s),'country':t,'country_name':loc(t),'original_estimate':n,'current':current[s,t],
                        'ratio':current[s,t]/n if n else None})
    states=[]
    for s in sorted(set(before)|set(after)):
        f=target.states[s];origland=int(f.get('arable_land',0));prevland=int(installed_states.get(s,f).get('arable_land',0))
        old_parts=prior_employment[s];represented={r['country'] for r in old_parts}
        baseline_shares=apportioned(Counter(owners[s].values()),origland)
        aggregate=max(origland,sum(r['required_arable_share'] for r in old_parts)+sum(v for t,v in baseline_shares.items() if t not in represented))
        states.append({'state':s,'name':loc(s),'countries':sorted(set(owners[s].values())),
            'original_population':before[s],'current_population':after[s],'population_delta':after[s]-before[s],
            'population_ratio':after[s]/before[s] if before[s] else None,
            'source_population':staged[s]/100,'template_population':template[s],
            'original_land':origland,'previous_land':prevland,'revised_land':origland,
            'aggregate_land_demand_without_fragment_multiplier':aggregate,
            'land_split_amplification':max(0,prevland-aggregate),
            'land_ratio':prevland/origland if origland else None,
            'source_places':[{'location':k,'population':v} for k,v in source_places[s].most_common()],
            'employment':employment_by_state[s],'building_adjustments':adjustments_by_state[s],
            'resources':resources_by_state[s],
            'employment_gap':sum(r['capacity_gap_full_staffing'] for r in employment_by_state[s]),
            'safety_gap':sum(r['capacity_gap_safety_staffing'] for r in employment_by_state[s])})
    countries={}
    for tag in ['ITA','BOH']:
        countries[tag]={'name':loc(tag),'original_same_territory_estimate':territory_reference[tag],
            'current_population':sum(n for (s,t),n in current.items() if t==tag),
            'employment_gap':sum(r['capacity_gap_full_staffing'] for r in employment if r['country']==tag),
            'safety_gap':sum(r['capacity_gap_safety_staffing'] for r in employment if r['country']==tag),
            'removed_building_levels':sum(r['before']-r['after'] for r in adjustments if r['country']==tag)}
    stats={'original_population':sum(before.values()),'current_population':sum(after.values()),
        'source_population':sum(staged.values())/100,'template_population':sum(template.values()),
        'rounding_difference':round(sum(after.values())-sum(staged.values())/100-sum(template.values()),2),
        'states':len(states),'growing_states':sum(r['population_delta']>0 for r in states),
        'double_states':sum((r['population_ratio'] or 0)>=2 for r in states),'tenfold_states':sum((r['population_ratio'] or 0)>=10 for r in states),
        'original_land':sum(r['original_land'] for r in states),'previous_land':sum(r['previous_land'] for r in states),
        'land_split_amplification':sum(r['land_split_amplification'] for r in states),
        'resource_split_amplification':sum(r['split_amplification'] for rs in resources_by_state.values() for r in rs),
        'removed_building_levels':sum(r['before']-r['after'] for r in adjustments),
        'employment_gap_workers':sum(r['capacity_gap_full_staffing'] for r in employment),
        'employment_gap_parts':sum(r['capacity_gap_full_staffing']>0 for r in employment)}
    tracked=[*sorted((game/'common/history/pops').glob('*.txt')), installed/'common/history/pops/00_eu5_world.txt',
             installed/'common/history/buildings/00_eu5_world.txt',installed/'common/history/countries/00_eu5_world.txt',
             *sorted((installed/'map_data/state_regions').glob('*.txt')),political/'province_owners.json',
             demographic/'staging/province_population_draft.csv',ROOT/'config/personal/economy_capacity.json']
    data={'installed_version':load(installed/'.metadata/metadata.json')['version'],'status':'review_not_installed_balance_unresolved',
        'stats':stats,'states':states,'parts':parts,'countries':countries,
        'policy':{'geography':'Keep original V3 arable land and fixed resource limits; no population or border multiplier.',
            'workforce':config['workforce_share'],'staffing':config['formal_staffing_safety_fraction'],
            'population':'Unchanged; source census conserved. Original population split by current province count is only an estimate.',
            'review_scope':'Current installed buildings fitted to original caps; no new industry, migration, law, fiscal or market rebalance.',
            'rural_employment_precision':'Source paid agriculture uses the prior rounded audit; population comparison and geographic caps are exact.'},
        'verified':{'population_matches_demographic_output':True,'source_allocation_conserved':True,'capacity_overlay_matches_original':True,'buildings_fit_caps':True},
        'input_sha256':{str(p.resolve()):sha(p) for p in tracked}}
    write(output/'comparison.json',data)
    (output/'人口与容量修正规则对照.html').write_text((ROOT/'tools/population_geography_comparison.html').read_text(encoding='utf-8').replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/')),encoding='utf-8')
    write(output/'review_manifest.json',{'status':data['status'],'prior_economy':str(prior.resolve()),'installed_version':data['installed_version'],
        'inputs':data['input_sha256'],'outputs':{p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}})
    print(json.dumps({'stats':stats,'countries':countries},ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ['game','installed','prior','demographic','political','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.game,a.installed,a.prior,a.demographic,a.political,a.output)
