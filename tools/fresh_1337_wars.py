from build_fresh_1337 import *
from opening_wars import plan,render
from build_m2_prototype import state_owners
from border_war_goals import load_candidates,price_scripts,VALUES

def build(mod):
 source=read(RUN/'source/wars.json');mapping=read(RUN/'political/conversion_report.json');audit=read(AUDIT)
 policy=read(ROOT/'config/personal/opening_wars.json');policy['source_sha256']=source['source_sha256'];policy['source_date']=audit['date'];policy['war_overrides']={}
 for w in source['wars']:
  kind=w['goals'][0]['kind']
  route={'civil_war':'native_civil_war_annexation','take_province':'one_state_territorial_goal','superiority':'humiliation_approximation'}.get(kind)
  if not route:raise ValueError('Unsupported objective '+kind)
  policy['war_overrides'][w['id']]={'source_goal':w['goals'][0]['definition'],'route':route,'basis':'source war kind; existing conversion approximation'}
 states=root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES'];owners={};provinces={};claims={}
 for key,obj in states.entries():
  owned=state_owners(obj);owners.update(owned);provinces[key[2:]]=set(owned);claims[key[2:]]={v.removeprefix('c:') for k,v in obj.entries() if k=='add_claim'}
 parents={e['target_subject']:e['target_overlord'] for e in mapping['subjects']}
 result=plan(source,policy,mapping,{str(l['id']):l['name'] for l in audit['locations']},RUN/'demographic/staging/province_population_draft.csv',owners,provinces,claims,parents)
 load_candidates(result,mod,GAME,ROOT/'.local/m3/cache/tribal_land_edges.json',claims,policy['territorial_budget']['per_side'])
 native=root((GAME/'common/diplomatic_plays/00_diplomatic_plays.txt').read_text(encoding='utf-8-sig')).fields()
 scripts=render(result,native)
 scripts[VALUES]=price_scripts(GAME)
 for rel,body in scripts.items():text(mod/rel,body)
 write(RUN/'war_mapping.json',result);write(RUN/'war_policy.json',policy)
 print('Wars regenerated',len(result))
if __name__=='__main__':build(Path(read(RUN/'fresh_context.json')['mod_directory']))
