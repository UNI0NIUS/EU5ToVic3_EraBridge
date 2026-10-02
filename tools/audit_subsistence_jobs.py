"""Diagnose real unemployed workers versus local subsistence vacancies.

Read-only: changing a profession is not equivalent to hiring a pop. Keep the
population database intact and distinguish capacity from actual employment.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from economy_model import Target
from extract_m3_politics import fields, sequence
from pdx_text import root, Object

GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')


def audit(path, tags):
    data=path.read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    doc=root(data.decode('utf-8-sig')).fields()
    del data
    def db(name): return fields(fields(doc.get(name)).get('database'))
    countries={i:fields(o) for i,o in db('country_manager').items() if isinstance(o,Object)}
    countries={i:o for i,o in countries.items() if o.get('definition') in tags}
    states={i:fields(o) for i,o in db('states').items() if isinstance(o,Object)}
    states={i:o for i,o in states.items() if o.get('country') in countries}
    target=Target(GAME)
    buildings={}
    transfers=[]
    for i,o in db('building_manager').items():
        if not isinstance(o,Object): continue
        f=fields(o)
        if f.get('state') not in states or not f.get('building','').startswith('building_subsistence_'): continue
        pms=sequence(f.get('production_methods'))
        numeric=target.numeric(pms)
        levels=int(f.get('levels',0))
        buildings[i]={'id':i,'state_id':f['state'],'building':f['building'],'levels':levels,
            'peasant_capacity_from_pm':numeric['building_employment_peasants_add']*levels,
            'staffed_level_equivalents':float(f.get('staffing',0)),
            'hiring_rate':float(f.get('hiring_rate',0)), 'production_methods':pms}
        for _,t in fields(f).get('employee_transfers',Object('',0,0)).entries():
            tf=fields(t)
            if tf.get('old_pop_type')!='peasants' and tf.get('new_pop_type')=='peasants':
                transfers.append({'state':states[f['state']]['region'],'country':countries[states[f['state']]['country']]['definition'],
                    'building_id':i,**{k:v for k,v in tf.items() if not isinstance(v,Object)}})
    counts=defaultdict(Counter); employed=defaultdict(Counter)
    for _,o in fields(doc['pops'])['database'].entries():
        if not isinstance(o,Object):continue
        f=fields(o);s=f.get('location')
        if s not in states:continue
        workers=int(f.get('workforce',0));people=workers+int(f.get('dependents',0))
        counts[s]['population']+=people
        counts[s]['workforce']+=workers
        if f.get('workplace') in buildings:
            employed[f['workplace']][f.get('type')]+=workers
            counts[s]['subsistence_workers']+=workers
        if 'workplace' not in f and workers:
            counts[s]['unemployed_workers']+=workers
            counts[s]['unemployed_'+f.get('type','unknown')]+=workers
    bystate=defaultdict(list)
    for i,b in buildings.items():
        b['actual_workers_by_profession']=dict(employed[i])
        # Peasant positions may legally be staffed by enslaved workers as well.
        b['occupied_peasant_slots']=employed[i]['peasants']+employed[i]['slaves']
        b['vacant_peasant_slots']=max(0,b['peasant_capacity_from_pm']-b['occupied_peasant_slots'])
        bystate[b['state_id']].append(b)
    rows=[]
    for i,s in states.items():
        c=counts[i]; vacancy=sum(b['vacant_peasant_slots'] for b in bystate[i])
        rows.append({'state':s['region'],'state_id':i,'country':countries[s['country']]['definition'],
            **dict(c),'arable_land':int(s.get('arable_land',0)),
            'subsistence_levels':sum(b['levels'] for b in bystate[i]),
            'peasant_capacity':sum(b['peasant_capacity_from_pm'] for b in bystate[i]),
            'vacant_peasant_slots':vacancy,'possible_local_reassignment_workers':min(vacancy,c['unemployed_workers']),
            'unemployment_beyond_local_subsistence_vacancies':max(0,c['unemployed_workers']-vacancy),
            'buildings':bystate[i]})
    totals={}
    for tag in sorted(tags):
        rs=[r for r in rows if r['country']==tag]
        totals[tag]={k:sum(r.get(k,0) for r in rs) for k in ('population','workforce','unemployed_workers','unemployed_laborers',
            'subsistence_workers','subsistence_levels','peasant_capacity','vacant_peasant_slots','possible_local_reassignment_workers','unemployment_beyond_local_subsistence_vacancies')}
        totals[tag]['non_peasant_to_peasant_transfers_recorded']=sum(int(t.get('transfer_total',0)) for t in transfers if t['country']==tag)
    return {'save':str(path.resolve()),'sha256':sha,'date':doc['date'],'playthrough_id':doc.get('playthrough_id'),
        'game_version':fields(doc.get('meta_data')).get('version'),'mods':sequence(fields(doc.get('meta_data')).get('mods')),
        'countries':totals,'states':rows,'recent_non_peasant_to_peasant_transfers':transfers,
        'limitations':['Snapshot is evidence for this campaign, not proof of the exact installed mod revision.',
            'Vacancies use serialized active PM base employment and actual worker records; dependent persons do not consume worker slots.',
            'Slave employment also consumes peasant slots. No cross-state migration is assumed.',
            'Transfers are only records retained in this snapshot, not a complete transition history.',
            'This audit neither changes population professions nor creates land or jobs.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--countries',nargs='+',default=['ITA','BOH']);args=p.parse_args()
    assert args.output.resolve()!=args.save.resolve()
    result=audit(args.save,set(args.countries));args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'date':result['date'],'countries':result['countries']},ensure_ascii=False))
