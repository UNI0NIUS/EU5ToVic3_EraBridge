"""Rebuild source population/literacy and source-conditioned laws for a fresh run."""
from build_fresh_1337 import *
from m4_demographics import round_groups
from population_state_rounding import preserve_populated_parts

def build():
 c=read(RUN/'fresh_context.json');mod=Path(c['mod_directory']);demo=RUN/'demographic';stage=demo/'staging';owners=read(Path(c['political_run'])/'province_owners.json');summary=read(RUN/'source/population/source_summary.json')
 inverse=defaultdict(set)
 for p,ns in c['geography_mapping'].items():
  if any(p in ps for ps in owners.values()):
   for n in ns:inverse[n].add(p)
 lookup={p:(s,t) for s,ps in owners.items() for p,t in ps.items()};records=[];popids=Counter();groups=Counter();srcrows=list(rows(RUN/'source/population/source_populations.csv'))
 for r in srcrows:
  n=int(r['centipersons'])
  if not n:continue
  ps=inverse[r['location']]
  if not ps:raise ValueError('Missing populated location '+r['location'])
  for p,amount in allocate(n,c['location_weights'].get(r['location'],{p:1 for p in ps})).items():
   if not amount:continue
   s,t=lookup[p];culture=c['mapping'][r['source_culture']];religion=c['religions'][r['source_religion']]
   records.append([r['location'],r['pop_id'],r['source_owner'],p,s,t,r['source_culture'],culture,r['source_religion'],r['source_class'],amount,'reviewed']);popids[r['pop_id']]+=amount
 assert all(popids[r['pop_id']]==int(r['centipersons']) for r in srcrows)
 csvwrite(stage/'province_population_draft.csv',['source_location','source_pop_id','source_owner','target_province','target_state','target_owner','source_culture','target_culture','source_religion','source_class','centipersons','mapping_status'],records)
 from m4_migrant_cultures import build_migrants
 profile=read(ROOT/'config/personal/m4_demographics.json');sdefs={k:fields(o) for p in (EU5/'in_game/common/cultures').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
 migrant,mi=build_migrants(demo/'migrant_assets',stage,GAME,EU5,profile,sdefs,{k:(v,'reviewed') for k,v in c['mapping'].items()},set(defs(mod,'cultures'))-set(k for k in defs(mod,'cultures') if k.startswith('eu5_migrant_')))
 for p in (demo/'migrant_assets').rglob('*'):
  if p.is_file():dest=mod/p.relative_to(demo/'migrant_assets');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 for r in records:
  s,t,sc,sr,n=r[4],r[5],r[6],r[8],r[10];culture=migrant.get((sc,s),c['mapping'][sc]);groups[s,t,culture,c['religions'][sr]]+=n
 rounded,rounding=preserve_populated_parts(groups,round_groups(groups));write(demo/'demographics/state_part_rounding.json',rounding);assert sum(groups.values())==summary['world_centipersons']
 csvwrite(demo/'demographics/resident_population_groups.csv',['state','owner','culture','religion','centipersons','preview_integer_persons'],((*k,n,rounded[k]) for k,n in sorted(groups.items())))
 csvwrite(demo/'demographics/resident_culture_crosswalk.csv',['source_culture','target_culture'],sorted(c['mapping'].items()))
 csvwrite(demo/'demographics/resident_religion_crosswalk.csv',['source_religion','target_religion'],sorted(c['religions'].items()))
 from fresh_empty_state_templates import template_groups
 supplements,template_inputs=template_groups(GAME,read(RUN/'source_empty_templates.json'),groups,owners)
 island_templates=read(RUN/'island_templates.json')
 for p,r in island_templates.items():
  key=(r['state'],r['owner'],r['culture'],r['religion'])
  if any(k[:2]==key[:2] and n for k,n in groups.items()):raise ValueError('Island template part already has source population')
  supplements[key]+=r['persons']
  template_inputs.append(GAME/r['population_reference_file'])
 csvwrite(demo/'template_fallback/template_population_groups.csv',['state','owner','culture','religion','persons'],((*k,n) for k,n in sorted(supplements.items())))
 write(demo/'template_fallback/template_report.json',dict(source_empty_states=read(RUN/'source_empty_templates.json'),template_supplement_persons=sum(supplements.values()),island_templates=island_templates,source_population_unchanged=True,input_sha256={str(p):digest(p) for p in template_inputs}))
 source_rounded=rounded.copy();rounded.update(supplements)
 parts=defaultdict(lambda:defaultdict(list))
 for (s,t,cu,rel),n in sorted(rounded.items()):
  if n:parts[s][t].append(block('create_pop',f'culture = {cu}\nreligion = {rel}\nsize = {n}'))
 text(mod/'common/history/pops/00_eu5_world.txt',block('POPS',''.join(block('s:'+s,''.join(block('region_state:'+t,''.join(rs)) for t,rs in ts.items())) for s,ts in parts.items())))
 missing=sorted({(s,t) for s,ps in owners.items() for t in ps.values()}-{k[:2] for k,n in rounded.items() if n})
 write(demo/'demographics/demographics_report.json',dict(source_sha256=summary['source_sha256'],migrant_cultures=mi,world_centipersons=sum(groups.values()),world_integer_persons=sum(rounded.values()),empty_state_parts=missing,used_cultures=len({k[2] for k,n in rounded.items() if n}),source_integer_persons=sum(source_rounded.values()),template_supplement_persons=sum(supplements.values()),population_policy='source conserved; previously approved Acre/Nauru vanilla templates separately accounted'))
 write(stage/'staging_report.json',dict(source_sha256=summary['source_sha256'],political_run=c['political_run'],world_centipersons=sum(groups.values()),allocated_centipersons=sum(groups.values()),unmapped_centipersons=0,files_sha256=files(stage)))
 # Homelands are curated historical cores, plus the already-authorized whole-state majority supplement.
 # Do not use the superseded automatic 20% source-location heuristic.
 home=defaultdict(set);statecounts=Counter();totals=Counter();reasons=[]
 for (s,t,cu,rel),n in rounded.items():totals[s]+=n;statecounts[s,cu]+=n
 for (s,cu),n in statecounts.items():
  if 2*n>totals[s]:home[s].add(cu);reasons.append(dict(state=s,culture=cu,basis='strict_whole_state_majority'))
 history=read(ROOT/'config/personal/m5_historical_homelands.json')
 active={k[2] for k,n in rounded.items() if n}
 for r in history['entries']:
  if r['status']!='candidate_core' or r['culture'] not in active:continue
  # Cross-save cores require a current local resident anchor; later-only migration cannot seed 1337.
  for n in r.get('anchors',{}):
   linked={lookup[p][0] for p in inverse[n]}
   evidence=sum(int(x['centipersons']) for x in srcrows if x['location']==n and c['mapping'][x['source_culture']]==r['culture'])
   if evidence:
    for s in linked & set(r['states']):home[s].add(r['culture']);reasons.append(dict(state=s,culture=r['culture'],basis='curated_historical_core_and_current_source_presence',anchor=n))
 from v3_startup_validation import rewrite_homelands,validate_state_history
 path=mod/'common/history/states/00_eu5_world.txt';content=rewrite_homelands(path.read_text(encoding='utf-8-sig'),home)
 # Reusable definitions are finalized by the complete-package identity pass.
 validate_state_history(content,set(c['mapping'].values())|set(defs(mod,'cultures')))
 text(path,content);write(RUN/'homeland_manifest.json',reasons)
 from m4_literacy import build as literacy
 result=literacy(RUN/'base',demo,mod,GAME,RUN/'source/literacy',RUN/'source/population')
 report=read(RUN/'base/package_report.json');report['output_sha256']=files(mod);report['literacy']=result;write(RUN/'base/package_report.json',report)
 print(json.dumps(dict(persons=sum(rounded.values()),cultures=len(active),migrants=len(mi['cultures']),empty_parts=len(missing),literacy=result['world_literacy_percent'])))
if __name__=='__main__':build()
