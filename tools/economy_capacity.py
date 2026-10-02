"""Employment and land envelopes for the population conversion (not a hiring simulator)."""
from collections import Counter, defaultdict
import math
import re
from economy_model import apportioned, block
from extract_m3_politics import fields, sequence
from pdx_text import Object, root
from economy_geography import preserve_geography, local_limit


def capped_allocation(weights, total, caps):
    """Largest remainders with redistribution; never exceed a state/law cap."""
    result = Counter()
    remaining = total
    while remaining:
        eligible = {k: weights.get(k, 0) for k in sorted(caps) if result[k] < caps[k]}
        if not eligible:
            break
        if not sum(eligible.values()):
            eligible = {k: caps[k]-result[k] for k in eligible}
        proposal = apportioned(eligible, remaining)
        moved = 0
        for k, n in proposal.items():
            n = min(n, caps[k]-result[k])
            result[k] += n
            moved += n
        if not moved:
            raise ValueError('Allocation made no progress')
        remaining -= moved
    return dict(result), remaining


class Ledger:
    def __init__(self, target, rows, population, techs, laws, owners, british_pms, config):
        self.target, self.population, self.techs, self.laws = target, population, techs, laws
        self.owners, self.british_pms, self.config = owners, british_pms, config
        self.rows = {(r['state'], r['owner'], target.aliases.get(r['building'], r['building'])): dict(r) for r in rows}
        self.by_state, self.by_country = defaultdict(set), defaultdict(set)
        for key in self.rows:
            self.by_state[key[:2]].add(key); self.by_country[key[1]].add(key)
        self.coefficient_cache, self.pm_cache = {}, {}
        self.arable_kinds = {b for f in target.states.values() for b in sequence(f.get('arable_resources'))}
        self.changes, self.warnings = [], []
        self.military_demand = defaultdict(Counter)
        self.source_classes = Counter()
        self.source_paid_agriculture = Counter()

    def local(self, state, tag):
        return [self.rows[k] for k in sorted(self.by_state[state,tag]) if k in self.rows and self.rows[k]['levels'] > 0]

    def coefficients(self, row):
        key = row['building'],tuple(row['pms']),frozenset(self.techs[row['owner']])
        if key not in self.coefficient_cache:
            self.coefficient_cache[key] = self.target.coefficients(row['building'], row['pms'], self.techs[row['owner']])
        c = self.coefficient_cache[key]
        if row['building'] == 'building_barrack':
            c = {**c, 'jobs': 1000}
        return c

    def jobs(self, state, tag):
        return sum(self.coefficients(r)['jobs']*r['levels'] for r in self.local(state,tag))+getattr(self,'ownership_jobs',{}).get((state,tag),0)

    def allowed(self, kind, tag):
        return set(sequence(self.target.buildings[kind].get('unlocking_technologies'))) <= self.techs[tag]

    def pms(self, kind, tag):
        key = kind,tag,frozenset(self.techs[tag]),frozenset(self.laws[tag])
        if key in self.pm_cache: return self.pm_cache[key]
        pms = self.target.select(kind, self.techs[tag], self.british_pms[kind], self.laws[tag])
        if kind == 'building_port' and self.target.available('pm_basic_port', self.techs[tag], self.laws[tag]):
            pms = ['pm_basic_port']  # Anchorage supplies neither ships nor useful infrastructure.
        self.pm_cache[key] = pms
        return pms

    def put(self, state, tag, kind, n, reason, pms=None):
        n = int(n)
        key = state,tag,kind
        old = self.rows.get(key)
        before = old['levels'] if old else 0
        if n <= 0:
            self.rows.pop(key, None)
            if before:
                self.changes.append({'state':state,'country':tag,'building':kind,'before':before,'after':0,'reason':reason})
            return
        if not self.allowed(kind,tag):
            self.warnings.append({'state':state,'country':tag,'building':kind,'reason':'technology_locked','wanted':n})
            return
        methods = pms or (old['pms'] if old else self.pms(kind,tag))
        if n == before and old and methods == old['pms']:
            return
        r = {'state':state,'owner':tag,'building':kind,'levels':n,'pms':methods}
        if old and 'guards' in old:
            r['guards'] = old['guards']
        # Government/military buildings use levels, not fabricated private ownership.
        if kind in ('building_barrack','building_naval_administration','building_government_administration','building_university','building_construction_sector','building_railway'):
            r['body'] = f'building = {kind}\nlevel = {n}\nreserves = 1\nactivate_production_methods = {{ '+ ' '.join(methods)+' }\n'
        self.rows[key] = r
        self.by_state[key[:2]].add(key); self.by_country[tag].add(key)
        self.changes.append({'state':state,'country':tag,'building':kind,'before':before,'after':n,'reason':reason})

    def add(self, state, tag, kind, n, reason, pms=None):
        old = self.rows.get((state,tag,kind),{}).get('levels',0)
        self.put(state,tag,kind,old+n,reason,pms)
        return self.rows.get((state,tag,kind),{}).get('levels',0)-old

    def balance(self, tag):
        balance = Counter()
        for key in sorted(self.by_country[tag]):
            if key not in self.rows: continue
            r = self.rows[key]
            c = self.coefficients(r)
            for g,v in c['outputs'].items(): balance[g] += v*r['levels']
            for g,v in c['inputs'].items(): balance[g] -= v*r['levels']
        for g,v in self.military_demand[tag].items(): balance[g] -= v
        return balance

    def capped_room(self, state, tag, kind, pms=None):
        pms = pms or self.pms(kind,tag)
        jobs = self.target.coefficients(kind,pms,self.techs[tag])['jobs']
        # Adding levels replaces the methods of ALL existing levels of this type.
        # Workforce automation may have changed those methods since the caller
        # selected its expansion methods, so price that replacement as well.
        old = self.rows.get((state,tag,kind))
        replacement = (jobs-self.coefficients(old)['jobs'])*old['levels'] if old else 0
        budget = max(0,self.population[state,tag]*self.config['maximum_formal_workforce_share']-self.jobs(state,tag)-replacement)
        room = math.floor(budget/jobs) if jobs > 0 else 0
        if hasattr(self,'development'):
            room = min(room,self.development.room(state,tag,kind,pms))
        if preserve_geography(self):
            cap = local_limit(self,state,tag,kind)
            used = sum(r['levels'] for r in self.local(state,tag) if r['building'] in self.arable_kinds) if kind in self.arable_kinds else self.rows.get((state,tag,kind),{}).get('levels',0)
            if cap is not None:
                room = min(room,max(0,cap-used))
        if kind in self.arable_kinds:
            if hasattr(self,'agriculture'):
                room = min(room,self.agriculture.room(state,tag,kind,pms))
            rural_workers = (sum(self.source_classes[state,tag,c] for c in self.config['rural_classes'])+self.source_paid_agriculture[state,tag])*self.config['workforce_share']
            agricultural_jobs = sum(self.coefficients(r)['jobs']*r['levels'] for r in self.local(state,tag) if r['building'] in self.arable_kinds)
            rural_room = max(0,rural_workers*self.config['commercial_rural_workforce_limit']-agricultural_jobs-replacement)
            room = min(room,math.floor(rural_room/jobs) if jobs else 0)
        capped = fields(self.target.states[state].get('capped_resources'))
        if kind in capped:
            shares = apportioned(Counter(self.owners[state].values()),int(capped[kind]))
            room = min(room,max(0,shares.get(tag,0)-self.rows.get((state,tag,kind),{}).get('levels',0)))
        return room


