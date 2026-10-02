"""Fresh-save build adapter. Never reads campaign history from a prior mod."""
import csv,json,re,shutil,argparse
from collections import Counter,defaultdict
from pathlib import Path
from decimal import Decimal
from pdx_text import root,Object
from m3_world import World,digest,fields
from build_m3_world import Exporter,block,load_localization
from build_m2_prototype import objects,strings,allocate
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.local/conversion/1337-20261002'
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
AUDIT=ROOT/'.local/m1/runs/20260930-092431-opening-b3105a18/report/import_report.json'
REVIEW=ROOT/'outputs/01a0f510-fde4-7dd3-983c-d5b74834b7cf-culture1337'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def text(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v,encoding='utf-8-sig')
def rows(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def csvwrite(p,headers,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(headers);w.writerows(data)
def files(p):return {f.relative_to(p).as_posix():digest(f) for f in p.rglob('*') if f.is_file()}
def defs(mod,kind):
 paths={p.name:p for base in (GAME,mod) for p in sorted((base/'common'/kind).glob('*.txt'))}
 return {k:o for p in paths.values() for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}

def identity_assets(out,prior):
 # Only reusable definitions/icons are imported; no country, map or population history.
 for directory in ['common/cultures','common/religions','common/discrimination_traits','common/discrimination_trait_groups','gfx/interface/icons/religion_icons']:
  if (prior/directory).exists():shutil.copytree(prior/directory,out/directory,dirs_exist_ok=True)
 cultures=defs(prior,'cultures');traits=defs(prior,'discrimination_traits');groups=defs(prior,'discrimination_trait_groups')
 labels={lang:{} for lang in ['english','simp_chinese']}
 for lang in labels:
  for base in [GAME/'localization'/lang,prior/'localization'/lang,prior/'localization/replace'/lang]:labels[lang].update(load_localization(base))
 keep=set(cultures)|set(traits)|set(groups)|set(defs(out,'religions'))
 labels={lang:{k:v for k,v in ls.items() if k in keep} for lang,ls in labels.items()}
 mapping=read(REVIEW/'candidate_mapping.json')['mappings'];assets=read(REVIEW/'candidate_assets.json')['assets']
 first={r['source_culture']:r for r in read(REVIEW/'first_pass_audit.json')['rows']}
 audit={r['source_culture']:r for r in read(REVIEW/'audit.json')['rows']}
 from culture_1337_rules import PRESERVE_BATCHES
 hints={n:t for t,names,*_ in PRESERVE_BATCHES for n in names.split()}
 bodies={};newtraits={};newgroups={};manifest=[]
 for key,design in assets.items():
  if key in cultures:continue
  source=design['members'][0];r=audit[source]
  template=first[source]['target_culture']
  if template not in cultures:template=hints.get(source)
  if template not in cultures:raise ValueError('No explicitly reviewed asset template: '+source+' '+str(template))
  body=cultures[template].text();heritage=design['heritage'];language=design['language']
  if heritage not in traits:raise ValueError('Missing reviewed heritage '+heritage)
  if language not in traits:
   # Catalogue IDs preserve a reviewed speech identity; no invented language family.
   families={x['family_id'] for x in r.get('linguistic_evidence',[]) if x.get('family_id')}
   group=('eu5_1337_family_'+next(iter(families))) if len(families)==1 and not language.startswith('eu5_review_language_source_') else 'eu5_1337_group_'+language
   newgroups[group]='type = language';newtraits[language]='type = language\ntrait_group = '+group
   for lang in labels:labels[lang][language]=design['name']+('语' if lang=='simp_chinese' else ' language');labels[lang][group]=labels[lang][language]
  body=re.sub(r'\bheritage\s*=\s*\w+','heritage = '+heritage,body)
  body=re.sub(r'\blanguage\s*=\s*\w+','language = '+language,body)
  bodies[key]=body;cultures[key]=dict(objects(root(block(key,body))))[key]
  for lang in labels:labels[lang][key]=design['name'] if lang=='simp_chinese' else source.replace('_culture','').replace('_',' ').title()
  manifest.append(dict(target=key,template=template,heritage=heritage,language=language,names='Existing regional template names retained as explicit gameplay scaffold; no historical certification',graphics='Existing reviewed regional template',source=source))
 for key,design in read(REVIEW/'candidate_mapping.json').get('display_scope_overrides',{}).items():
  labels['simp_chinese'][key]=design['name']
 for kind,name,data in [('cultures','cultures',bodies),('discrimination_traits','traits',newtraits),('discrimination_trait_groups','groups',newgroups)]:
  text(out/f'common/{kind}/zz_eu5_1337_{name}.txt',''.join(block(k,v) for k,v in sorted(data.items())))
 for lang,ls in labels.items():text(out/f'localization/replace/{lang}/zz_eu5_1337_identity_l_{lang}.yml','l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in sorted(ls.items())))
 write(RUN/'identity_asset_manifest.json',manifest)
 return mapping,labels

def build():
 audit=read(AUDIT);politics=read(RUN/'source/politics.json');summary=read(RUN/'source/population/source_summary.json')
 assert summary['source_sha256']==read(REVIEW/'candidate_mapping.json')['source_sha256']==politics['source_sha256']
 package=RUN/'base';mod=package/'eu5_m5_1337_test'
 if (RUN/'fresh_context.json').exists():raise ValueError('Completed base exists')
 prior=Path(read(ROOT/'.local/m5/installation-latest.json')['package']);prior_report=read(prior/'package_report.json');prior_mod=Path(prior_report['mod_directory'])
 mod.mkdir(parents=True,exist_ok=True);mapping,labels=identity_assets(mod,prior_mod)
 profile=read(ROOT/'config/personal/m3_world.json')
 profile.update(source_sha256=summary['source_sha256'],source_date=audit['date'],country_tag_overrides={},country_tag_mapping_file=None,custom_cultures={},culture_aliases=mapping,uncolonized_region_overrides={},fallback_country_overrides={},province_anchor_overrides={},unmapped_state_anchors={},decentralize_source_countries=[],regional_anchor_profile=str(RUN/'regional.json'),notes=['Fresh 1337 source; independently rebuilt territory and population; isolated test.'])
 profile['government_laws']['steppe_horde']='law_monarchy'
 profile['subject_types'].update(tusi='vassal',samanta='vassal',appanage='vassal')
 write(RUN/'regional.json',{'states':{}})
 # Resolve religions using the existing explicit rules, never a blanket fallback.
 from m4_demographics import religion_resolution
 rd={k:fields(o) for k,o in defs(mod,'religions').items()};sd={k:fields(o) for p in (EU5/'in_game/common/religions').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
 rp=read(ROOT/'config/personal/m4_demographics.json');religions={}
 used=set(summary['religion_centipersons'])|{c['religion'] for c in politics['countries'].values() if c.get('religion')}
 extra={r:{'source_group':sd[r]['group'],'heritage':'heritage_christian' if sd[r]['group']=='christian' else None,'taboos':[],'reason':'Apply existing source-religion preservation rule to newly present 1337 identity.'} for r in sorted(used) if not religion_resolution(r,sd[r],profile,rp,rd)[0]}
 if extra:
  from m4_religions import write_custom_religions
  assetdir=RUN/'new_religion_assets';write_custom_religions(assetdir,GAME,EU5,sd,{'custom_religions':extra,'religion_aliases':{}})
  for p in assetdir.rglob('*'):
   if p.is_file():
    rel=p.relative_to(assetdir);dest=mod/rel
    if p.suffix in ('.txt','.yml'):dest=dest.with_name('zz_1337_'+dest.name)
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
  rp['custom_religions'].update(extra);rd={k:fields(o) for k,o in defs(mod,'religions').items()}
 write(RUN/'religion_policy.json',rp)
 for r in sorted(used):
  target,_,_=religion_resolution(r,sd[r],profile,rp,rd)
  if not target:raise ValueError('Unreviewed religion '+r)
  religions[r]=target
 profile['religion_aliases']=religions;write(RUN/'profile.json',profile)
 w=World(GAME,EU5,audit,politics,profile,ROOT/'.local/m3/cache')
 geo=read(ROOT/'config/geography/reviewed_location_links.json')
 assert geo['source_map_sha256']==digest(EU5/'in_game/map_data/locations.png') and geo['target_map_sha256']==digest(GAME/'map_data/provinces.png')
 reviewed=set(geo['locations']);w.mapping={p:sorted(set(ns)-reviewed) for p,ns in w.mapping.items()};weights={}
 for n,r in geo['locations'].items():
  weights[n]={t['province']:t['weight'] for t in r['targets']}
  for p in weights[n]:w.mapping.setdefault(p,[]).append(n)
 pops=list(rows(RUN/'source/population/source_populations.csv'));lc=defaultdict(Counter);lr=defaultdict(Counter)
 for r in pops:lc[r['location']][r['source_culture']]+=int(r['centipersons']);lr[r['location']][r['source_culture'],r['source_religion']]+=int(r['centipersons'])
 from terrain_connectivity import source_seeds,complete,require_export_ready
 from terrain_reviews import validate_document,apply_references
 from m3_uncolonized import province_land_edges
 seeds,natives,empty=source_seeds(w.province_state,w.mapping,w.locations,w.uninhabitable,lc,mapping,weights)
 reviews=validate_document(read(ROOT/'.local/m3/terrain-workstation-1337/terrain_reviews.json'),geo['source_map_sha256'],geo['target_map_sha256'],w.province_state,w.locations)
 allowed_overrides=set();rereview=ROOT/'.local/m3/terrain-workstation-1337-rereview'
 if (rereview/'terrain_reviews.json').exists():
  scope=read(rereview/'review_scope.json');assert scope['source_map_sha256']==geo['source_map_sha256'] and scope['target_map_sha256']==geo['target_map_sha256']
  extra_reviews=validate_document(read(rereview/'terrain_reviews.json'),geo['source_map_sha256'],geo['target_map_sha256'],w.province_state,w.locations)
  confirmed={p:r for p,r in extra_reviews.items() if r.get('review_round')==scope['review_round']}
  # Explicit user re-marking takes precedence for this reviewed geometry only.
  reviews.update(confirmed);allowed_overrides=set(confirmed)&set(scope['provinces'])
  if any(r['status']!='mapped' for r in confirmed.values()):raise ValueError('Re-reviewed terrain remains deferred or pending')
 missing=apply_references(reviews,w.province_state,w.locations,w.uninhabitable,lc,seeds,natives,allowed_overrides)
 if missing:raise ValueError('Reviewed terrain has no current source evidence: '+str(missing))
 # Review references also use the final culture map before connected components.
 for p,r in seeds.items():
  if r.get('source_culture'):
   c=mapping[r['source_culture']];r['owner']='native:'+c;r['mapped_culture']=c;natives[r['owner']]=c
 w.owners={s:{p:'land' for p in ps} for s,ps in w.provinces.items()}
 plan=require_export_ready(complete(w.province_state,province_land_edges(w,ROOT/'.local/m3/cache/tribal_land_edges.json'),seeds,natives))
 write(RUN/'terrain_plan.json',plan);write(RUN/'terrain_seeds.json',seeds)
 w.owners={s:{} for s in w.provinces}
 native_templates={t:fields(o) for t,o in w.country_defs.items() if fields(o).get('country_type')=='decentralized'}
 placeholder=min(native_templates)
 for p,r in plan['provinces'].items():w.owners[r['state']][p]=r['owner'][7:] if r['owner'].startswith('source:') else 'v:'+placeholder
 w.represented={c for ps in w.owners.values() for c in ps.values() if not c.startswith('v:')}
 mapped={n for p in w.province_state for n in w.mapping.get(p,[])}
 w.unmapped_locations=[l for n,l in w.locations.items() if n not in mapped and Decimal(l['population_persons'])>0]
 if w.unmapped_locations:raise ValueError('Populated source geography unresolved: '+str(len(w.unmapped_locations)))
 w.microstates=[{'id':i,'tag':c['tag'],'population':c['population_persons']} for i,c in w.source.items() if i not in w.represented]
 # Existing approved tag correspondences are relinked by exact source definition, not old save IDs.
 approved=read(ROOT/'config/personal/country_tag_mappings.json')['matches'];bytag=defaultdict(set)
 for r in approved.values():bytag[r['source_tag']].add(r['target_tag'])
 matches={};taken=set()
 for i in sorted(w.represented,key=int):
  ts=bytag.get(w.source[i]['tag'],set())
  if len(ts)==1 and next(iter(ts)) not in taken:
   t=next(iter(ts));taken.add(t);matches[i]={'source_tag':w.source[i]['tag'],'target_tag':t,'basis':'exact source tag relinked across saves'}
 write(RUN/'tag_map.json',dict(source_sha256=summary['source_sha256'],target_version=profile['target_version'],matches=matches));profile['country_tag_mapping_file']=str(RUN/'tag_map.json')
 w.politics_model()
 from native_country_tags import allocate as tags
 native_tags=tags([r['owner'] for r in plan['native_components']],set(w.country_defs)|set(w.countries))
 for component in plan['native_components']:
  tag=native_tags[component['owner']];c=component['culture'];counts=Counter();faith=Counter();statepop=Counter()
  for p in component['provinces']:
   seed=seeds[plan['provinces'][p]['root']]
   for n in seed['source_locations']:
    for (sc,sr),amount in lr[n].items():
     if mapping[sc]==c:counts[sc]+=amount;faith[sr]+=amount;statepop[w.province_state[p]]+=amount
   w.owners[w.province_state[p]][p]=tag
  sc=min(counts,key=lambda k:(-counts[k],k));sr=min(faith,key=lambda k:(-faith[k],k))
  prior_counts=Counter(w.original[w.province_state[p]].get(p) for p in component['provinces'])
  choices=[t for t,f in native_templates.items() if c in strings(f['cultures'])] or [t for t in prior_counts if t in native_templates] or sorted(native_templates)
  template=min(choices,key=lambda t:(-prior_counts[t],t));capital=min(statepop,key=lambda s:(-statepop[s],s))
  w.countries[tag]=dict(source_id=None,tag=tag,template=template,country_type='decentralized',capital=capital,capital_exact=False,generated_uncolonized=True,source_culture=sc,culture=c,cultures=[c],source_religion=sr,religion=religions[sr],provinces=len(component['provinces']),type_reason='mapped_primary_culture_land_component')
 from fresh_empty_state_templates import apply_ownership,prepare_island_templates
 empty_templates=apply_ownership(w,lc,weights,read(ROOT/'config/personal/m4_population_policy.json'),province_land_edges(w,ROOT/'.local/m3/cache/tribal_land_edges.json'));write(RUN/'source_empty_templates.json',empty_templates)
 island_templates=prepare_island_templates(w,GAME,read(ROOT/'config/personal/m4_population_policy.json'),lc,weights,mapping,religions,lr);write(RUN/'island_templates.json',island_templates)
 live=Counter(t for ps in w.owners.values() for t in ps.values());w.countries={t:c for t,c in w.countries.items() if t in live}
 from empty_native_attachments import attach
 for country in w.countries.values():
  if country.get('source_id'):country['culture']=mapping[politics['countries'][country['source_id']]['culture']]
 attachments=attach(w,plan,seeds,lc,weights);write(RUN/'empty_native_attachments.json',attachments)
 w.substates={s:Counter(ps.values()) for s,ps in w.owners.items()};w.transfers={(s,t):Counter(w.owners[s][p] for p,old in ps.items() if old==t and p in w.owners[s]) for s,ps in w.original.items() for t in set(ps.values())}
 write(RUN/'profile.json',profile)
 print('Territory',plan['summary'],'countries',len(w.countries),'omitted',len(w.microstates),flush=True)
 e=Exporter(w)
 e.valid_cultures.update(defs(mod,'cultures'));e.valid_religions.update(defs(mod,'religions'))
 e.names();e.cultures()
 for lang in e.localization:
  for t,c in w.countries.items():
   if c.get('generated_uncolonized'):e.localization[lang][t]=e.localization[lang][t+'_ADJ']=labels[lang].get(c['culture'],c['source_culture'])
 for method in ('country_setup','state_setup','pops','buildings','military','characters','diplomacy','organizations','flags','finish'):
  print(method,flush=True);getattr(e,method)()
 for rel,value in e.outputs.items():text(mod/rel,value)
 for rel,src in e.binary_assets.items():p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,p)
 report=e.report();report['empty_native_attachments']=attachments;report.update(mod_directory=str(mod),profile_sha256=digest(RUN/'profile.json'),audit_sha256=digest(AUDIT),politics_sha256=digest(RUN/'source/politics.json'),output_sha256=files(mod))
 political=RUN/'political';write(political/'conversion_report.json',report);write(political/'province_owners.json',w.owners)
 write(RUN/'fresh_context.json',{'political_run':str(political),'mod_directory':str(mod),'mapping':mapping,'religions':religions,'location_weights':weights,'geography_mapping':w.mapping})
 write(package/'package_report.json',dict(mod_directory=str(mod),political_run=str(political),demographic_run=str(RUN/'demographic'),output_sha256=files(mod)))
 print('Political base complete',flush=True)
if __name__=='__main__':build()
