"""Read native plaintext runtime saves, independently of generated history scripts."""
from pathlib import Path
import argparse,json
from pdx_text import root,Object
from extract_m3_politics import fields
from m3_world import digest
from package_m5_economic_modules import files
from decimal import Decimal


def read_save(path):
    data=fields(root(path.read_text(encoding='utf-8-sig')))
    def db(name):
        manager=fields(data[name]);dead=set()
        container=fields(manager.get('dead',root(''))).get('dead_objects',root(''))
        for _,v in container.entries():
            dead.add(fields(v)['object'] if isinstance(v,Object) else v)
        return {k:fields(v) for k,v in manager['database'].entries() if isinstance(v,Object) and k not in dead}
    countries=db('country_manager');tags={k:v['definition'] for k,v in countries.items()}
    def tag(cid):return tags.get(cid,cid)
    def values(obj):return [v for _,v in obj.entries()] if isinstance(obj,Object) else []
    states={k:{'owner':tag(v['country']),'region':v['region'],'provinces':values(fields(v['provinces'])['provinces'])} for k,v in db('states').items() if 'country' in v}
    pacts=[{'first':tag(fields(v['targets'])['first']),'second':tag(fields(v['targets'])['second']),'type':v['action']} for v in db('pacts').values()]
    goals=[]
    for k,g in db('war_goal_manager').items():
        target=fields(g['target']);sid=target.get('state')
        goals.append({'id':k,'play':g['diplomatic_play'],'type':g['type'],'holder':tag(g['holder']),
                      'target':tag(target.get('country')),'state':states.get(sid), 'status':g['status'],'demand_type':g.get('demand_type')})
    wars=db('war_manager');plays=[]
    for k,v in db('diplomatic_plays').items():
        if not v.get('type','').startswith('dp_eu5_opening_war_'):continue
        w=wars.get(v.get('war'),{})
        plays.append({'id':k,'type':v['type'],'attacker':tag(v['initiator']),'defender':tag(v['target']),
                      'attackers':sorted([tag(v['initiator'])]+[tag(i) for i in values(v.get('initiators'))]),
                      'defenders':sorted([tag(v['target'])]+[tag(i) for i in values(v.get('targets'))]),
                      'involved':sorted(tag(i) for i in values(v.get('involved'))),
                      'war':v.get('war'),'peace_date':w.get('peace_date'),
                      'war_members':sorted(tag(fields(o)['country']) for _,o in w.get('war_participants',root('')).entries()),
                      'goals':[g for g in goals if g['play']==k]})
    variables={}
    for v in countries.values():
        variables[v['definition']]={}
        for _,item in fields(v.get('variables',root(''))).get('data',root('')).entries():
            f=fields(item)
            if f['flag'].startswith('eu5_w_'):
                d=fields(f['data']);variables[v['definition']][f['flag']]=d
    return {'date':data['date'],'plays':plays,'states':states,'pacts':pacts,'budget_variables':variables,
            'countries':{v['definition']:{'dead':v.get('dead','no'),'capital':v.get('capital')} for v in countries.values()},
            'save':str(path.resolve()),'save_sha256':digest(path)}


