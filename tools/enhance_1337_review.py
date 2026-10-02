"""Readable country-type maps and evidence labels for supervised review."""
from build_fresh_1337 import *
from build_location_workstation import packed,paint
from PIL import Image
import numpy as np
OUT=ROOT/'.local/m3/terrain-workstation-1337-rereview'

def build():
 data=read(OUT/'data.json');owners=read(RUN/'political/province_owners.json');m=read(RUN/'political/conversion_report.json');byid={str(c['source_id']):c for c in m['countries'].values() if c['source_id']}
 names={'decentralized':'松散部落','recognized':'国家','unrecognized':'国家（未认可）','colonial':'殖民国家','company':'公司国家'}
 actual_pop=Counter()
 for r in rows(RUN/'demographic/demographics/resident_population_groups.csv'):actual_pop[r['state'],r['owner']]+=int(r['preview_integer_persons'])
 for r in rows(RUN/'demographic/template_fallback/template_population_groups.csv'):actual_pop[r['state'],r['owner']]+=int(r['persons'])
 for p,r in data['targets'].items():
  r['owner']=owners[r['state']][p];c=m['countries'][r['owner']];r['owner_name']=c.get('name_simp_chinese',r['owner_name']);r['country_type']=c['country_type'];r['type_name']=names[c['country_type']];r['culture_key']=c['culture']
 for n,r in data['sources'].items():
  r['type_name']='荒地' if r['barren'] else '无主民族地区' if r['owner']=='0' else names.get(byid.get(r['owner'],{}).get('country_type'),'源国家')
 for c in data['components']:
  if c.get('issue'):
   tags=Counter(owners[data['targets'][p]['state']][p] for p in c['provinces']);tag=tags.most_common(1)[0][0];country=m['countries'][tag];c['issue']['country_type']=country['country_type'];c['issue']['type_name']=names[country['country_type']];c['issue']['current_owner']=tag;c['issue']['current_owner_name']=country.get('name_simp_chinese',tag);c['issue']['current_population']=sum(actual_pop[state,t] for state,t in {(data['targets'][p]['state'],owners[data['targets'][p]['state']][p]) for p in c['provinces']})
 anchors=defaultdict(list)
 for p,r in data['targets'].items():anchors[r['state'],r['owner']].append(p)
 data['target_labels']=[]
 for (state,t),ps in anchors.items():
  center=np.array([data['targets'][p]['xy'] for p in ps]).mean(axis=0);p=min(ps,key=lambda p:float(np.linalg.norm(np.array(data['targets'][p]['xy'])-center)))
  r=data['targets'][p];data['target_labels'].append(dict(xy=r['xy'],owner=t,text=r['type_name']+' · '+r['owner_name']))
 for kind in ['source','target']:
  path=OUT/(kind+'-map.png');backup=OUT/(kind+'-map-before-types.png')
  if not backup.exists():shutil.copyfile(path,backup)
  im=Image.open(OUT/(kind+'-ids.png')).convert('RGB');ids=packed(im);palette={};owners=np.zeros(1<<24,dtype=np.int32);ownerids={}
  records=data['sources'] if kind=='source' else data['targets']
  for key,r in records.items():
   code=int(r['color'],16) if kind=='source' else int(key[1:],16)
   tribe=r['owner']=='0' and not r['barren'] if kind=='source' else r['country_type']=='decentralized'
   color=(180,171,142) if tribe else (74,113,139)
   if kind=='source' and r['barren']:color=(83,91,99)
   palette[code]=color;owner=r['owner'];ownerids.setdefault(owner,len(ownerids)+1);owners[code]=ownerids[owner]
  paint(im,palette,path);arr=np.array(Image.open(path).convert('RGB'));region=owners[ids];edge=(region!=np.roll(region,1,axis=1)) | (region!=np.roll(region,1,axis=0));edge &= region>0;arr[edge]=(54,69,78)
  Image.fromarray(arr).save(path)
 data['source_labels']=[dict(xy=r['xy'],owner=r['owner'],text=r['type_name']+' · '+(r.get('mapped_culture') or r['culture'] if r['owner']=='0' else r['owner_name'])) for r in sorted(data['sources'].values(),key=lambda r:-float(r['population'])) if r['evidence']]
 data['display_style']='country_types_with_names';write(OUT/'data.tmp',data);(OUT/'data.tmp').replace(OUT/'data.json')
 print('Country type labels and calm maps updated')
if __name__=='__main__':build()
