"""Source-relative economic development envelopes, not universal self-sufficiency."""
from collections import Counter, defaultdict
import math
from economy_model import apportioned
from extract_m3_politics import fields


def manufacturing_kinds(target):
    result = set()
    for kind, f in target.buildings.items():
        group = f['building_group']
        while group:
            if group == 'bg_manufacturing':
                result.add(kind); break
            group = target.building_groups[group].get('parent_group')
    return result


def development_parameters(intensity, urban_share, paid_share, source_manufacturing, seed_jobs, population, workforce_share, policy):
    """Continuous rules; labels below are descriptive and do not impose country bonuses."""
    intensity = max(0, intensity)
    industrial = min(1, intensity)
    commercial = min(1, max(0, urban_share)+max(0, paid_share))
    expansion = policy['manufacturing_expansion_base']+policy['manufacturing_expansion_industrial']*industrial
    artisan = population*workforce_share*min(policy['artisan_workforce_ceiling'], urban_share*policy['urban_artisan_workforce_fraction'])
    ceiling = max(seed_jobs*expansion, source_manufacturing*workforce_share*policy['observed_manufacturing_tolerance'], artisan)
    return {'industrial_factor': industrial, 'commercial_factor': commercial,
            'manufacturing_job_ceiling': math.floor(ceiling),
            'commercial_food_reference_factor': min(1, policy['food_reference_floor']+policy['food_commercial_weight']*commercial+policy['food_industrial_weight']*industrial),
            'trade_reference_factor': min(1, policy['trade_reference_floor']+policy['trade_commercial_weight']*commercial+policy['trade_industrial_weight']*industrial),
            'heavy_industry_expansion_allowed': intensity >= policy['new_heavy_industry_intensity_min']}


