"""One-time proportional population normalization, preserving identities and caps."""
from collections import Counter, defaultdict
import math

from economy_model import apportioned


def majority_signature(groups, whole_state=False):
    totals=Counter();cultures=Counter();religions=Counter()
    for (s,t,c,r),n in groups.items():
        scope=s if whole_state else (s,t)
        totals[scope]+=n;cultures[scope,c]+=n;religions[scope,r]+=n
    return {('culture',scope,c) for (scope,c),n in cultures.items() if 2*n>totals[scope]}|{
        ('religion',scope,r) for (scope,r),n in religions.items() if 2*n>totals[scope]}


def calibrate(groups, eligible, employment, owner_jobs, elite_retention, policy):
    if not 0<policy['workforce_share']<=1:raise ValueError('Invalid workforce ratio')
    if not 0<=policy['maximum_country_reduction_fraction']<=policy['maximum_state_country_reduction_fraction']<1:
        raise ValueError('Invalid population reduction limits')
    if policy['workforce_reserve_fraction']<0:raise ValueError('Negative workforce reserve')
    if not eligible<=groups.keys():raise ValueError('Source identities missing from installed population')
    bypart=defaultdict(dict);national=Counter();rows={};cuts={}
    for k,n in groups.items():bypart[k[:2]][k]=n;national[k[1]]+=n
    pairs=[(r['state'],r['country']) for r in employment]
    if len(pairs)!=len(set(pairs)):raise ValueError('Duplicate employment state-country part')
    if policy.get('require_full_world_coverage') and set(pairs)!=set(bypart):
        raise ValueError('Incomplete worldwide employment coverage')
    for r in employment:
        pair=r['state'],r['country'];local=bypart[pair];n=sum(local.values())
        if n!=r['population']:raise ValueError('Employment/population mismatch: '+str(pair))
        source=sum(v for k,v in local.items() if k in eligible)
        owner=owner_jobs.get(pair,0)
        if owner>r['formal_job_capacity']:raise ValueError('Owner jobs exceed formal jobs')
        capacity=(r['formal_job_capacity']-owner)*policy['productive_staffing_fraction']+owner*policy['owner_staffing_fraction']+r['new_subsistence_job_capacity']
        required=math.ceil(capacity*(1+policy['workforce_reserve_fraction'])/policy['workforce_share'])
        floor=max(required,n-source+math.ceil(source*min(1,elite_retention.get(pair,0))))
        cut=min(math.floor(source*policy['maximum_state_country_reduction_fraction']),max(0,n-floor))
        cuts[pair]=cut
        rows[pair]={'state':pair[0],'country':pair[1],'population_before':n,'source_persons':source,
            'planning_worker_capacity':capacity,'population_target_with_reserve':required,
            'elite_pool_minimum_retention_fraction':elite_retention.get(pair,0),'requested_cut_before_country_cap':cut}
    for t,total in national.items():
        local={p:n for p,n in cuts.items() if p[1]==t};limit=math.floor(total*policy['maximum_country_reduction_fraction'])
        if sum(local.values())>limit:cuts.update(apportioned(local,limit))
    output=dict(groups)
    for pair,cut in cuts.items():
        source=rows[pair]['source_persons']
        rows[pair]['cut_budget_after_country_cap']=cut
        rows[pair]['source_retention_fraction_requested']=(source-cut)/source if source else 1
        if not source:continue
        # Exact integer arithmetic and upward rounding: no group is over-cut,
        # erased, or silently converted to another culture/religion.
        for k,n in bypart[pair].items():
            if k in eligible:output[k]=max(policy['minimum_persons_per_existing_group'],(n*(source-cut)+source-1)//source)
    frozen=set()
    for whole in (False,True):
        before=majority_signature(groups,whole);after=majority_signature(output,whole)
        scopes={v[1] for v in before^after}
        for k,n in groups.items():
            scope=k[0] if whole else k[:2]
            if scope in scopes:output[k]=n;frozen.add(k[:2])
    assert majority_signature(groups)==majority_signature(output)
    assert majority_signature(groups,True)==majority_signature(output,True)
    for pair,row in rows.items():
        n=sum(output[k] for k in bypart[pair]);row['population_after']=n
        row['removed_persons']=row['population_before']-n
        row['majority_guard_preserved_original']=pair in frozen
        row['reduction_fraction']=row['removed_persons']/max(1,row['population_before'])
        assert row['removed_persons']<=math.floor(row['source_persons']*policy['maximum_state_country_reduction_fraction'])
        row['estimated_workforce_after']=n*policy['workforce_share']
        row['remaining_worker_gap_at_planning_staffing']=max(0,row['estimated_workforce_after']-row['planning_worker_capacity'])
        if row['removed_persons']:
            assert row['estimated_workforce_after']+1e-6>=row['planning_worker_capacity']*(1+policy['workforce_reserve_fraction'])
    for k,n in output.items():
        assert 0<n<=groups[k]
        if k not in eligible:assert n==groups[k]
    actual_national=Counter()
    for k,n in output.items():actual_national[k[1]]+=n
    for t,n in national.items():assert n-actual_national[t]<=math.floor(n*policy['maximum_country_reduction_fraction'])
    return output,list(rows.values())
