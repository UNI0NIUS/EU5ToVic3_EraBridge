"""Explicit empty-population supplements without replacing another save's owners."""
from collections import Counter
from fresh_empty_state_templates import allocated_population,island_template_people
from build_m2_prototype import objects,strings,allocate
from m3_world import fields
from pdx_text import root

def apply_ownership(world,populations,weights,policy,edges=()):
    amounts=allocated_population(world,populations,weights)
    empty={s for s,ps in world.owners.items() if not sum(amounts[p] for p in ps)}
    if empty-set(policy['empty_state_templates']):
        raise ValueError('Unreviewed whole source-empty states: '+str(sorted(empty-set(policy['empty_state_templates']))))
    chosen={}
    for s in sorted(empty):
        template=policy['empty_state_templates'][s]
        current=set(world.owners[s].values())
        # Native-only consolidation is applicable only when BOTH this state and the
        # neighboring evidence are native in the CURRENT source save.
        if policy.get('empty_state_owner_modes',{}).get(s)=='join_adjacent_same_template_culture' and all(world.countries[t].get('generated_uncolonized') for t in current):
            culture=strings(fields(world.country_defs[template])['cultures'])[0];border=Counter()
            for a,b in edges:
                for p,q in ((a,b),(b,a)):
                    if world.province_state.get(p)!=s or world.province_state.get(q) in (None,s):continue
                    t=world.owners[world.province_state[q]][q];c=world.countries[t]
                    if c.get('generated_uncolonized') and c.get('culture')==culture:border[t]+=1
            ranked=border.most_common()
            if ranked and (len(ranked)==1 or ranked[0][1]>ranked[1][1]):
                world.owners[s]={p:ranked[0][0] for p in world.owners[s]}
        chosen[s]=dict(template=template,owners=dict(Counter(world.owners[s].values())),basis='explicit_empty_population_template_current_save_territory')
        for tag in chosen[s]['owners']:world.countries[tag]['explicit_population_template']=True
    return chosen

def template_groups(game,chosen,source_groups,owners):
    if {k[0] for k,n in source_groups.items() if n}&set(chosen):raise ValueError('Template overlaps source population')
    cultures={k:fields(o) for p in (game/'common/cultures').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    result=Counter();inputs=[];found=set()
    for path in sorted((game/'common/history/pops').glob('*.txt')):
        used=False
        for state,obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['POPS']):
            s=state.removeprefix('s:')
            if s not in chosen:continue
            weights=chosen[s]['owners']
            if dict(Counter(owners[s].values()))!=weights:raise ValueError('Template territory changed')
            used=True;found.add(s)
            for _,part in objects(obj):
                for op,pop in objects(part):
                    if op!='create_pop':raise ValueError('Unexpected template operation')
                    f=fields(pop);culture=f['culture'];religion=f.get('religion',cultures[culture]['religion'])
                    for t,n in allocate(int(f['size']),weights).items():result[s,t,culture,religion]+=n
        if used:inputs.append(path)
    if found!=set(chosen):raise ValueError('Explicit empty-state template missing')
    return result,inputs

def prepare_island_templates(world,game,policy,populations,weights,mapping,religions,faiths):
    amounts=allocated_population(world,populations,weights);result={}
    for p,r in island_template_people(game,policy).items():
        state=world.province_state[p];tag=world.owners[state][p]
        # An island exception is inapplicable once that state part has source people.
        if any(amounts[q] for q,t in world.owners[state].items() if t==tag):continue
        evidence=populations[r['culture_reference']]
        if not evidence:raise ValueError('Island template lacks current culture evidence: '+p)
        sc=min(evidence,key=lambda k:(-evidence[k],k));faith=Counter()
        for (cu,rel),n in faiths[r['culture_reference']].items():
            if cu==sc:faith[rel]+=n
        if not faith:raise ValueError('Island template lacks current religion evidence: '+p)
        sr=min(faith,key=lambda k:(-faith[k],k))
        r.update(owner=tag,culture=mapping[sc],religion=religions[sr]);result[p]=r
        world.countries[tag]['explicit_population_template']=True
    return result
