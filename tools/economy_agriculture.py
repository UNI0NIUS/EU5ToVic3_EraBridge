"""Source-backed commercial agriculture with a finite subsistence land reserve.

The development allowance is a gameplay assumption, not a historical employment
statistic. Neither paid employment nor subsistence demand can create arable land.
"""
from collections import Counter
import math
from economy_model import apportioned
from economy_geography import local_limit
from extract_m3_politics import sequence


class AgriculturePlanner:
    def __init__(self, ledger, source, links, tags, policy):
        self.ledger, self.profiles = ledger, {}
        self.policy = policy
        if not 0 <= policy['maximum_peasant_commercialization_fraction'] <= 1:
            raise ValueError('Peasant commercialization fraction must be between zero and one')
        observed, development = Counter(), Counter()
        for loc in source['locations'].values():
            for pair, fraction in links.get(loc['name'], {}).items():
                n = loc['population']*fraction
                observed[pair] += n
                development[pair] += n*loc['development']
        for (state, tag), pop in sorted(ledger.population.items()):
            if tag not in tags:
                continue
            kinds = sequence(ledger.target.states[state].get('arable_resources'))
            kinds = [k for k in kinds if ledger.allowed(k, tag)]
            if not kinds:
                continue
            rural = sum(ledger.source_classes[state, tag, c] for c in ledger.config['rural_classes'])
            paid = ledger.source_paid_agriculture[state, tag]
            # Defensive bound: occupational evidence cannot exceed residents.
            scale = min(1, pop/max(1, rural+paid))
            rural, paid = rural*scale, paid*scale
            dev = development[state, tag]/max(1, observed[state, tag])
            fraction = min(1, max(0, dev/100))*policy['maximum_peasant_commercialization_fraction']
            workforce = ledger.config['workforce_share']
            commercial = (paid+rural*fraction)*workforce
            subsistence = rural*(1-fraction)*workforce
            sub = ledger.target.states[state]['subsistence_building']
            subjobs = ledger.target.coefficients(sub, ledger.pms(sub,tag), ledger.techs[tag])['jobs']
            farmjobs = min(ledger.target.coefficients(k,ledger.pms(k,tag),ledger.techs[tag])['jobs'] for k in kinds)
            land = local_limit(ledger,state,tag,kinds[0])
            wanted_farm = commercial/max(1,farmjobs)
            wanted_sub = subsistence/max(1,subjobs)
            # In overcrowded states share scarce land between the two observed
            # livelihoods; do not evict all farms or create land for either group.
            if wanted_farm+wanted_sub > land:
                farm_cap = math.floor(land*wanted_farm/max(1e-9,wanted_farm+wanted_sub))
            else:
                farm_cap = max(0,land-math.ceil(wanted_sub))
            self.profiles[state,tag] = {
                'state':state,'country':tag,'population_weighted_development':round(dev,4),
                'source_rural_persons':rural,'source_paid_agriculture_person_equivalents':paid,
                'source_occupation_normalization':scale,
                'peasant_commercialization_fraction':fraction,
                'commercial_job_ceiling':math.floor(commercial),
                'source_subsistence_worker_target':math.ceil(subsistence),
                'arable_share':land,'commercial_land_ceiling':farm_cap,
                'reserved_subsistence_land':land-farm_cap}

    def room(self,state,tag,kind,pms=None):
        p = self.profiles.get((state,tag))
        if p is None or kind not in self.ledger.arable_kinds:
            return math.inf
        rows = [r for r in self.ledger.local(state,tag) if r['building'] in self.ledger.arable_kinds]
        jobs = sum(self.ledger.coefficients(r)['jobs']*r['levels'] for r in rows)
        per_level = self.ledger.target.coefficients(kind,pms or self.ledger.pms(kind,tag),self.ledger.techs[tag])['jobs']
        jobs += sum((per_level-self.ledger.coefficients(r)['jobs'])*r['levels']
                    for r in rows if r['building']==kind)
        return max(0,min(p['commercial_land_ceiling']-sum(r['levels'] for r in rows),
                         math.floor((p['commercial_job_ceiling']-jobs)/max(1,per_level))))

    def constrain_existing(self):
        changes = []
        for (state,tag),p in self.profiles.items():
            rows = [r for r in self.ledger.local(state,tag) if r['building'] in self.ledger.arable_kinds]
            levels = sum(r['levels'] for r in rows)
            jobs = sum(self.ledger.coefficients(r)['jobs']*r['levels'] for r in rows)
            scale = min(1,p['commercial_land_ceiling']/max(1,levels),p['commercial_job_ceiling']/max(1,jobs))
            allocated = apportioned({r['building']:r['levels'] for r in rows},math.floor(levels*scale))
            costs = {r['building']:self.ledger.coefficients(r)['jobs'] for r in rows}
            while sum(n*costs[k] for k,n in allocated.items()) > p['commercial_job_ceiling']:
                k = max((k for k,n in allocated.items() if n),key=lambda k:(costs[k],allocated[k],k))
                allocated[k] -= 1
            for r in rows:
                n = allocated[r['building']]
                if n == r['levels']:
                    continue
                changes.append({'state':state,'country':tag,'building':r['building'],'before':r['levels'],'after':n})
                self.ledger.put(state,tag,r['building'],n,'source_agriculture_and_subsistence_reserve',r['pms'])
        return changes

    def audit(self):
        rows = []
        for pair,p in self.profiles.items():
            farms = [r for r in self.ledger.local(*pair) if r['building'] in self.ledger.arable_kinds]
            jobs = sum(self.ledger.coefficients(r)['jobs']*r['levels'] for r in farms)
            levels = sum(r['levels'] for r in farms)
            rows.append({**p,'commercial_levels':levels,'commercial_jobs':jobs,
                         'remaining_subsistence_land':p['arable_share']-levels,
                         'commercial_job_excess':max(0,jobs-p['commercial_job_ceiling']),
                         'commercial_land_excess':max(0,levels-p['commercial_land_ceiling'])})
        return {'policy':self.policy,'states':rows}
