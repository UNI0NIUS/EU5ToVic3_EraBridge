"""Local source development correction, independent of British output per capita."""
from collections import Counter, defaultdict
import math

from economy_model import apportioned, industry_mapping
from pdx_text import root


def unit(value):
    return min(1.0,max(0.0,value))


def same_economic_world(before,after):
    """Population-mode metadata alone must not reopen an approved growth plan."""
    prefixes=('map_data/state_regions/','common/history/buildings/','common/history/countries/')
    subset=lambda values:{k:v for k,v in values.items() if k.startswith(prefixes)}
    return subset(before)==subset(after)


def bounded_import_need(reference,after,baseline_inputs,prices,extra_output_value,policy):
    increases={g:max(0,max(0,-after.get(g,0))-max(0,-reference.get(g,0))) for g in set(after)|set(reference)}
    if any(n>baseline_inputs.get(g,0)*policy['maximum_extra_input_import_fraction']+1e-6 for g,n in increases.items()):
        return False
    cost=sum(n*prices[g] for g,n in increases.items())
    return cost<=extra_output_value*policy['maximum_extra_import_to_output_value']+1e-6


def industrial_uplift(development,urban_share,modern_share,source_industry_share,technologies,policy):
    development=unit((development-policy['development_floor'])/(policy['development_full']-policy['development_floor']))
    urban=unit(urban_share/policy['urban_full_share'])
    density=unit(source_industry_share/policy['source_industrial_population_reference'])
    tech=sum(t in technologies for t in policy['technology_markers'])/len(policy['technology_markers'])
    return min(policy['maximum_extra_fraction'],density*(development*policy['development_weight']+
        urban*policy['urban_weight']+unit(modern_share)*policy['modern_factory_weight']+tech*policy['production_technology_weight']))


def source_evidence(source,stage,eu5,mapping_policy,industry_policy):
    links=defaultdict(Counter)
    for r in stage:links[r['source_location']][r['target_state'],r['target_owner']]+=int(r['centipersons'])
    links={k:{p:n/sum(v.values()) for p,n in v.items()} for k,v in links.items() if sum(v.values())}
    mapping,stages=industry_mapping(eu5,mapping_policy)
    constants={k.replace('_employment','').replace('mills','mill'):float(v)*1000
        for k,v in root((eu5/'main_menu/common/script_values/default_values.txt').read_text(encoding='utf-8-sig')).entries()
        if k in ('guild_employment','workshop_employment','manufactory_employment','mills_employment')}
    local=defaultdict(Counter);weights=Counter()
    for loc in source['locations'].values():
        for pair,f in links.get(loc['name'],{}).items():
            n=loc['population']*f;local[pair]['population']+=n;local[pair]['development_weighted']+=n*loc['development']
            if loc['rank']!='rural_settlement':local[pair]['urban_population']+=n
    for b in source['buildings']:
        kind=mapping.get(b['type'])
        if not kind:continue
        loc=source['locations'][b['location']];stage_name=stages[b['type']]
        occupied=float(b.get('employed',0))*1000
        capacity=float(b.get('level',0))*constants[stage_name]
        score=industry_policy['source_employment_weight']*occupied+industry_policy['source_installed_capacity_weight']*capacity
        for (s,t),f in links.get(loc['name'],{}).items():
            local[s,t]['industry_person_equivalents']+=occupied*f
            local[s,t]['industry_score']+=score*f
            if stage_name in ('manufactory','mill'):local[s,t]['modern_score']+=score*f
            weights[s,t,kind]+=score*f
    profiles={}
    for pair,v in local.items():
        n=max(1,v['population']);score=max(1,v['industry_score'])
        profiles[pair]={'population':v['population'],'development':v['development_weighted']/n,
            'urban_share':v['urban_population']/n,'modern_share':v['modern_score']/score,
            'source_industry_share':v['industry_person_equivalents']/n}
    return profiles,weights,links


def factory_targets(baseline_rows,profiles,weights,techs,policy,manufacturing):
    """Use an immutable baseline, so package rebuilding never stacks the uplift."""
    stock=Counter({(r['state'],r['owner'],r['building']):r['levels'] for r in baseline_rows if r['building'] in manufacturing and not r.get('guards')})
    groups=defaultdict(dict);audit=[]
    for key,n in sorted(stock.items()):
        s,t,k=key;p=profiles.get((s,t))
        if not p or not weights.get(key):continue
        boost=industrial_uplift(p['development'],p['urban_share'],p['modern_share'],p['source_industry_share'],techs[t],policy)
        groups[t,k][s]=n*boost
        audit.append({'state':s,'country':t,'building':k,'baseline_levels':n,'extra_fraction':boost,**p})
    additions={(s,t,k):n for (t,k),v in groups.items() for s,n in apportioned(v).items() if n}
    return {key:n+additions.get(key,0) for key,n in stock.items()},audit
