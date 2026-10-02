"""Evidence-based adjudication of the supervised 1337 empty-terrain queue."""
from build_fresh_1337 import *
OUT=ROOT/'.local/m3/terrain-workstation-1337-rereview'

def build():
 d=read(OUT/'data.json');plan=read(RUN/'terrain_plan.json');seeds=read(RUN/'terrain_seeds.json');m=read(RUN/'political/conversion_report.json');reviews=read(OUT/'terrain_reviews.json')
 edges={frozenset(edge) for edge in read(ROOT/'.local/m3/cache/tribal_land_edges.json')['edges']};result={};counts=Counter()
 for c in d['components']:
  if c.get('review_scope')!='empty_parts':continue
  traces=[];country=m['countries'][c['issue']['owner']]
  for p in c['provinces']:
   node=p;visited=set()
   while plan['provinces'][node]['kind']=='land_inferred':
    if node in visited:raise ValueError('Terrain parent cycle')
    visited.add(node);parent=plan['provinces'][node]['parent']
    if frozenset([node,parent]) not in edges:raise ValueError('Terrain inference crosses a non-land edge')
    node=parent
   seed=seeds[node];valid=(seed['owner']==('source:'+str(country['source_id']))) if country['source_id'] else seed.get('mapped_culture')==country['culture']
   if p!='x800111' and not valid:raise ValueError('Owner differs from source anchor: '+p)
   traces.append(dict(province=p,root=node,land_steps=len(visited),source_locations=seed['source_locations'],source_owner=seed['owner'],source_culture=seed.get('source_culture'),mapped_culture=seed.get('mapped_culture'),evidence_kind=seed['kind']))
  if 'x800111' in c['provinces']:
   action='island_template';title='母岛按用户专门规则修正';reason='采用原版文件注释中的小笠原26人参考，民族随当前存档塞班岛映射；不再并入雅浦国家。补位人口与源人口分开记账。'
  elif c['issue']['source_centipersons']:
   action='integer_rounding';title='保持民族归属，修正整数表示';reason=f"源台账为 {c['issue']['source_centipersons']/100:g} 人，并非无人口。分州至少保留1人的整数表示，优先从向上取整的人口组调剂，全球总人口不变。"
  elif 'x46467A' in c['provinces']:
   action='retain_user_review';title='保留用户已复核的因纽特归属';reason='沿用 baffin_island / kinngait 参考。核对为无人口岛屿延伸，保留因纽特民族，不凭空迁入居民或改为邻近其他民族。'
  else:
   action='retain_source_country' if country['source_id'] else 'retain_native_continuity'
   title='保留源国家边界' if country['source_id'] else '保留民族连片归属'
   reason='逐块回溯实际陆地邻接路径，终点具有当前源存档的'+('国家归属' if country['source_id'] else '主体民族')+'证据；未发现跨海推断或俄罗斯原版回退。这部分属于源无人荒地延伸，州内其他部分有居民，国家在其他州也有居民。保留既定规则，不新增人口。'
  counts[action]+=1;result[c['component']]=dict(status='approved',title=title,reason=reason,action=action,reviewer='AI under explicit user supervision',rule_scope='conversion evidence and geography continuity; not a new historical ethnographic claim',provinces=c['provinces'],traces=traces,baseline_owner=c['issue']['owner'],baseline_revision=reviews['revision'],baseline_review_rows={p:reviews['entries'].get(p,{}) for p in c['provinces']})
 write(OUT/'adjudications.json',result);write(RUN/'supervised_terrain_adjudication.json',dict(counts=dict(counts),groups=result,input_sha256={str(p):digest(p) for p in [RUN/'terrain_plan.json',RUN/'terrain_seeds.json',RUN/'political/conversion_report.json',OUT/'terrain_reviews.json']}))
 print(json.dumps(counts,ensure_ascii=False))
if __name__=='__main__':build()
