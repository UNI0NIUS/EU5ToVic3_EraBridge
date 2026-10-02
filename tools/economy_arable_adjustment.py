"""Bounded arable correction from mapped geography, source development and history."""
from collections import Counter, defaultdict
import math

from economy_model import apportioned
from extract_m3_politics import fields
from pdx_text import root


def location_fraction(geo, source, irrigated, policy):
    topography=geo.get('topography');climate=geo.get('climate');vegetation=geo.get('vegetation')
    if topography not in policy['topography_ceiling'] or climate=='arctic': return 0.0
    development=min(1,max(0,source['development']/100))
    development=policy['minimum_development_factor']+(1-policy['minimum_development_factor'])*development
    cropped=source.get('raw_material') in policy['crop_goods'] or source.get('observed_crop_building',False)
    if vegetation=='desert' and not (irrigated and cropped):return 0.0
    evidence=1 if cropped else .85 if irrigated else .4
    water=policy['climate_factor'].get(climate,0)
    if irrigated and climate in ('arid','cold_arid'):water=max(water,.3)
    fraction=policy['topography_ceiling'][topography]*water*policy['vegetation_factor'].get(vegetation,0)*development*evidence
    recovery=policy.get('cultivated_land_recovery')
    if recovery and vegetation!='desert':
        progress=min(1,max(0,(source['development']-recovery['development_floor'])/(recovery['development_full']-recovery['development_floor'])))
        observed=1 if cropped else recovery['irrigation_only_evidence'] if irrigated else 0
        cultivated=recovery['maximum_fraction']*progress*observed*recovery['climate_factor'].get(climate,0)*recovery['topography_factor'].get(topography,0)
        fraction=max(fraction,cultivated)
    return min(policy['maximum_increase_fraction'],fraction)


def profiles(source, stage_rows, geography_path, policy):
    geography={k:fields(v) for k,v in root(geography_path.read_text(encoding='utf-8-sig')).entries()}
    locations={v['name']:v for v in source['locations'].values()}
    irrigated={source['locations'][str(b['location'])]['name'] for b in source['buildings']
        if b['type']=='irrigation_systems' and float(b.get('level',0))>0 and float(b.get('employed',0))>0}
    recovery=policy.get('cultivated_land_recovery',{})
    suffixes=tuple(recovery.get('cultivation_building_suffixes',[]))
    cultivated={source['locations'][str(b['location'])]['name'] for b in source['buildings']
        if (b['type'].endswith(suffixes) or b['type'] in recovery.get('cultivation_building_types',[]))
        and float(b.get('level',0))>0 and float(b.get('employed',0))>0}
    links=defaultdict(set)
    for r in stage_rows: links[r['target_state'],r['target_province']].add(r['source_location'])
    result=defaultdict(list)
    for (s,p),names in sorted(links.items()):
        if not names<=geography.keys():raise ValueError('Missing source terrain: '+str(names-geography.keys()))
        fractions=[location_fraction(geography[n],dict(locations[n],observed_crop_building=n in cultivated),n in irrigated,policy) for n in sorted(names)]
        result[s].append({'province':p,'source_locations':sorted(names),'geographic_fraction':sum(fractions)/len(fractions),
            'development':sum(min(100,max(0,locations[n]['development'])) for n in names)/len(names),
            'crop_evidence_fraction':sum(locations[n].get('raw_material') in policy['crop_goods'] or n in cultivated for n in names)/len(names),
            'irrigation_fraction':sum(n in irrigated for n in names)/len(names)})
    output={}
    for s,ps in sorted(result.items()):
        base=sum(p['geographic_fraction'] for p in ps)/len(ps)
        dev=sum(p['development'] for p in ps)/len(ps)
        history=policy['historical_overrides'].get(s)
        if history:
            # Historical evidence substitutes a bounded local interpretation of
            # terrain, not additional population-driven demand or modern works.
            base=max(base,history['maximum_fraction']*(.25+.75*dev/100))
        fraction=min(base,policy['restricted_state_ceiling'].get(s,policy['maximum_increase_fraction']))
        output[s]={'state':s,'maximum_fraction':fraction,'province_mean_development':dev,
            'geographic_fraction':sum(p['geographic_fraction'] for p in ps)/len(ps),
            'historical_override':history,'mapped_provinces':len(ps),'province_evidence':ps}
    return output


def choose_land(original, maximum_fraction, owners, demands):
    """Smallest bounded increase achieving the maximum locally usable benefit.

    demands[tag] = (unfilled worker demand, jobs per subsistence level).
    No national pooling: an idle hectare in another state cannot employ a pop.
    """
    if original<0 or not 0<=maximum_fraction<=1:raise ValueError('Invalid geographic envelope')
    if not owners: return original,{}
    base=apportioned(owners,original)
    best_land=original;best_benefit=0;best={}
    ceiling=original+math.floor(original*maximum_fraction+1e-9)
    for n in range(original+1,ceiling+1):
        allocation=apportioned(owners,n)
        # Largest-remainder apportionment can otherwise steal a split-state
        # owner's original hectare when total land rises (Alabama paradox).
        if any(allocation.get(t,0)<v for t,v in base.items()):continue
        benefits={t:min(max(0,gap),max(0,allocation.get(t,0)-base.get(t,0))*jobs) for t,(gap,jobs) in demands.items()}
        benefit=sum(benefits.values())
        if benefit>best_benefit:
            best_land,best_benefit,best=n,benefit,benefits
    return best_land,best


def plan(target, owners, employment, evidence):
    parts=defaultdict(dict)
    for r in employment:parts[r['state']][r['country']]=r
    rows=[];changes={}
    for s,p in evidence.items():
        original=int(target.states[s].get('arable_land',0))
        demands={t:(r['capacity_gap_safety_staffing'],r['subsistence_jobs_per_level']) for t,r in parts[s].items()}
        new,benefit=choose_land(original,p['maximum_fraction'],Counter(owners.get(s,{}).values()),demands)
        if new>original:changes[s]=new
        rows.append({k:v for k,v in p.items() if k!='province_evidence'}|{'original_arable':original,'new_arable':new,
            'extra_arable':new-original,'bounded_ceiling':original+math.floor(original*p['maximum_fraction']+1e-9),
            'planned_worker_gap_reduction_by_country':benefit})
    return changes,rows
