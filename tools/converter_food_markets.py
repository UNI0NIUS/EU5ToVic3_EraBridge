"""Static market food scenario from effective V3 political and transport history."""
from collections import Counter,defaultdict
from pathlib import Path
from pdx_text import root,Object
from build_m2_prototype import objects
from economy_model import definitions
from extract_m3_politics import fields,sequence


def market_membership(tags,diplomacy,blocs,actions,identities,principles):
    parents={t:t for t in tags};reasons=defaultdict(list);memberships=defaultdict(list)
    def find(t):
        while parents[t]!=t:parents[t]=parents[parents[t]];t=parents[t]
        return t
    def join(leader,member,reason):
        if leader not in parents or member not in parents or member in independent:return
        a,b=find(leader),find(member)
        if a!=b:parents[b]=a
        reasons[member].append(reason)
    pacts=[]
    for text in diplomacy:
        for _,outer in objects(root(text)):
            for owner,obj in objects(outer):
                for k,v in objects(obj):
                    if k=='create_diplomatic_pact':
                        f=fields(v);pacts.append((owner[2:],str(f.get('country',''))[2:],f.get('type')))
    independent={b for a,b,kind in pacts if fields(actions.get(kind,{}).get('pact')).get('market_owner')=='second_country' or kind=='grant_own_market'}
    for a,b,kind in pacts:
        pact=fields(actions.get(kind,{}).get('pact'))
        if pact.get('subject_type') or pact.get('market_owner')=='first_country':join(a,b,'附属或共同市场协议：'+str(kind))
    def common_market(f):return fields(f.get('power_bloc_modifier')).get('power_bloc_customs_union_bool')=='yes'
    for text in blocs:
        for _,outer in objects(root(text)):
            for owner,obj in objects(outer):
                added=[]
                for k,v in objects(obj):
                    if k=='power_bloc':added += [p for field,p in v.entries() if field=='add_principle']
                for k,v in objects(obj):
                    if k!='create_power_bloc':continue
                    f=fields(v);leader=owner[2:];name=f.get('name',leader)
                    active=[p for field,p in v.entries() if field in ('principle','add_principle')]+added
                    union=common_market(identities.get(f.get('identity'),{})) or any(common_market(principles.get(p,{})) for p in active)
                    members=[leader]+[str(t)[2:] for field,t in v.entries() if field=='member']
                    for member in members:
                        if member not in parents:continue
                        memberships[member].append(dict(name=name,leader=leader,customs_union=union))
                        if union:join(leader,member,'国家集团关税同盟：'+name)
    return {t:find(t) for t in sorted(parents)},dict(memberships),dict(reasons)


def political_inputs(world):
    original=getattr(world,'_original_world',world)
    cache=getattr(original,'_market_rules',None)
    if cache is None:
        cache={}
        for key,folder in [('actions','diplomatic_actions'),('identities','power_bloc_identities'),('principles','power_bloc_principles')]:
            cache[key]=definitions(world.game/'common'/folder);cache[key].update(definitions(world.mod/'common'/folder))
        original._market_rules=cache
    override=getattr(world,'_political_reconciliation',({},[]))[0]
    def documents(folder):
        paths={p.relative_to(world.mod).as_posix():p.read_text(encoding='utf-8-sig') for p in sorted((world.mod/folder).glob('*.txt'))}
        paths.update({rel:text for rel,text in override.items() if rel.startswith(folder+'/')})
        return list(paths.values())
    capitals={}
    for text in documents('common/country_definitions'):
        for tag,obj in objects(root(text)):
            if 'capital' in fields(obj):capitals[tag]=fields(obj)['capital']
    return documents('common/history/diplomacy'),documents('common/history/power_blocs'),capitals,cache


