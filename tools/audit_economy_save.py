"""Read a plaintext/decoded V3 save for economic acceptance; no save modification.

For binary saves first use inspect_save_metadata.py --game vic3 --full-output.
Never treat an old mod's runtime data as validation of a new candidate.
"""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from economy_model import definitions
from extract_m3_politics import fields,sequence
from m3_world import digest
from pdx_text import Object,root


def audit(save,tags,expected_mod=None):
    doc=root(save.read_text(encoding='utf-8-sig')).fields()
    metadata=fields(doc.get('meta_data'))
    mods=sequence(metadata.get('mods'))
    if expected_mod and expected_mod not in mods:
        raise ValueError('Save does not list the requested candidate mod: '+expected_mod)
    def db(name): return fields(fields(doc.get(name)).get('database'))
    countries={i:fields(o) for i,o in db('country_manager').items() if isinstance(o,Object) and fields(o).get('definition') in tags}
    states={i:fields(o) for i,o in db('states').items() if isinstance(o,Object) and fields(o).get('country') in countries}
    famine={fields(o).get('state'):fields(o) for o in db('famine_manager').values() if isinstance(o,Object)}
    aggregate=defaultdict(Counter)
    food_states=defaultdict(Counter)
    occupations=defaultdict(Counter)
    for o in db('pops').values():
        if not isinstance(o,Object): continue
        p=fields(o);s=p.get('location')
        if s not in states: continue
        n=int(p.get('workforce',0))+int(p.get('dependents',0))
        aggregate[s]['population']+=n
        aggregate[s]['workforce']+=int(p.get('workforce',0))
        if 'wealth' in p:
            aggregate[s]['wealth_weighted']+=float(p['wealth'])*n
            aggregate[s]['wealth_population']+=n
        if 'previous_quality_of_life' in p:
            aggregate[s]['sol_weighted']+=float(p['previous_quality_of_life'])*n
            aggregate[s]['sol_population']+=n
        occupations[states[s]['country']][p.get('type','unknown')]+=n
        food=fields(p.get('food_security'))
        food_states[states[s]['country']][food.get('state','not_serialized')]+=n
    output={}
    for cid,c in countries.items():
        budget=fields(c.get('budget'));rows=[];total=Counter()
        for sid,s in states.items():
            if s['country']!=cid: continue
            a=aggregate[sid];total.update(a)
            stats=fields(s.get('pop_statistics'))
            rows.append({'id':sid,'state':s.get('region'),'population':a['population'],
                         'unemployed_workers':int(stats.get('population_unemployed_workforce',0)),
                         'subsisting_workers':int(stats.get('population_subsisting_workforce',0)),
                         'arable_land':s.get('arable_land'),'infrastructure':s.get('infrastructure'),
                         'infrastructure_usage':s.get('infrastructure_usage'),
                         'market_access_serialized':s.get('market_access'),
                         'famine':{k:v for k,v in famine.get(sid,{}).items() if not isinstance(v,Object)} or None})
        income=sum(float(v) for v in sequence(budget.get('weekly_income'))) if 'weekly_income' in budget else None
        expenses=sum(float(v) for v in sequence(budget.get('weekly_expenses'))) if 'weekly_expenses' in budget else None
        output[c['definition']]={'country_id':cid,'population':total['population'],'workforce':total['workforce'],
            'population_weighted_wealth':total['wealth_weighted']/total['wealth_population'] if total['wealth_population'] else None,
            'population_weighted_previous_quality_of_life':total['sol_weighted']/total['sol_population'] if total['sol_population'] else None,
            'food_security_persons':dict(food_states[cid]),'occupation_persons':dict(occupations[cid]),
            'population_statistics':{k:v for k,v in fields(c.get('pop_statistics')).items() if not isinstance(v,Object)},
            'weekly_income':income,'weekly_expenses':expenses,'weekly_balance':None if income is None or expenses is None else income-expenses,
            'money':budget.get('money'),'credit':budget.get('credit'),
            'states_with_famine_records':sum(r['famine'] is not None for r in rows),'states':rows}
    return {'date':doc.get('date'),'save':str(save.resolve()),'sha256':digest(save),'mods':mods,
            'expected_mod_confirmed':bool(expected_mod),'countries':output,
            'limitations':['A single observation does not establish sustained balance.',
                           'Missing market-access serialization is unknown, not 100 percent. Inspect the in-game map.',
                           'Famine records are reported verbatim; inspect dates and runtime status before attributing population loss.',
                           'GDP and actual goods shortages/prices still require a game UI or dedicated market audit.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--countries',nargs='+',default=['ITA','BOH']);p.add_argument('--expected-mod')
    a=p.parse_args()
    if a.output.resolve()==a.save.resolve(): raise ValueError('Cannot overwrite save')
    result=audit(a.save,set(a.countries),a.expected_mod)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'date':result['date'],'countries':list(result['countries']),'expected_mod_confirmed':result['expected_mod_confirmed']}))
