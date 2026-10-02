"""Explicit source-empty exceptions; never add template people to populated states."""
from collections import Counter, defaultdict
from build_m2_prototype import allocate, objects, strings
from m3_world import fields
from pdx_text import root

def allocated_population(world, populations, weights):
    inverse=defaultdict(set)
    for p,names in world.mapping.items():
        if p in world.province_state:
            for n in names:inverse[n].add(p)
    result=Counter()
    for n,cultures in populations.items():
        amount=sum(cultures.values())
        if amount:
            if not inverse[n]:raise ValueError('Unmapped populated location: '+n)
            result.update(allocate(amount,weights.get(n,{p:1 for p in inverse[n]})))
    return result

def apply_ownership(world,populations,weights,policy,edges=()):
    amounts=allocated_population(world,populations,weights)
    empty={s for s,ps in world.owners.items() if not sum(amounts[p] for p in ps)}
    chosen={s:t for s,t in policy['empty_state_templates'].items() if s in empty}
    if empty-set(chosen):raise ValueError('Unreviewed whole source-empty states: '+str(sorted(empty-set(chosen))))
    for s,t in list(chosen.items()):
        mode=policy.get('empty_state_owner_modes',{}).get(s)
        if mode=='join_adjacent_same_template_culture':
            template_culture=strings(fields(world.country_defs[t])['cultures'])[0];border=Counter()
            for a,b in edges:
                for p,q in [(a,b),(b,a)]:
                    if world.province_state.get(p)!=s or world.province_state.get(q) in (None,s):continue
                    tag=world.owners[world.province_state[q]][q];country=world.countries[tag]
                    if country.get('generated_uncolonized') and country.get('culture')==template_culture:border[tag]+=1
            if not border:raise ValueError('No adjacent same-culture native owner for '+s)
            ranked=border.most_common()
            if len(ranked)>1 and ranked[0][1]==ranked[1][1]:raise ValueError('Ambiguous adjacent template owner for '+s)
            winner=ranked[0][0];world.owners[s]={p:winner for p in world.owners[s]};chosen[s]=winner
            continue
        if t in world.countries:raise ValueError('Template tag already in use: '+t)
        original=fields(world.country_defs[t]);culture=strings(original['cultures'])[0]
        world.owners[s]={p:t for p in world.owners[s]}
        world.countries[t]=dict(source_id=None,tag=t,template=t,country_type='decentralized',capital=s,capital_exact=True,
            culture=culture,cultures=strings(original['cultures']),source_empty_template=True,
            provinces=len(world.owners[s]),type_reason='previously_authorized_source_empty_state_template')
    return chosen

def template_groups(game,chosen,source_groups,owners):
    occupied={k[0] for k,n in source_groups.items() if n}
    if occupied & set(chosen):raise ValueError('Template overlaps source population')
    for s,t in chosen.items():
        if set(owners[s].values())!={t}:raise ValueError('Template state is split: '+s)
    cultures={k:fields(o) for p in (game/'common/cultures').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    result=Counter();inputs=[]
    for p in sorted((game/'common/history/pops').glob('*.txt')):
        used=False
        for state,obj in objects(root(p.read_text(encoding='utf-8-sig')).fields()['POPS']):
            s=state.removeprefix('s:')
            if s not in chosen:continue
            used=True
            for _,part in objects(obj):
                for op,pop in objects(part):
                    if op!='create_pop':raise ValueError('Unexpected template operation: '+op)
                    f=fields(pop);cu=f['culture'];rel=f.get('religion',cultures[cu]['religion'])
                    result[s,chosen[s],cu,rel]+=int(f['size'])
        if used:inputs.append(p)
    if {k[0] for k,n in result.items() if n}!=set(chosen):raise ValueError('Template population missing')
    return result,inputs


def island_template_people(game,policy):
    """Read the explicitly authorized, commented vanilla island reference."""
    result={}
    for p,r in policy.get('island_population_templates',{}).items():
        path=game/r['population_reference_file'];raw=path.read_text(encoding='utf-8-sig')
        state=dict(objects(root(raw).fields()['POPS']))['s:'+r['state']]
        import re
        commented='\n'.join(re.sub(r'^\s*# ?', '', line) for line in state.text().splitlines() if re.match(r'^\s*#',line))
        # Descriptive comment lines are omitted; only the explicit region block is parsed.
        start=commented.index('region_state:'+r['commented_template_owner'])
        obj=dict(objects(root(commented[start:]))).get('region_state:'+r['commented_template_owner'])
        if obj is None:raise ValueError('Commented island template missing')
        n=sum(int(fields(pop)['size']) for op,pop in objects(obj) if op=='create_pop')
        if n<=0:raise ValueError('Empty island template')
        result[p]=dict(r,persons=n,reference_sha256=__import__('m3_world').digest(path),reference_active_in_vanilla=False)
    return result

def prepare_island_templates(world,game,policy,populations,weights,mapping,religions,faiths):
    amounts=allocated_population(world,populations,weights);result=island_template_people(game,policy)
    for p,r in result.items():
        if amounts[p]:raise ValueError('Island supplement overlaps source population: '+p)
        state=world.province_state[p];tag=world.owners[state][p];country=world.countries[tag]
        if not country.get('generated_uncolonized'):raise ValueError('Island native reference resolved to a source country')
        evidence=populations[r['culture_reference']]
        sc=min(evidence,key=lambda k:(-evidence[k],k));cu=mapping[sc]
        if country['culture']!=cu:raise ValueError('Island culture differs from source reference')
        faith=Counter()
        for (culture,rel),n in faiths[r['culture_reference']].items():
            if culture==sc:faith[rel]+=n
        sr=min(faith,key=lambda k:(-faith[k],k))
        r.update(owner=tag,culture=cu,religion=religions[sr]);country['explicit_template_persons']=r['persons']
    return result