def transport_access(rows,markets,capitals,edges,coasts,buildings,target,techs):
    by_key={(r['state'],r['country']):r for r in rows};parents={k:k for k in by_key}
    provinces={p:(r['state'],r['country']) for r in rows for p in r['provinces']}
    def find(k):
        while parents[k]!=k:parents[k]=parents[parents[k]];k=parents[k]
        return k
    def join(a,b):
        a,b=find(a),find(b)
        if a!=b:parents[max(a,b)]=min(a,b)
    for a,b in edges:
        x,y=provinces.get(a),provinces.get(b)
        if x and y and markets[x[1]]==markets[y[1]]:join(x,y)
    local=defaultdict(list)
    for b in buildings:local[b['state'],b['owner']].append(b)
    ports=set()
    for key,row in by_key.items():
        if set(row['provinces'])&coasts and any(b['building']=='building_port' and b['levels']>0 and 'pm_anchorage' not in b['pms'] for b in local[key]):ports.add(find(key))
    market_rows=defaultdict(list)
    for key in by_key:market_rows[markets[key[1]]].append(key)
    main={}
    for owner,keys in market_rows.items():
        capital=(capitals.get(owner),owner)
        if capital not in by_key:capital=max(keys,key=lambda k:(k[1]==owner,by_key[k]['population'],k))
        main[owner]=find(capital)
    # Shipping is a capacity scenario: both land components need a productive
    # coastal port. Fleet tonnage, convoys and blockades still require runtime.
    access={};usage_cache={}
    for key,row in by_key.items():
        component=find(key);anchor=main[markets[key[1]]]
        connected=component==anchor or component in ports and anchor in ports
        try:
            usage=0
            for b in local[key]:
                if b['building'] not in usage_cache:usage_cache[b['building']]=target.infrastructure_usage(b['building'])
                usage+=usage_cache[b['building']]*b['levels']
            capacity=target.infrastructure(key[0],row['population'],techs[key[1]],local[key])
            ratio=min(1,max(0,capacity)/usage) if usage>0 else 1
            access[key]=dict(ratio=ratio if connected else 0,connected=bool(connected),infrastructure=capacity,infrastructure_usage=usage)
        except (ValueError,KeyError):access[key]=dict(ratio=None,connected=bool(connected),infrastructure=None,infrastructure_usage=None)
    return access


def allocate_food(rows,markets,access,threshold):
    """Pool only accessible net output, so imports cannot be counted twice."""
    pools=defaultdict(lambda:dict(goods=Counter(),demand=0,unknown=False,countries=set()))
    for row in rows:
        key=row['state'],row['country'];a=access[key]['ratio'];pool=pools[markets[row['country']]]
        pool['countries'].add(row['country'])
        if a is None:pool['unknown']=True;continue
        pool['demand']+=row['food_demand']*a
        if row['food_supply'] is None and a:pool['unknown']=True
        for good,value in row.get('food_net',{'food':row['food_supply'] or 0}).items():pool['goods'][good]+=value*a
    for pool in pools.values():
        pool['supply']=sum(max(0,v) for v in pool['goods'].values())
        pool['shortfall']=None if pool['unknown'] else max(0,1-pool['supply']/pool['demand']) if pool['demand'] else 0
    for row in rows:
        a=access[row['state'],row['country']]['ratio'];owner=markets[row['country']];pool=pools[owner]
        row['local_food_shortfall']=row['food_shortfall']
        row['market_owner']=owner;row['market_food_shortfall']=pool['shortfall']
        row['market_access_estimate']=a;row['market_connected']=access[row['state'],row['country']]['connected']
        row['market_members']=len(pool['countries'])
        demand=row['food_demand'];local=row['food_supply']
        if a==0:effective=row['local_food_shortfall']
        elif a is None or local is None or pool['shortfall'] is None:effective=None
        elif demand:
            available=(1-a)*local+a*demand*(1-pool['shortfall'])
            effective=max(0,1-available/demand)
        else:effective=0
        row['food_shortfall']=effective
        row['risks']=[r for r in row['risks'] if r!='food']
        if effective is not None and effective+1e-12>=threshold:row['risks'].append('food')
    return {owner:dict(countries=sorted(p['countries']),supply=p['supply'],demand=p['demand'],shortfall=p['shortfall']) for owner,p in pools.items()}


def apply(world,rows,options):
    diplomacy,blocs,capitals,rules=political_inputs(world)
    markets,memberships,reasons=market_membership({r['country'] for r in rows},diplomacy,blocs,**rules)
    access=transport_access(rows,markets,capitals,getattr(world,'transport_edges',world.edges),getattr(world,'coastal_provinces',set()),world.buildings,world.target,world.techs)
    result=allocate_food(rows,markets,access,options['food_shortfall_threshold'])
    for row in rows:
        row['market_name']=world.labels.get(row['market_owner'],row['market_owner'])
        row['power_blocs']=memberships.get(row['country'],[])
        row['market_evidence']=reasons.get(row['country'],[])
    return result
