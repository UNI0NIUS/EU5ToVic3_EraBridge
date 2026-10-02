"""Reopen the existing terrain workstation for empty state-part review."""
from build_fresh_1337 import *
from build_terrain_workstation import political_color
from build_location_workstation import paint
from terrain_display_geometry import refresh_geometry
from PIL import Image
from copy import deepcopy
OUT=ROOT/'.local/m3/terrain-workstation-1337-rereview'
ROUND='1337-empty-state-parts-20261002'

def build():
 old=ROOT/'.local/m3/terrain-workstation-1337'
 if (OUT/'data.json').exists():raise ValueError('Review dataset exists; preserve user changes')
 OUT.mkdir(parents=True,exist_ok=True);data=read(old/'data.json');doc=read(old/'terrain_reviews.json')
 owners=read(RUN/'political/province_owners.json');mapping=read(RUN/'political/conversion_report.json');context=read(RUN/'fresh_context.json');seeds=read(RUN/'terrain_seeds.json');plan=read(RUN/'terrain_plan.json')
 groups=list(rows(RUN/'demographic/demographics/resident_population_groups.csv'));templates=list(rows(RUN/'demographic/template_fallback/template_population_groups.csv'))
 parts=Counter();exact=Counter();world=Counter();location_parts=defaultdict(Counter)
 for r in groups:parts[r['state'],r['owner']]+=int(r['preview_integer_persons']);exact[r['state'],r['owner']]+=int(r['centipersons']);world[r['owner']]+=int(r['preview_integer_persons'])
 for r in templates:parts[r['state'],r['owner']]+=int(r['persons']);world[r['owner']]+=int(r['persons'])
 for r in rows(RUN/'demographic/staging/province_population_draft.csv'):location_parts[r['source_location']][r['target_state']]+=int(r['centipersons'])
 labels=load_localization(GAME/'localization/simp_chinese');mod=Path(context['mod_directory'])
 for base in [mod/'localization/simp_chinese',mod/'localization/replace/simp_chinese']:labels.update(load_localization(base))
 for n,r in data['sources'].items():r['mapped_culture']=labels.get(context['mapping'].get(r.get('culture_key')),context['mapping'].get(r.get('culture_key'),''))
 for c in data['components']:c['review_scope']='original'
 updated=[]
 for state,ps in sorted(owners.items()):
  for tag in sorted(set(ps.values())):
   if parts[state,tag]:continue
   provinces=sorted(p for p,t in ps.items() if t==tag);country=mapping['countries'][tag]
   reason='源人口经全局取整后为零' if exact[state,tag] else '源国家所持荒地在本州无人' if country['source_id'] else '民族地块跨州延伸，但本州没有居民'
   priority=0 if set(provinces)&{'x46467A','x800111'} else 1
   updated.append(dict(component='empty-'+state+'-'+tag,states=[state],state_names=[labels.get(state,state)],provinces=provinces,review_scope='empty_parts',priority=priority,
       issue=dict(owner=tag,owner_name=country.get('name_simp_chinese',labels.get(tag,tag)),culture=labels.get(country['culture'],country['culture']),culture_key=country['culture'],source_centipersons=exact[state,tag],country_population=world[tag],reason=reason),candidates=[]))
 updated.sort(key=lambda c:(c['priority'],-len(c['provinces']),c['component']))
 data['components']=updated+data['components'];data['review_round']=ROUND;data['reference_population_by_location']=dict(location_parts)
 data['summary']['empty_state_parts']=len(updated);data['summary']['rereview_provinces']=sum(len(c['provinces']) for c in updated)
 data['review_baseline_revision']=doc['revision'];data['report']=str(RUN)
 for state,ps in owners.items():
  for p,t in ps.items():
   c=mapping['countries'][t];r=data['targets'][p];r.update(owner=t,owner_name=c.get('name_simp_chinese',labels.get(t,t)),kind=plan['provinces'][p]['kind'],sources=seeds[plan['provinces'][p]['root']]['source_locations'])
 Image.MAX_IMAGE_PIXELS=150_000_000
 for name in ['source-ids.png','source-map.png','target-ids.png']:shutil.copyfile(old/name,OUT/name)
 im=Image.open(OUT/'target-ids.png').convert('RGB');wanted={p for c in updated for p in c['provinces']}
 paint(im,{int(p[1:],16):(222,84,98) if p in wanted else political_color(r['owner']) for p,r in data['targets'].items()},OUT/'target-map.png')
 refresh_geometry(data,im)
 (OUT/'data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 write(OUT/'terrain_reviews.json',doc)
 write(OUT/'baseline_reviews.json',doc)
 write(OUT/'review_scope.json',dict(review_round=ROUND,source_map_sha256=data['source_map_sha256'],target_map_sha256=data['target_map_sha256'],provinces=sorted(wanted),base_review_revision=doc['revision'],source_population_sha256=digest(RUN/'demographic/demographics/resident_population_groups.csv')))
 print(json.dumps(dict(groups=len(updated),provinces=len(wanted),original_entries=len(doc['entries']),first=updated[0]['component'],directory=str(OUT))))
if __name__=='__main__':build()
