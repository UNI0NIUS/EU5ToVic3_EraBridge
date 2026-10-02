"""Apply existing political and military evidence rules before economic generation."""
from build_fresh_1337 import *
from economy_model import Target,definitions,closure
from military_technology_design import evaluate as military_evaluate,validate
from deploy_political_rules import deployment_laws,institution_plan,history_body
from build_economy import expand_template_tech
from technology_mapping import TechnologyMapper

def build():
 c=read(RUN/'fresh_context.json');mod=Path(c['mod_directory']);review=read(RUN/'political-rules/report.json');source=read(RUN/'source/economy.json');mapping=read(Path(c['political_run'])/'conversion_report.json')
 target=Target(GAME);lawdefs={k:fields(o) for k,o in defs(mod,'laws').items()}
 ep=read(ROOT/'config/personal/economy.json');mp=read(ROOT/'config/personal/military_technology.json');advances=definitions(EU5/'in_game/common/advances');validate(mp,target,advances,definitions(EU5/'in_game/common/unit_types'),definitions(EU5/'in_game/common/institution'))
 from economy_model import british_baseline
 baseline=british_baseline(ROOT/'.local/m0/clean-starts/vic3-start.txt',target);mapper=TechnologyMapper(EU5,target,baseline['technologies'],ep['technology_progression'],ep['technology_rules'])
 actual=defaultdict(set);regular=set();ships={r['owner'] for r in read(RUN/'source/navy.json')['ships']}
 for r in read(RUN/'source/military.json')['subunits']:
  if not r['levies'] and not r['mercenary']:
   actual[r['owner']].add(r['type'])
   if r['category']!='army_auxiliary':regular.add(r['owner'])
 path=mod/'common/history/countries/00_eu5_world.txt';old=root(path.read_text(encoding='utf-8-sig')).fields()['COUNTRIES'];bodies=[];audits={}
 for key,obj in objects(old):
  tag=key[2:];country=mapping['countries'][tag];sid=country['source_id'];r=review['countries'][tag]
  if not sid:
   bodies.append(block(key+' ?',obj.text()));continue
  laws,overrides=deployment_laws(r,lawdefs)
  # Preserve the source shogunate/union law established by the political exporter.
  for op,value in obj.entries():
   if op=='activate_law' and value.split(':')[-1] in ('law_eu5_bakufu','law_eu5_tenno'):
    law=value.split(':')[-1];laws[lawdefs[law]['group']]=law
  mapped,_=mapper.map(source['countries'][sid]);mil,decisions=military_evaluate(source['countries'][sid],actual[sid],sid in regular,sid in ships,mp,target,advances)
  tech={t for t in mapped if target.techs[t]['category']!='military'}|mil|set(r['capability_technology_proposals'])
  for law in laws.values():tech.update(strings(lawdefs[law]['unlocking_technologies']) if lawdefs[law].get('unlocking_technologies') else [])
  tech=closure(tech,target.techs);levels,caps=institution_plan(r,set(laws.values()),tech,lawdefs,target)
  bodies.append(block(key+' ?',history_body(obj.text(),laws,tech,levels)));audits[tag]=dict(laws=laws,overrides=overrides,technologies=sorted(tech),military=decisions,institutions=levels)
 text(path,block('COUNTRIES',''.join(bodies)));write(RUN/'deployed_source_politics.json',audits)
 text(mod/'common/history/buildings/00_eu5_world.txt',block('BUILDINGS','# All capacity regenerated from source; no territorial template stock.'))
 text(mod/'common/history/military_formations/00_eu5_world.txt',block('MILITARY_FORMATIONS','# Source regular armies and fleets are generated in economic completion.'))
 r=read(RUN/'base/package_report.json');r['output_sha256']=files(mod);write(RUN/'base/package_report.json',r)
 print('Applied source laws and technology',len(audits))
if __name__=='__main__':build()
