"""Independent readback checks and release manifest for the fresh 1337 mod."""
from build_fresh_1337 import *
from package_m4_population_test import parse_pops,effective
from verify_m4_culture_assets import validate_culture
from economy_model import Target,building_rows,definitions
from build_economy import expand_template_tech
from complete_economy import active_laws
from extract_m3_politics import sequence
from build_m2_prototype import walk,scalars

def finish():
 package=RUN/'complete';mod=package/'eu5_m5_1337_test';mapping=read(RUN/'political/conversion_report.json');owners=read(RUN/'political/province_owners.json');context=read(RUN/'fresh_context.json')
 # New colours follow the previous deterministic perceptual-separation rule.
 import numpy as np,colorsys
 from m5_culture_geography import read_color,lab,COLOR
 from build_m2_prototype import patch,replace_body
 allcult=defs(mod,'cultures');new=read(REVIEW/'candidate_assets.json')['assets'];old={k:read_color(o.text()) for k,o in allcult.items() if k not in new};pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');counts=Counter()
 for k,n in pops.items():counts[k[2]]+=n
 colors=np.array([colorsys.hsv_to_rgb(h/192,s,v) for h in range(192) for s in (.4,.55,.7,.85,.98) for v in (.50,.62,.74,.86,.98)])
 labs=lab(colors);distance=np.linalg.norm(labs[:,None,:]-lab(list(old.values()))[None,:,:],axis=2).min(axis=1);assigned={};color_audit=[]
 minimum=read(ROOT/'config/personal/m5_culture_geography.json')['colors']['minimum_delta_e_76']
 for k in sorted(new,key=lambda k:(-counts[k],k)):
  preferred=lab(read_color(allcult[k].text()));near=np.linalg.norm(labs-preferred,axis=1);allowed=distance>=minimum
  if not allowed.any():raise ValueError('Reviewed colour-separation budget exhausted')
  idx=int(np.where(allowed,-near,-1e9).argmax());assigned[k]=[round(float(v),5) for v in colors[idx]];color_audit.append(dict(culture=k,color=assigned[k],nearest_delta_e=float(distance[idx])))
  distance=np.minimum(distance,np.linalg.norm(labs-labs[idx],axis=1))
 path=mod/'common/cultures/zz_eu5_1337_cultures.txt';content=path.read_text(encoding='utf-8-sig');edits=[]
 for k,o in objects(root(content)):edits.append(replace_body(o,COLOR.sub('color = { '+' '.join(map(str,assigned[k]))+' }',o.text())))
 text(path,patch(content,edits));write(package/'culture_colors.json',color_audit)
 cultures=effective(mod,'common/cultures');traits=effective(mod,'common/discrimination_traits');traitgroups=effective(mod,'common/discrimination_trait_groups');religions=effective(mod,'common/religions');countries=effective(mod,'common/country_definitions')
 from v3_startup_validation import validate_state_history,culture_modifiers,flag_assets,validate_opening_war_removals
 validate_state_history((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig'),cultures)
 culture_modifiers(GAME,mod)
 flag_assets(GAME,mod)
 validate_opening_war_removals(mod,read(RUN/'war_mapping.json'))
 locs={lang:{} for lang in ['english','simp_chinese']}
 for lang in locs:
  for base in [GAME/'localization'/lang,mod/'localization'/lang,mod/'localization/replace'/lang]:locs[lang].update(load_localization(base))
 for k in {k[2] for k in pops}:validate_culture(k,cultures[k],traits,traitgroups,religions,locs)
 assert all(k[3] in religions for k in pops)
 actual={};states=root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES']
 for key,obj in objects(states):
  state=key[2:];actual[state]={}
  for op,v in obj.entries():
   if op=='add_homeland':assert v.startswith('cu:') and v[3:] in cultures,(state,v)
   if op=='create_state':
    f=fields(v);tag=f['country'][2:];assert tag in countries
    for p in strings(f['owned_provinces']):assert p not in actual[state];actual[state][p]=tag
 assert actual==owners
 assert sum(pops.values())==394557661
 sourcegroups={tuple(r[k] for k in ['state','owner','culture','religion']):int(r['preview_integer_persons']) for r in rows(RUN/'demographic/demographics/resident_population_groups.csv') if int(r['preview_integer_persons'])}
 assert sum(sourcegroups.values())==394540034
 from fresh_empty_state_templates import template_groups
 supplement,_=template_groups(GAME,read(RUN/'source_empty_templates.json'),sourcegroups,owners)
 for p,r in read(RUN/'island_templates.json').items():supplement[r['state'],r['owner'],r['culture'],r['religion']]+=r['persons']
 assert sum(supplement.values())==17627
 assert pops==Counter(sourcegroups)+supplement
 assert set(owners)=={k[0] for k,n in pops.items() if n}
 assert set(mapping['countries'])=={k[1] for k,n in pops.items() if n}, 'Country without opening population'
 for k in pops:assert k[1] in set(owners[k[0]].values())
 for tag in {t for ps in owners.values() for t in ps.values()}:
  assert len(tag)==3 and tag in countries
  assert tag in set(owners[countries[tag]['capital']].values())
  assert all(c in cultures for c in strings(countries[tag]['cultures']))
 target=Target(GAME);target.states.update(definitions(mod/'map_data/state_regions'));target._law_definitions={k:fields(o) for k,o in defs(mod,'laws').items()};target._law_effects={k:o for k,o in objects(root((GAME/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig')))}
 effects={k:o for k,o in objects(root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')))}
 histories={k[2:]:o for k,o in objects(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['COUNTRIES'])};techs={t:expand_template_tech(o,effects,target) for t,o in histories.items()};laws={t:active_laws(o,target,mapping['countries'][t]) for t,o in histories.items()}
 for t,c in mapping['countries'].items():
  if c.get('generated_uncolonized'):assert not re.search(r'\beffect_native_conscription_\d+',histories[t].text()),('unjustified native bonus',t)
 buildings=building_rows(mod/'common/history/buildings/00_eu5_world.txt');seen=set();resources=Counter();barracks=Counter()
 for r in buildings:
  s,t,k=r['state'],r['owner'],r['building'];assert (s,t,k) not in seen;seen.add((s,t,k));assert r['levels']>0 and t in owners[s].values()
  assert set(sequence(target.buildings[k].get('unlocking_technologies')))<=techs[t],('building technology',s,t,k)
  for pm in r['pms']:assert target.available(pm,techs[t],laws[t]),('illegal PM',s,t,k,pm)
  for g in sequence(target.buildings[k].get('production_method_groups')):assert len(set(r['pms'])&set(sequence(target.groups[g]['production_methods'])))==1,('PM coverage',s,t,k,g)
  resources[s,k]+=r['levels']
  if k=='building_barrack':barracks[s,t]+=r['levels']
 for (s,k),n in resources.items():
  cap=fields(target.states[s]['capped_resources']).get(k) if 'capped_resources' in target.states[s] else None
  if cap is not None:assert n<=int(cap),('resource cap',s,k)
 formations=root((mod/'common/history/military_formations/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['MILITARY_FORMATIONS'];units=Counter();armies=fleets=0
 for k,o in objects(formations):
  tag=k[2:];assert tag in histories
  for op,f in objects(o):
   if op!='create_military_formation':continue
   if fields(f)['type']=='army':armies+=1
   else:fleets+=1
   for action,unit in objects(f):
    if action=='combat_unit':
     u=fields(unit);units[u['state_region'][2:],tag]+=int(u['count'])
 assert units==barracks
 for p in (mod/'common/history').rglob('*.txt'):
  for k,o in walk(root(p.read_text(encoding='utf-8-sig'))):
   if k and k.startswith('c:'):assert k[2:] in countries,('country scope',p,k)
 name='EU5 M5 - World 1337 - Generic Rules TEST';meta=read(mod/'.metadata/metadata.json');meta.update(name=name,id='eu5-m5-world-1337-test',version='0.6.2-1337-test3',short_description='Fresh 1337 source conversion. Source population preserved. New 1836 bookmark campaign required. Runtime test pending.');write(mod/'.metadata/metadata.json',meta)
 text(package/'eu5_m5_1337_test.mod',f'name="{name}"\nversion="0.6.2-1337-test3"\nsupported_version="1.13.11"\npath="mod/eu5_m5_1337_test"\n')
 summary=read(package/'summary.json');summary.update(used_cultures=len({k[2] for k in pops}),effective_cultures=len(cultures),religions=len({k[3] for k in pops}),buildings=len(buildings),building_levels=sum(r['levels'] for r in buildings),armies=armies,battalions=sum(units.values()),fleets=fleets,wars=len(read(RUN/'war_mapping.json')),omitted_source_countries=len(mapping['omitted_countries']))
 write(package/'summary.json',summary)
 inp=[AUDIT,ROOT/'.local/m0/clean-starts/eu5-start.txt',REVIEW/'candidate_mapping.json',REVIEW/'candidate_assets.json',ROOT/'config/geography/reviewed_location_links.json',ROOT/'.local/m3/terrain-workstation-1337/terrain_reviews.json',RUN/'political/conversion_report.json',RUN/'capacity/verification.json',RUN/'demographic/staging/staging_report.json']
 inp += [ROOT/'.local/m3/terrain-workstation-1337-rereview/terrain_reviews.json',RUN/'island_templates.json',RUN/'source_empty_templates.json']
 inp += [RUN/'war_mapping.json',RUN/'war_policy.json',GAME/'common/diplomatic_plays/00_diplomatic_plays.txt']
 inp += list((GAME/'common/modifier_type_definitions').glob('*.txt'))+list((GAME/'common/static_modifiers').glob('*.txt'))
 inp+=list((RUN/'source').glob('*.json'));inp+=list((ROOT/'config/personal').glob('*.json'));inp+=list((ROOT/'tools').glob('*.py'))
 result=dict(status='passed_static_runtime_pending',source_date='1337.4.1',source_sha256=context and read(RUN/'source/population/source_summary.json')['source_sha256'],version=meta['version'],mod_name=name,mod_directory=str(mod),political_run=str(RUN/'political'),demographic_run=str(RUN/'demographic'),source_population_conserved=True,population_mode='preserve',new_campaign_required=True,full_conversion_ready=False,summary=summary,input_sha256={str(p):digest(p) for p in inp},output_sha256=files(mod))
 write(package/'package_report.json',result);write(package/'verification.json',dict(status='passed_static_runtime_pending',checks=['complete_land_coverage','no_vanilla_ownership_fallback','exact_population_ledger','approved_empty_state_templates_no_source_overlap','no_empty_whole_states_or_countries','culture_religion_trait_localization_references','unique_country_tags','owned_capitals','building_PM_technology_gates','resource_caps','army_barracks_exact_match','recursive_history_parse','state_history_no_bare_tokens','homeland_culture_scope_syntax','required_culture_and_religion_static_modifiers','identity_modifier_type_dependencies','side_specific_seed_war_goal_removal','imported_flag_texture_paths'],runtime_verified=False,summary=summary))
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':finish()
