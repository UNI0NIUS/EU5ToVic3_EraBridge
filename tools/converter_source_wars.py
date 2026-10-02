from converter_source_world import *
from opening_wars import plan,render
from build_m2_prototype import state_owners
from border_war_goals import load_candidates,price_scripts,VALUES

def war_route(w):
 kind=w['goals'][0]['kind']
 route={'civil_war':'native_civil_war_annexation','take_province':'one_state_territorial_goal','take_capital':'one_state_territorial_goal','superiority':'humiliation_approximation','aggression':'humiliation_approximation'}.get(kind)
 if kind=='independence':
  if w.get('dependency'):return 'native_independence_with_suspended_dependency_bridge'
  if w.get('revolt'):return 'native_secession_bridge'
 if not route:raise ValueError('Unsupported objective or missing independence evidence: '+kind)
 return route

def build(mod):
 source=read(RUN/'source/wars.json');mapping=read(RUN/'political/conversion_report.json');audit=read(AUDIT)
 policy=read(ROOT/'config/personal/opening_wars.json');policy['source_sha256']=source['source_sha256'];policy['source_date']=audit['date'];policy['war_overrides']={}
 for w in source['wars']:
  route=war_route(w)
  policy['war_overrides'][w['id']]={'source_goal':w['goals'][0]['definition'],'route':route,'basis':'source war kind; existing conversion approximation'}
 states=root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES'];owners={};provinces={};claims={}
 for key,obj in states.entries():
  owned=state_owners(obj);owners.update(owned);provinces[key[2:]]=set(owned);claims[key[2:]]={v.removeprefix('c:') for k,v in obj.entries() if k=='add_claim'}
 parents={e['target_subject']:e['target_overlord'] for e in mapping['subjects']}
 tags={str(c['source_id']):tag for tag,c in mapping['countries'].items() if c.get('source_id') is not None}
 for w in source['wars']:
  override=policy['war_overrides'][w['id']]
  if override['route']!='one_state_territorial_goal':continue
  target=tags.get(w['original_target']);leader=target;seen=set()
  while leader in parents and leader not in seen:seen.add(leader);leader=parents[leader]
  defenders={tags.get(p['source_id']) for p in w['participants'] if p['status']=='Active' and p['side']=='Defender'}
  if leader!=target and leader in defenders:override['candidate_defender_leader']=leader
 result=plan(source,policy,mapping,{str(l['id']):l['name'] for l in audit['locations']},RUN/'demographic/staging/province_population_draft.csv',owners,provinces,claims,parents)
 by_id={w['id']:w for w in source['wars']}
 for row in result:
  goal=by_id[row['id']]['goals'][0]
  if goal['kind']=='aggression':row['limitation']=goal['evidence']
 load_candidates(result,mod,GAME,RUN/'cache/tribal_land_edges.json',claims,policy['territorial_budget']['per_side'])
 native=root((GAME/'common/diplomatic_plays/00_diplomatic_plays.txt').read_text(encoding='utf-8-sig')).fields()
 recognition=root((GAME/'common/war_goal_types/22_revoke_all_claims.txt').read_text(encoding='utf-8-sig')).fields()['revoke_all_claims']
 scripts=render(result,native,recognition)
 scripts[VALUES]=price_scripts(GAME)
 for rel,body in scripts.items():text(mod/rel,body)
 write(RUN/'war_mapping.json',result);write(RUN/'war_policy.json',policy)
 print('Wars regenerated',len(result))
if __name__=='__main__':build(Path(read(RUN/'fresh_context.json')['mod_directory']))
