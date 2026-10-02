"""Compose the complete 1337 candidate, using current generic capacity policies."""
from converter_source_world import *
import math
from copy import deepcopy
from economy_model import Target,definitions,building_rows,render_buildings
from build_economy import expand_template_tech
from complete_economy import active_laws
from economy_capacity import Ledger,carry_land,write_land
from economy_ownership import OwnershipPlanner,province_evidence,vanilla_reference
from economy_development import manufacturing_kinds
from economy_source_development import source_evidence,factory_targets
from economy_supply_chain import planning_balance,planning_coefficients,audit as supply_audit
from package_m5_source_development import try_add
from economy_arable_adjustment import profiles,plan as land_plan
from package_m5_arable_adjustment import adjusted_employment
from package_m4_population_test import parse_pops

def build():
 package=RUN/'complete';mod=package/'eu5_converted'
 if mod.exists():raise ValueError('Complete candidate directory already exists')
 shutil.copytree(RUN/'base/eu5_converted',mod)
 shutil.copytree(RUN/'capacity/overlay',mod,dirs_exist_ok=True)
 # Freeze reusable cultural assets and apply the newly reviewed family grouping.
 prior=ASSETS
 identity_assets(mod,prior)
 shutil.copytree(RUN/'demographic/migrant_assets',mod,dirs_exist_ok=True)
 # Population overlays can retain older definitions with the same identity keys.
 # Normalize before Target/source-claim readers reject duplicate definitions.
 from converter_identity_assets import sync
 sync(mod,ASSETS)
 from v3_startup_validation import culture_modifiers,flag_assets
 culture_modifiers(GAME,mod,write=True)
 flag_assets(GAME,mod,EU5)
 policy=read(ROOT/'config/personal/economy_capacity.json');rules=read(ROOT/'config/personal/economy_source_development.json')
 mapping=read(RUN/'political/conversion_report.json');source=read(RUN/'source/economy.json');owners=read(RUN/'political/province_owners.json')
 stage=list(rows(RUN/'demographic/staging/province_population_draft.csv'));groups=parse_pops(mod/'common/history/pops/00_eu5_world.txt');population=Counter()
 for k,n in groups.items():population[k[:2]]+=n
 target=Target(GAME);target.states.update(definitions(mod/'map_data/state_regions'));target._law_definitions={k:fields(o) for k,o in defs(mod,'laws').items()};target._law_effects={k:o for k,o in objects(root((GAME/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig')))}
 effects={k:o for k,o in objects(root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')))}
 history={k[2:]:o for k,o in objects(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['COUNTRIES'])}
 techs={t:expand_template_tech(o,effects,target) for t,o in history.items()};laws={t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()};target.global_technologies=set().union(*techs.values())
 baseline=building_rows(mod/'common/history/buildings/00_eu5_world.txt');ledger=Ledger(target,baseline,population,techs,laws,owners,defaultdict(set),policy['employment']);ledger.supply_chain_policy=policy['supply_chain']
 old_ownership=read(RUN/'capacity/ownership.json');ledger.ownership_jobs={(r['state'],r['country']):r['estimated_owner_jobs'] for r in old_ownership['owner_hosts']}
 ledger.owner_levels={(r['state'],r['country']):r['referenced_owned_levels'] for r in old_ownership['owner_hosts']}
 tags={t for t,c in mapping['countries'].items() if c['source_id'] is not None}
 evidence,weights,links=source_evidence(source,stage,EU5,read(ROOT/'config/personal/economy.json'),rules['industry'])
 manufacturing=manufacturing_kinds(target);targets,industrial=factory_targets(baseline,evidence,weights,techs,rules['industry'],manufacturing)
 reference=Ledger(target,deepcopy(baseline),population,techs,laws,owners,defaultdict(set),policy['employment']);reference.supply_chain_policy=policy['supply_chain']
 ledger.source_expansion_reference={t:planning_balance(reference,t) for t in tags};ledger.source_input_reference=defaultdict(Counter);ledger.source_added_output_value=Counter()
 for r in baseline:
  for g,n in planning_coefficients(ledger,r['building'],r['pms'],r['owner'])['inputs'].items():ledger.source_input_reference[r['owner']][g]+=n*r['levels']
 resources={k for f in target.states.values() for k in fields(f['capped_resources'])} if all('capped_resources' in f for f in target.states.values()) else {k for f in target.states.values() if 'capped_resources' in f for k in fields(f['capped_resources'])}
 for iteration in range(rules['industry']['passes']):
  start=len(ledger.changes);inputs=defaultdict(Counter)
  for (s,t,k),n in targets.items():
   remaining=n-ledger.rows.get((s,t,k),{}).get('levels',0)
   if remaining<=0:continue
   methods=ledger.rows.get((s,t,k),{}).get('pms') or ledger.pms(k,t);co=planning_coefficients(ledger,k,methods,t)
   for g,v in co['inputs'].items():inputs[t][g]+=max(0,v-co['outputs'].get(g,0))*remaining
  for t,gs in sorted(inputs.items()):
   for good,demand in sorted(gs.items()):
    need=max(0,demand-max(0,planning_balance(ledger,t)[good]))
    for kind in policy['input_support']['goods'].get(good,[]):
     if not need or kind not in resources:continue
     choices=sorted((s for s,tag in population if tag==t and ledger.rows.get((s,t,kind))),key=lambda s:(-ledger.rows[s,t,kind]['levels'],s))
     for s in choices:
      co=ledger.coefficients(ledger.rows[s,t,kind]);produced=co['outputs'].get(good,0)-co['inputs'].get(good,0)
      if produced>0:need=max(0,need-try_add(ledger,s,t,kind,math.ceil(need/produced),rules['industry'],'source_industry_incremental_raw_material_support')*produced)
  for (s,t,k),n in sorted(targets.items(),key=lambda kv:(kv[0][2] not in ('building_tooling_workshop','building_steel_mill','building_motor_industry'),kv[0])):
   if t in tags:try_add(ledger,s,t,k,n-ledger.rows.get((s,t,k),{}).get('levels',0),rules['industry'],'local_source_development_industry_uplift')
  print('Industry supplement',iteration+1,len(ledger.changes)-start,flush=True)
  if len(ledger.changes)==start:break
 ledger.ownership=OwnershipPlanner(ledger,province_evidence(stage,source),tags,policy['ownership'],vanilla_reference(target,policy['ownership']));ledger.ownership.apply();ownership=ledger.ownership.audit()
 ledger.owner_levels={(r['state'],r['country']):r['referenced_owned_levels'] for r in ownership['owner_hosts']}
 _,employment=carry_land(ledger,Counter(),set(techs))
 vanilla=Target(GAME);lp=read(ROOT/'config/personal/economy_arable_adjustment.json');lp.update(rules['arable']);geo=profiles(source,stage,EU5/'in_game/map_data/location_templates.txt',lp);changes,land_evidence=land_plan(vanilla,owners,employment,geo)
 desired={s:changes.get(s,int(f['arable_land'])) for s,f in vanilla.states.items() if 'arable_land' in f};employment=adjusted_employment(employment,desired,owners)
 for s,n in desired.items():target.states[s]['arable_land']=str(n)
 text(mod/'common/history/buildings/00_eu5_world.txt',render_buildings(list(ledger.rows.values())));write_land(target,RUN/'base/eu5_converted',mod,desired)
 ledger.ownership.verify(building_rows(mod/'common/history/buildings/00_eu5_world.txt'))
 for name,data in [('employment',employment),('ownership',ownership),('land_evidence',land_evidence),('industry_evidence',industrial),('source_development_changes',ledger.changes),('supply_chain',supply_audit(ledger,tags))]:write(package/(name+'.json'),data)
 from converter_source_wars import build as wars
 wars(mod)
 from m5_dynamic_identity import apply as dynamic_identity
 from converter_refresh import country_labels
 country_labels(mod,GAME,mapping['countries'])
 # Label cleanup removes generated name keys too; regenerate the current world's keys.
 write(RUN/'dynamic_identity_manifest.json',dynamic_identity(mod,GAME,mapping,refresh_legacy_names=False))
 from converter_source_claims import install as source_claims
 write(package/'source_claims.json',source_claims(mod,GAME,RUN,ROOT,mapping['countries'],read(RUN/'fresh_context.json')['mapping']))
 from converter_opening_balance import install as opening_balance
 write(package/'opening_balance.json',opening_balance(mod,GAME,ROOT,mapping['countries'],RUN))
 # Both authorized population policies start from the same immutable source population.
 from package_m5_population_options import apply_mode
 from package_m5_population_calibration import rewrite_populations
 pp=read(ROOT/'config/personal/economy_population_options.json');elite={};classes=Counter()
 for r in stage:classes[r['target_state'],r['target_owner'],r['source_class']]+=int(r['centipersons'])/100
 for h in ownership['owner_hosts']:
  s,t=h['state'],h['country'];minimum=0
  for label,kind,cls,profession,fraction in [('manor','building_manor_house','nobles','aristocrats',1),('finance','building_financial_district','burghers','capitalists',policy['ownership']['burgher_investor_fraction'])]:
   levels=h['referenced_owned_levels'].get(label,0)
   if not levels:continue
   pm=target.select(kind,techs[t],set(),laws[t]);required=levels*target.numeric(pm)['building_employment_'+profession+'_add'];pool=classes[s,t,cls]*pp['workforce_share']*fraction;minimum=max(minimum,required/pool if pool else 1)
  elite[s,t]=min(1,minimum)
 calibrated,calibration=apply_mode('reserve_15',groups,employment,ledger.ownership_jobs,elite,pp)
 text(package/'original_population.txt',(mod/'common/history/pops/00_eu5_world.txt').read_text(encoding='utf-8-sig'))
 text(package/'population_reserve_15.txt',rewrite_populations((mod/'common/history/pops/00_eu5_world.txt').read_text(encoding='utf-8-sig'),calibrated));write(package/'population_reserve_15.json',calibration)
 write(package/'summary.json',dict(source_date=read(AUDIT)['date'],source_population=read(RUN/'demographic/demographics/demographics_report.json')['source_integer_persons'],template_supplement_population=read(RUN/'demographic/template_fallback/template_report.json')['template_supplement_persons'],total_population=sum(groups.values()),reserve_15_population=sum(calibrated.values()),population_mode=pp['population_mode'],countries=len(mapping['countries']),native_countries=sum(c.get('generated_uncolonized',False) for c in mapping['countries'].values()),land_provinces=40717,empty_population_countries=sorted(set(mapping['countries'])-{k[1] for k in groups}),new_industry_levels=sum(r['levels'] for r in ledger.rows.values())-sum(r['levels'] for r in baseline),land_added=sum(desired[s]-int(vanilla.states[s]['arable_land']) for s in desired),runtime_verified=False))
 print('Complete candidate composed',sum(groups.values()),sum(calibrated.values()),flush=True)
if __name__=='__main__':build()
