"""Attach zero-population native terrain to its current source-reference country.

Explicit user-selected island exception. This never reallocates people or joins
inhabited ethnic countries across sea gaps.
"""
from collections import Counter,defaultdict
from build_m2_prototype import allocate

def attach(world,plan,seeds,populations,location_weights):
    inverse=defaultdict(set)
    for p,names in world.mapping.items():
        if p in world.province_state:
            for name in names:inverse[name].add(p)
    by_location=defaultdict(Counter);country_population=Counter();state_population=Counter();province_population=Counter()
    for name,cultures in populations.items():
        amount=sum(cultures.values())
        if not amount:continue
        targets=inverse[name]
        if not targets:raise ValueError('Unmapped populated reference: '+name)
        for p,n in allocate(amount,location_weights.get(name,{p:1 for p in targets})).items():
            tag=world.owners[world.province_state[p]][p]
            by_location[name][tag]+=n;country_population[tag]+=n;state_population[world.province_state[p],tag]+=n;province_population[p]+=n
    empty={t for t,c in world.countries.items() if c.get('generated_uncolonized') and not country_population[t]
           and not c.get('explicit_template_persons') and not c.get('explicit_population_template')}
    decisions=[]
    for tag in sorted(empty):
        provinces=[p for ps in world.owners.values() for p,t in ps.items() if t==tag]
        references={n for p in provinces for n in seeds[plan['provinces'][p]['root']]['source_locations']}
        candidates=Counter()
        for name in sorted(references):
            for target,n in by_location[name].items():
                if n and target not in empty:candidates[target]+=n
        same=Counter({t:n for t,n in candidates.items() if world.countries[t]['culture']==world.countries[tag]['culture']})
        pool=same or candidates;ranked=pool.most_common()
        if not ranked or (len(ranked)>1 and ranked[0][1]==ranked[1][1]):raise ValueError('Ambiguous empty native reference: '+tag)
        winner=ranked[0][0]
        decisions.append(dict(from_country=tag,to_country=winner,culture=world.countries[tag]['culture'],
            target_culture=world.countries[winner]['culture'],source_references=sorted(references),
            candidate_centipersons=dict(candidates),same_culture_reference_preferred=bool(same),
            provinces=sorted(provinces),population_transferred=0,
            basis='User-authorized empty-terrain exception: current populated owner of the source reference, not a vanilla country'))
        for p in provinces:world.owners[world.province_state[p]][p]=winner
    # An attachment must have residents in this state, not merely elsewhere in the country.
    # Only repair the explicitly authorized empty-terrain attachments, not real source borders.
    for decision in decisions:
        for state in sorted({world.province_state[p] for p in decision['provinces']}):
            original=decision['to_country']
            if state_population[state,original]:continue
            ps=[p for p in decision['provinces'] if world.province_state[p]==state]
            candidates={t for p,t in world.owners[state].items() if province_population[p] and world.countries[t]['culture']==decision['culture']}
            if not candidates:
                decision.setdefault('unpopulated_state_parts',[]).append(dict(state=state,owner=original,provinces=ps,basis='No same-culture resident owner inside this state; preserve reviewed ethnic reference and flag for review'))
                continue
            scores={t:min(world.distance(p,q) for p in ps for q,o in world.owners[state].items() if o==t and province_population[q]) for t in candidates}
            ranked=sorted(scores,key=lambda t:(scores[t],t))
            if len(ranked)>1 and scores[ranked[0]]==scores[ranked[1]]:raise ValueError('Ambiguous empty-state attachment: '+state)
            winner=ranked[0]
            for p in ps:world.owners[state][p]=winner
            decision.setdefault('state_owner_corrections',[]).append(dict(state=state,from_country=original,to_country=winner,provinces=ps,basis='nearest populated same-culture owner within the original state',population_transferred=0))
    for tag in empty:del world.countries[tag]
    for tag,c in world.countries.items():c['provinces']=sum(t==tag for ps in world.owners.values() for t in ps.values())
    return decisions