class DevelopmentPlanner:
    def __init__(self, ledger, source, links, structure, seed_economy, political, policy):
        self.ledger, self.policy = ledger, policy
        self.manufacturing = manufacturing_kinds(ledger.target)
        self.profiles, self.denied = {}, Counter()
        observed = defaultdict(Counter)
        self.state_urban = Counter()
        for loc in source['locations'].values():
            for (state, tag), weight in links.get(loc['name'], {}).items():
                pop = loc['population']*weight
                observed[tag]['population'] += pop
                observed[tag]['development_weighted'] += pop*loc['development']
                if loc['rank'] != 'rural_settlement':
                    observed[tag]['urban_population'] += pop
                    self.state_urban[state,tag] += pop
        for tag, country in sorted(political['countries'].items()):
            pop = sum(p for (s,t),p in ledger.population.items() if t == tag)
            if not pop: continue
            rows = [ledger.rows[k] for k in sorted(ledger.by_country[tag]) if k in ledger.rows]
            jobs = sum(ledger.coefficients(r)['jobs']*r['levels'] for r in rows if r['building'] in self.manufacturing)
            levels = Counter()
            for r in rows:
                if r['building'] in self.manufacturing: levels[r['building']] += r['levels']
            evidence = structure['countries'].get(tag, {})
            raw = observed[tag]
            urban = min(1, raw['urban_population']/max(1, raw['population']))
            paid = sum(ledger.source_paid_agriculture[s,t] for s,t in ledger.population if t == tag)/pop
            intensity = seed_economy.get(tag, {}).get('relative_industrial_intensity', 0)
            params = development_parameters(intensity, urban, paid, evidence.get('manufacturing', 0), jobs, pop, ledger.config['workforce_share'], policy)
            label = 'agrarian_craft' if intensity < .1 else 'commercial_craft' if intensity < .35 else 'manufacturing' if intensity < .7 else 'industrial_frontier'
            if not {'atmospheric_engine','mechanical_tools'} & ledger.techs[tag] and label == 'industrial_frontier': label = 'advanced_hand_manufacturing'
            self.profiles[tag] = {'country': tag, 'name': country.get('name_simp_chinese', tag),
                'scope': 'source_economy' if country['source_id'] is not None else 'vanilla_fallback_preserved',
                'country_type': country['country_type'], 'population': pop,
                'source_linked_population': raw['population'], 'source_urban_population_share': urban,
                'source_population_weighted_development': raw['development_weighted']/max(1,raw['population']),
                'source_paid_agriculture_share': paid, 'source_employment': evidence,
                'source_relative_industrial_intensity': intensity, 'development_description': label,
                'production_technologies': sorted(t for t in ledger.techs[tag] if ledger.target.techs[t]['category'] == 'production'),
                'seed_manufacturing_jobs': jobs, 'seed_manufacturing_levels': dict(levels), **params}

    def jobs(self, tag):
        return sum(self.ledger.coefficients(self.ledger.rows[k])['jobs']*self.ledger.rows[k]['levels']
                   for k in self.ledger.by_country[tag] if k in self.ledger.rows and k[2] in self.manufacturing)

    def room(self, state, tag, kind, pms=None):
        if kind not in self.manufacturing or tag not in self.profiles: return math.inf
        p = self.profiles[tag]
        if p['scope'] != 'source_economy': return math.inf
        if kind in self.policy['heavy_industry_kinds'] and not p['heavy_industry_expansion_allowed'] and not p['seed_manufacturing_levels'].get(kind):
            self.denied[tag, kind, 'no_source_heavy_industry_base'] += 1
            return 0
        jobs = self.ledger.target.coefficients(kind, pms or self.ledger.pms(kind,tag), self.ledger.techs[tag])['jobs']
        old = self.ledger.rows.get((state,tag,kind))
        replacement = (jobs-self.ledger.coefficients(old)['jobs'])*old['levels'] if old else 0
        room = math.floor(max(0,p['manufacturing_job_ceiling']-self.jobs(tag)-replacement)/jobs) if jobs else 0
        if not room: self.denied[tag,kind,'source_development_envelope'] += 1
        return room

    def normalize_overloaded_states(self, tags):
        """Remove impossible inherited civilian establishments before adding new capacity.

        Military establishments and essential administration are protected. A country
        whose army alone exceeds its labor pool is reported, never silently disarmed.
        """
        ledger = self.ledger
        protected = {'building_barrack', 'building_government_administration', 'building_naval_fortification',
                     'building_naval_administration', 'building_naval_logistics_center', 'building_army_logistics_center'}
        changes = []
        for (state, tag), pop in sorted(ledger.population.items()):
            if tag not in tags: continue
            budget = pop*ledger.config['maximum_formal_workforce_share']
            excess = max(0, ledger.jobs(state,tag)-budget)
            if excess <= 0: continue
            # Spare discretionary government capacity first, then commodity capacity.
            rows = sorted(ledger.local(state,tag), key=lambda r:(r['building'] not in ('building_construction_sector','building_university','building_trade_center'), -ledger.coefficients(r)['jobs']*r['levels'], r['building']))
            for r in rows:
                if excess <= 0: break
                if r['building'] in protected or r.get('guards'): continue
                jobs = ledger.coefficients(r)['jobs']
                if jobs <= 0: continue
                remove = min(r['levels'], math.ceil(excess/jobs))
                ledger.put(state,tag,r['building'],r['levels']-remove,'inherited_civilian_capacity_exceeds_local_workforce',r['pms'])
                excess -= remove*jobs
                changes.append({'state':state,'country':tag,'building':r['building'],'removed_levels':remove})
        return changes

    def audit(self):
        result = {}
        for tag, p in self.profiles.items():
            result[tag] = {**p, 'final_manufacturing_jobs': self.jobs(tag),
                           'manufacturing_envelope_excess': max(0,self.jobs(tag)-p['manufacturing_job_ceiling'])}
        return {'countries': result,
                'blocked_expansions': [{'country':t,'building':k,'reason':reason,'attempts':n}
                                       for (t,k,reason),n in sorted(self.denied.items())],
                'policy': self.policy,
                'limitations': ['Capacity and job envelopes are explicit conversion assumptions, not GDP or actual employment.',
                                'Missing goods remain visible as import/development needs; no imports or treaties are invented.',
                                'Source territory/population links determine economic identity, not the borrowed vanilla country tag.',
                                'The four vanilla fallback countries retain original initialization.']}
