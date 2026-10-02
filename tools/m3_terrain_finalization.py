"""Refresh terrain inheritance after political ownership has reached its final state."""
from collections import Counter,defaultdict
import copy
import heapq


def plan(owners,repairs,countries,edges,population_votes=None,country_population=None):
    result=copy.deepcopy(owners);votes=population_votes or {};refresh=[];candidates={};mutable=set()
    # geometry() picks anchors before creating source-native tribal countries.
    # Reuse that explicit geographic provenance; never use a vanilla country as
    # a fresh ownership default or propagate from an already filled province.
    for r in repairs:
        if r['rule'] not in ('wasteland','new_target_province'):continue
        s,p,q=r['state'],r['province'],r['neighbor']
        old=owners[s][p];anchor=owners[s][q]
        if old==anchor:continue
        local={t:n for t,n in votes.get(p,{}).items() if n>0}
        candidates[p]={'state':s,'province':p,'from':old,'neighbor':q,'source_owner_votes':local}
        if local:result[s][p]=min(local,key=lambda t:(-local[t],t))
        else:mutable.add(p)
    # A centroid-nearest anchor can sit across somebody else's territory. Grow
    # only through actual land adjacency so filling terrain cannot create an
    # isolated patch on the other side of a reviewed source-owned settlement.
    adjacent=defaultdict(set)
    for a,b in edges:adjacent[a].add(b);adjacent[b].add(a)
    flat={p:t for ps in result.values() for p,t in ps.items()};queue=[];best={}
    for p in sorted(mutable):
        for q in sorted(adjacent[p]-mutable):
            if q in flat:heapq.heappush(queue,(1,q,p,flat[q]))
    while queue:
        distance,seed,p,owner=heapq.heappop(queue)
        if p in best:continue
        best[p]=(distance,seed,owner)
        for q in sorted(adjacent[p]&mutable):
            if q not in best:heapq.heappush(queue,(distance+1,seed,q,owner))
    unresolved=[{**candidates[p],'reason':'no_land_connected_final_evidence_retain_for_review'} for p in sorted(mutable-set(best))]
    for p,(distance,seed,owner) in best.items():result[candidates[p]['state']][p]=owner
    for p,r in sorted(candidates.items()):
        new=result[r['state']][p]
        if new!=r['from']:
            refresh.append({**r,'to':new,'reason':'reviewed_source_owned_population' if r['source_owner_votes'] else 'final_land_connected_owner',
                'land_seed':best[p][1] if p in best else p})
    # Newly attached terrain can join formerly separate same-culture tribal
    # components. Consolidate only generated tribes, never source countries.
    generated={t:c for t,c in countries.items() if c.get('generated_uncolonized')}
    parent={t:t for t in generated}
    def find(t):
        while parent[t]!=t:parent[t]=parent[parent[t]];t=parent[t]
        return t
    flat={p:t for ps in result.values() for p,t in ps.items()}
    for a,b in edges:
        x,y=flat.get(a),flat.get(b)
        if x not in generated or y not in generated or generated[x]['culture']!=generated[y]['culture']:continue
        x,y=find(x),find(y)
        if x!=y:parent[max(x,y)]=min(x,y)
    groups=defaultdict(list)
    for t in generated:groups[find(t)].append(t)
    aliases={};population=country_population or {}
    for group in groups.values():
        keep=min(group,key=lambda t:(-population.get(t,0),t))
        aliases.update({t:keep for t in group if t!=keep})
    for s,ps in result.items():
        for p,t in ps.items():ps[p]=aliases.get(t,t)
    changes=[{'state':s,'province':p,'from':t,'to':result[s][p]} for s,ps in owners.items() for p,t in ps.items() if t!=result[s][p]]
    live={t for ps in result.values() for t in ps.values()}
    empty=[t for t,c in countries.items() if t not in live and t not in aliases]
    if any(countries[t].get('source_id') is not None for t in empty):raise ValueError('Terrain update removed a source country')
    return {'schema':1,'stale_candidates':len(candidates),'anchor_refresh':refresh,'unresolved':unresolved,'country_aliases':aliases,'changes':changes,
            'removed_empty_fallbacks':sorted(empty),
            'rule':'refresh_recorded_nearest_anchor_after_politics_with_reviewed_owned_population_priority_then_merge_contiguous_same_culture_generated_tribes'}


def apply(world,report):
    for r in report['changes']:
        if world.owners[r['state']][r['province']]!=r['from']:raise ValueError('Terrain baseline changed')
    for r in report['changes']:world.owners[r['state']][r['province']]=r['to']
    for tag in report['country_aliases']:
        if not world.countries[tag].get('generated_uncolonized'):raise ValueError('Cannot merge source country')
        del world.countries[tag]
    for tag in report.get('removed_empty_fallbacks',[]):del world.countries[tag]
    world.substates={s:Counter(ps.values()) for s,ps in world.owners.items()}
    for tag,c in world.countries.items():c['provinces']=sum(ps[tag] for ps in world.substates.values())
    world.transfers={(s,t):Counter(world.owners[s][p] for p,v in old.items() if v==t and p in world.owners[s]) for s,old in world.original.items() for t in set(old.values())}


def prepare(world,stage=None):
    from pathlib import Path
    from package_m4_population_test import rows
    from m3_uncolonized import province_land_edges
    from m3_world import digest
    votes=defaultdict(Counter);population=Counter();inputs={str(Path(__file__).resolve()):digest(__file__)}
    if stage:
        path=Path(stage)/'province_population_draft.csv';inputs[str(path.resolve())]=digest(path)
        for r in rows(path):
            n=int(r['centipersons']);p=r['target_province'];s=r['target_state']
            population[world.owners[s][p]]+=n
            if r['source_owner'] in world.tags:votes[p][world.tags[r['source_owner']]]+=n
    report=plan(world.owners,world.repairs,world.countries,province_land_edges(world,Path(__file__).resolve().parents[1]/'.local/m3/cache/tribal_land_edges.json'),votes,population)
    report['input_sha256']=inputs
    apply(world,report);world.terrain_finalization=report
    return report