def verify(package,runtime,peace=None):
    rows=json.loads((package/'war_mapping.json').read_text(encoding='utf-8-sig'))
    saves=list((runtime/'save games').glob('*.v3'))
    opening=read_save(next(p for p in saves if 'eu5_capture_opening' in p.name))
    errors=[]
    def check(ok,message):
        if not ok:errors.append(message)
    check(len(opening['plays'])==len(rows),'opening war count')
    budget_audit=[];selected_by_war={}
    for row in rows:
        found=[p for p in opening['plays'] if p['type']==row['play_type']]
        if len(found)!=1:errors.append(row['id']+': missing/duplicate play');continue
        p=found[0];label=row['id']+': '
        check(p['attacker']==row['attacker'] and p['defender']==row['leader_target'],label+'leaders')
        check(p['attackers']==sorted(row['attackers']) and p['defenders']==sorted(row['defenders']),label+'sides')
        expected=sorted(row['attackers']+row['defenders'])
        check(p['involved']==expected and p['war_members']==expected,label+'play/war participants')
        check(p['peace_date']=='1.1.1',label+'not active war')
        active=[g for g in p['goals'] if g['status']=='active']
        check(sum(g['demand_type']=='primary_demand' for g in active)==1,label+'exactly one primary demand')
        if 'candidates' in row:
            def number(holder,key):
                d=opening['budget_variables'][holder].get(key)
                if d is None:raise ValueError('Missing runtime budget variable: '+holder+' '+key)
                if d.get('type')!='value':raise ValueError('Budget variable is not numeric')
                # V3 serializes fixed-point script values as raw units of 1/100000.
                return Decimal(str(d.get('identity','0')))/100000
            remaining={s:Decimal(str(row['budget_per_side'])) for s in ('attacker','defender')};selected=[]
            for candidate in row['candidates']:
                holder,key=candidate['budget_holder'],candidate['key']
                price=number(holder,key+'_price');check(price>0,label+'non-positive candidate price')
                affordable=price>0 and price<=remaining[candidate['side']]
                actual=key+'_selected' in opening['budget_variables'][holder]
                check(affordable==actual,label+'greedy budget decision '+key)
                if affordable:
                    remaining[candidate['side']]-=price
                    selected.append(dict(candidate,budget_cost=float(price)))
            def identity(g):return (g['type'],g['holder'],g['target'],g['state']['region'] if isinstance(g['state'],dict) else g['state'])
            check(sorted(identity(g) for g in active)==sorted(identity(g) for g in selected),label+'selected candidate goals')
            check(bool(selected),label+'no affordable objective')
            if selected:
                primary=[g for g in active if g['demand_type']=='primary_demand']
                check(len(primary)==1 and identity(primary[0])==identity(selected[0]),label+'primary priority')
            for side,holder in [('attacker',row['attacker']),('defender',row['leader_target'])]:
                actual=number(holder,f'eu5_w_{row["id"]}_{side}_remaining')
                check(abs(actual-remaining[side])<Decimal('.001') and 0<=actual<=row['budget_per_side'],label+'remaining '+side)
            selected_by_war[row['id']]=selected
            budget_audit.append({'id':row['id'],'budget_per_side':row['budget_per_side'],
                                 'spent':{s:float(Decimal(str(row['budget_per_side']))-n) for s,n in remaining.items()},'selected':selected})
            continue
        goal='eu5_recognize_secession' if row['goal']=='secession' else row['goal']
        wanted=[(goal,row['attacker'],row['target'])]
        if row['goal']=='secession':wanted.append(('annex_country',row['target'],row['attacker']))
        check(sorted((g['type'],g['holder'],g['target']) for g in active)==sorted(wanted),label+'effective goals')
        if row.get('state'):
            selected=[g for g in active if g['type']==goal]
            check(len(selected)==1 and selected[0]['state']['region']==row['state'] and selected[0]['state']['owner']==row['owner'],label+'state target')
    check({'first':'MAY','second':'EA4','type':'puppet'} in opening['pacts'],'suspended dependency bridge missing')
    colonial=[p for p in opening['pacts'] if p['first']=='ITA' and p['second']=='E9C']
    check(len(colonial)==1,'colonial relationship not preserved')
    result={'status':'passed' if not errors else 'failed','errors':errors,'opening':opening,
            'tested_output_sha256':files(package/'eu5_economy_test'),'budget_audit':budget_audit,
            'single_primary_verified':not any('primary' in e for e in errors)}
    if peace:
        after=read_save(next(p for p in saves if 'eu5_capture_peace' in p.name));result['peace']=after;result['peace_winner']=peace
        check(all(p['peace_date'] not in (None,'1.1.1') for p in after['plays']),'wars not resolved')
        pact={'first':'MAY','second':'EA4','type':'puppet'}
        check((pact in after['pacts'])==(peace=='target'),'independence peace outcome')
        check(all(p in after['pacts'] for p in colonial),'colonial pact lost at peace')
        for row in rows:
            if row.get('state') and 'candidates' not in row:
                old=[(sid,s) for sid,s in opening['states'].items() if s['region']==row['state']]
                for sid,s in old:
                    desired=row['attacker'] if peace=='initiator' and s['owner']==row['owner'] else s['owner']
                    # Transferred state IDs can merge; compare each original province set by packed IDs.
                    def expand(values):return {n for i in range(0,len(values),2) for n in range(int(values[i]),int(values[i])+int(values[i+1])+1)}
                    wanted=expand(s['provinces']);actual=set()
                    for a in after['states'].values():
                        if a['region']==row['state'] and a['owner']==desired:actual.update(expand(a['provinces']))
                    check(wanted<=actual,row['id']+': peace ownership '+s['owner']+' -> '+desired)
        changes={};affected=set()
        for row in rows:
            for c in selected_by_war.get(row['id'],[]):
                affected.add(c['state'])
                if c['side']!=('attacker' if peace=='initiator' else 'defender'):continue
                part=(c['state'],c['target'])
                check(part not in changes or changes[part]==c['holder'],'conflicting peace beneficiaries')
                changes[part]=c['holder']
        def expand(values):return {n for i in range(0,len(values),2) for n in range(int(values[i]),int(values[i])+int(values[i+1])+1)}
        for s in opening['states'].values():
            if s['region'] not in affected:continue
            desired=changes.get((s['region'],s['owner']),s['owner']);actual=set()
            for a in after['states'].values():
                if a['region']==s['region'] and a['owner']==desired:actual.update(expand(a['provinces']))
            check(expand(s['provinces'])<=actual,'budgeted peace ownership '+s['region']+' '+s['owner']+' -> '+desired)
        rebel_states=[s for s in opening['states'].values() if s['owner']=='E8S']
        owner='E8S' if peace=='initiator' else 'E7N'
        check(after['countries']['E8S']['dead']==('no' if peace=='initiator' else 'yes'),'secession country survival')
        for s in rebel_states:
            check(any(a['region']==s['region'] and a['owner']==owner for a in after['states'].values()),'secession peace territory')
    error_log=(runtime/'logs/error.log').read_text(encoding='utf-8-sig')
    errors_new=[l for l in error_log.splitlines() if any(t in l for t in ('eu5_opening_war','eu5_probe','eu5_snapshot','eu5_recognize_secession','00_eu5_world_wars','eu5_war_budget','eu5_budget_','eu5_native_'))]
    check(not errors_new,'new runtime script errors: '+str(errors_new[:10]))
    unexpected=[p.name for p in saves if 'TEST_FAIL' in p.name and 'eu5_capture_' not in p.name]
    check(not unexpected,'native test failures: '+str(unexpected))
    result['status']='passed' if not errors else 'failed'
    result['new_script_errors']=errors_new
    (runtime/'runtime_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'errors':errors,'wars':len(opening['plays']),'date':opening['date'],'peace_date':result.get('peace',{}).get('date')},ensure_ascii=False))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--peace',choices=('initiator','target'))
    a=p.parse_args();verify(a.package,a.runtime,a.peace)