def rural_kinds(target, state):
    return set(sequence(target.states[state].get('arable_resources')))


def carry_land(ledger, classes, managed_tags):
    """Measure rural/fallback demand without fabricating land to guarantee employment."""
    target = ledger.target
    needed, audit = {}, []
    for (state,tag), pop in sorted(ledger.population.items()):
        if tag not in managed_tags:
            continue
        rows = ledger.local(state,tag)
        farms = rural_kinds(target,state)
        farm_levels = sum(r['levels'] for r in rows if r['building'] in farms)
        farm_jobs = sum(ledger.coefficients(r)['jobs']*r['levels'] for r in rows if r['building'] in farms)
        formal = ledger.jobs(state,tag)
        subsistence = target.states[state].get('subsistence_building')
        if not subsistence:
            if pop > 0:
                raise ValueError('Populated state without subsistence definition: '+state)
            continue
        pms = ledger.pms(subsistence,tag)
        subjobs = target.coefficients(subsistence,pms,ledger.techs[tag])['jobs']
        rural_persons = sum(classes[state,tag,c] for c in ledger.config['rural_classes'])
        workforce = pop*ledger.config['workforce_share']
        source_rural_workers = (rural_persons+ledger.source_paid_agriculture[state,tag])*ledger.config['workforce_share']
        rural_floor = max(0,source_rural_workers-farm_jobs)
        isolated = (state,tag) in getattr(ledger,'isolated_states',set())
        staffing_credit = 0 if isolated else ledger.config['formal_staffing_safety_fraction']
        fallback = max(0,workforce-formal*staffing_credit)
        subsistence_levels = math.ceil(max(rural_floor,fallback)/subjobs)
        required = farm_levels+subsistence_levels
        needed[state,tag] = required
        audit.append({'state':state,'country':tag,'population':pop,'source_rural_persons':round(rural_persons),
                      'source_paid_agriculture_person_equivalents':round(ledger.source_paid_agriculture[state,tag]),
                      'source_rural_workforce':round(source_rural_workers),'estimated_workforce':round(workforce),
                      'formal_job_capacity':formal,'commercial_agricultural_jobs':farm_jobs,
                      'commercial_arable_levels':farm_levels,'subsistence_jobs_per_level':subjobs,
                      'source_rural_subsistence_levels':math.ceil(rural_floor/subjobs),
                      'required_arable_share':required,
                      'isolated_market_full_workforce_fallback':isolated,
                      'formal_staffing_credit':staffing_credit,
                      'fallback_beyond_source_rural_jobs':round(max(0,fallback-rural_floor)),
                      'subsistence_methods':pms})
    new_land = {}
    for state, owners in sorted(ledger.owners.items()):
        shares = Counter(owners.values())
        old = int(target.states[state].get('arable_land',0))
        required = {t:needed.get((state,t),0) for t in shares}
        total = old if preserve_geography(ledger) else max([old]+[math.ceil(n*sum(shares.values())/shares[t]) for t,n in required.items() if n])
        # Rounding can steal a share from a small split-state owner.
        while not preserve_geography(ledger) and any(apportioned(shares,total).get(t,0) < n for t,n in required.items()):
            total += 1
        if total != old:
            new_land[state] = total
    for r in audit:
        s,t = r['state'],r['country']
        old = int(target.states[s].get('arable_land',0)); total = new_land.get(s,old)
        shares = Counter(ledger.owners[s].values())
        allocation = apportioned(shares,total)[t]
        old_allocation = apportioned(shares,old)[t]
        r.update(old_arable_share=old_allocation,new_arable_share=allocation,
                 old_subsistence_job_capacity=max(0,old_allocation-r['commercial_arable_levels'])*r['subsistence_jobs_per_level'],
                 new_subsistence_job_capacity=max(0,allocation-r['commercial_arable_levels'])*r['subsistence_jobs_per_level'])
        r['capacity_gap_full_staffing'] = max(0,r['estimated_workforce']-r['formal_job_capacity']-r['new_subsistence_job_capacity'])
        r['unmet_arable_demand'] = max(0,r['required_arable_share']-allocation)
        r['capacity_gap_safety_staffing'] = max(0,math.ceil(r['population']*ledger.config['workforce_share']-r['formal_job_capacity']*r['formal_staffing_credit']-r['new_subsistence_job_capacity']))
        r['geography_policy'] = ledger.config.get('geography_policy','vanilla_capacity')
        if hasattr(ledger,'agriculture') and (s,t) in ledger.agriculture.profiles:
            r['commercial_agriculture_policy'] = ledger.agriculture.profiles[s,t]
        if r['capacity_gap_full_staffing'] and not preserve_geography(ledger):
            raise ValueError('Unresolved employment capacity: '+s+' '+t)
    return new_land,audit


def write_land(target, base_mod, output, new_land, new_resources=None):
    new_resources = new_resources or {}
    files = []
    for path in sorted((target.game/'map_data/state_regions').glob('*.txt')):
        rel = path.relative_to(target.game)
        existing = base_mod/rel
        source = (existing if existing.exists() else path).read_text(encoding='utf-8-sig')
        replacements = []
        for state,obj in root(source).entries():
            if state not in new_land and state not in new_resources:
                continue
            if state in new_land:
                matches = list(re.finditer(r'(?m)^(\s*arable_land\s*=\s*)\d+',obj.text()))
                if len(matches) != 1:
                    raise ValueError('Expected one arable land definition: '+state)
                m = matches[0]
                replacements.append((obj.start+m.start(),obj.start+m.end(),m[1]+str(new_land[state])))
            if state in new_resources:
                caps = fields(obj).get('capped_resources')
                content = ''.join(f'\n        {k} = {v}' for k,v in fields(target.states[state].get('capped_resources')).items())+'\n    '
                if caps:
                    replacements.append((caps.start,caps.end,content))
                else:
                    replacements.append((obj.end,obj.end,'\n    capped_resources = {'+content+'}\n'))
        if replacements:
            for a,b,value in sorted(replacements,reverse=True):
                source = source[:a]+value+source[b:]
            dest = output/rel
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(source,encoding='utf-8-sig')
            files.append(rel.as_posix())
    return files
