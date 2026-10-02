"""Province-evidence ownership of existing assets; never creates productive levels."""
from collections import Counter, defaultdict
import math
from economy_model import apportioned, block, building_rows
from economy_capacity import capped_allocation
from extract_m3_politics import fields
from pdx_text import Object, root

MANOR = 'building_manor_house'
FINANCE = 'building_financial_district'
OWNER_KIND = {'manor':MANOR,'finance':FINANCE}


def sector(target,kind):
    group = target.buildings[kind]['building_group']
    categories = {'bg_agriculture':'agriculture','bg_ranching':'agriculture','bg_plantations':'plantation',
                  'bg_mining':'resource','bg_logging':'resource','bg_fishing':'resource','bg_whaling':'resource',
                  'bg_manufacturing':'industry','bg_arts':'industry','bg_trade':'trade'}
    while group:
        if group in categories: return categories[group]
        group = target.building_groups[group].get('parent_group')
    return None


def vanilla_reference(target,policy):
    """Equal-country reference shares; no large-country or inherited-tag bonus."""
    country = defaultdict(Counter)
    for path in sorted((target.game/'common/history/buildings').glob('*.txt')):
        for row in building_rows(path):
            if row.get('guards'):continue
            kind = target.aliases.get(row['building'],row['building'])
            category = sector(target,kind)
            if category is None:continue
            for key,obj in root(row['body']).entries():
                if key in ('level','levels'):country[row['owner'],category]['government'] += int(obj)
                if key!='add_ownership':continue
                for key2,value in obj.entries():
                    f=fields(value);owner=f.get('type')
                    label = 'government' if key2=='country' else 'manor' if owner==MANOR else 'finance' if owner==FINANCE else 'self' if target.aliases.get(owner,owner)==kind else 'other'
                    country[row['owner'],category][label] += int(f.get('levels',0))
    profiles = {}
    for profile,tags in policy['vanilla_reference_profiles'].items():
        profiles[profile] = {}
        for category in policy['sectors']:
            samples=[]
            for tag in tags:
                c=country[tag,category];n=sum(c[k] for k in ('manor','finance','self'))
                if n:samples.append({k:c[k]/n for k in ('manor','finance','self')})
            if not samples:raise ValueError('Missing vanilla ownership reference '+profile+'/'+category)
            profiles[profile][category]={k:sum(c[k] for c in samples)/len(samples) for k in ('manor','finance','self')}
    return {'profiles':profiles,'countries':{t:{cat:dict(c) for (tag,cat),c in country.items() if tag==t} for t in sorted({t for tags in policy['vanilla_reference_profiles'].values() for t in tags})},
        'basis':'Installed vanilla 1836 building history, equal country weights within each profile; government/company assets excluded from the three-way private denominator; source provinces choose profiles continuously, never by target country tag.'}


def shares(noble_share,burgher_share,development,category,laws,policy,urban_share=0):
    """Explicit conversion weights; population shares are not shares of wealth."""
    n = max(0,noble_share)/policy['noble_reference_share']
    b = max(0,burgher_share)/policy['burgher_reference_share']
    progress = .5*min(1,max(0,development/100))+.5*min(1,max(0,urban_share))
    lower,upper,x = ('agrarian','mixed',progress*2) if progress<=.5 else ('mixed','industrial',(progress-.5)*2)
    refs = policy['calibrated_reference_shares']
    weights = {k:max(policy['reference_share_floor'],refs[lower][category][k]*(1-x)+refs[upper][category][k]*x) for k in ('manor','finance','self')}
    score = {'manor':n*weights['manor'],'finance':b*weights['finance'],'self':weights['self']}
    for law in sorted(laws):
        rule = policy.get('law_multipliers',{}).get(law,{})
        if rule.get('sectors') and category not in rule['sectors']: continue
        for key in score: score[key] *= rule.get(key,1)
    total = sum(score.values())
    return {k:v/total for k,v in score.items()}


def province_evidence(stage_rows,source):
    places = {v['name']:v for v in source['locations'].values()}
    result = {}
    for r in stage_rows:
        key = r['target_state'],r['target_owner'],r['target_province']
        p = result.setdefault(key,{'state':key[0],'country':key[1],'province':key[2],
            'population':0,'classes':Counter(),'development_weighted':0,'urban_population':0})
        n = int(r['centipersons'])/100
        loc = places[r['source_location']]
        p['population'] += n; p['classes'][r['source_class']] += n
        p['development_weighted'] += n*loc['development']
        if loc['rank']!='rural_settlement':p['urban_population'] += n
    for p in result.values():
        pop = max(1,p['population'])
        p['noble_share'] = p['classes']['nobles']/pop
        p['burgher_share'] = p['classes']['burghers']/pop
        p['development'] = p.pop('development_weighted')/pop
    return result


def split_existing(row):
    """Keep state/foreign/company holdings and top-level government levels intact."""
    if row.get('body') is None:
        return row['levels'],[],Counter({'self':row['levels']})
    private,kept,before = 0,[],Counter()
    for k,obj in root(row['body']).entries():
        if k!='add_ownership':continue
        for owner,value in obj.entries():
            f = fields(value)
            kind = f.get('type')
            domestic = str(f.get('country','')).removeprefix('c:')==row['owner']
            if owner=='building' and domestic and kind in (row['building'],MANOR,FINANCE):
                n = int(f['levels']);private += n
                before[{MANOR:'manor',FINANCE:'finance'}.get(kind,'self')] += n
            else:
                kept.append((owner,value.text()))
    return private,kept,before


def replace_ownership(row,kept,allocation):
    body = ''.join(block(k,v) for k,v in kept)
    for owner,n in sorted(allocation.items()):
        if not n:continue
        kind = OWNER_KIND.get(owner,row['building'])
        body += block('building',f'type = "{kind}"\ncountry = "c:{row["owner"]}"\nregion = "{row["state"]}"\nlevels = {n}')
    if row.get('body') is None:
        row['body'] = f'building = "{row["building"]}"\nreserves = 1\n'+block('add_ownership',body)+'activate_production_methods = { '+' '.join(row['pms'])+' }\n'
    else:
        original = row['body']
        spans = [(o.start,o.end) for k,o in root(original).entries() if k=='add_ownership']
        if not spans: raise ValueError('Private asset without ownership block')
        for i,(a,b) in reversed(list(enumerate(spans))):
            original = original[:a]+(body if i==0 else '')+original[b:]
        row['body'] = original


class OwnershipPlanner:
    def __init__(self,ledger,provinces,tags,policy,reference=None):
        self.ledger,self.policy,self.tags = ledger,dict(policy),tags
        self.reference = reference
        if reference:self.policy['calibrated_reference_shares'] = reference['profiles']
        self.provinces,self.rows,self.denied = provinces,[],[]
        self.hosts = defaultdict(Counter)
        self.costs,self.class_costs = {},{}
        self.before,self.after = defaultdict(Counter),defaultdict(Counter)
        self.expected = {}
        ledger.ownership_jobs = Counter()
        self.by_state = defaultdict(list)
        for p in provinces.values():self.by_state[p['state'],p['country']].append(p)
        for state,tag in ledger.population:
            if tag not in tags:continue
            for owner,kind in OWNER_KIND.items():
                pms = ledger.pms(kind,tag)
                self.costs[tag,owner] = ledger.target.coefficients(kind,pms,ledger.techs[tag])['jobs']
                profession = 'aristocrats' if owner=='manor' else 'capitalists'
                self.class_costs[tag,owner] = ledger.target.numeric(pms)['building_employment_'+profession+'_add']

    def local_weights(self,state,tag,category):
        result = Counter(); total = 0
        for p in self.by_state[state,tag]:
            s = shares(p['noble_share'],p['burgher_share'],p['development'],category,self.ledger.laws[tag],self.policy,p['urban_population']/max(1,p['population']))
            p.setdefault('ownership_shares_by_sector',{})[category] = s
            # Provincial judgments are made BEFORE aggregation. Sector workforce
            # locates assets within a state; no country average or overseas pool.
            c = p['classes']
            if category in ('agriculture','plantation'):
                weight = c['peasants']+c['tribesmen']+c['slaves']+.25*c['laborers']
            elif category=='industry':weight = c['burghers']+c['laborers']
            elif category=='trade':weight = c['burghers']+.1*p['urban_population']
            else:weight = c['laborers']+.25*(c['peasants']+c['tribesmen'])
            weight = max(weight,.01*p['population'])
            total += weight
            for k,v in s.items():result[k] += weight*v
        return {k:result[k]/total for k in ('manor','finance','self')} if total else {'manor':0,'finance':0,'self':1}

    def host_room(self,state,tag,owner):
        cls = 'nobles' if owner=='manor' else 'burghers'
        fraction = 1 if owner=='manor' else self.policy['burgher_investor_fraction']
        people = sum(p['classes'][cls] for p in self.by_state[state,tag])
        slots = math.floor(people*self.ledger.config['workforce_share']*fraction/self.class_costs[tag,owner])
        class_room = max(0,slots-self.hosts[state,tag][owner])
        owner_jobs = self.ledger.ownership_jobs[state,tag]
        productive = self.ledger.jobs(state,tag)-owner_jobs
        staffing = self.ledger.config.get('formal_staffing_safety_fraction',.75)
        free = max(0,self.ledger.population[state,tag]*self.ledger.config['workforce_share']-productive*staffing-owner_jobs)
        return max(0,min(class_room,math.floor(free/self.costs[tag,owner])))

    def apply(self):
        grouped = defaultdict(list)
        for key,row in sorted(self.ledger.rows.items()):
            category = sector(self.ledger.target,row['building'])
            if row['owner'] not in self.tags or row.get('guards') or category is None:continue
            n,kept,before = split_existing(row)
            if not n:continue
            grouped[row['state'],row['owner'],category].append((row,n,kept,before))
        # Reserve pre-existing owner jobs in protected or foreign holdings too.
        replaced = {tuple((r['state'],r['owner'],r['building'])) for rows in grouped.values() for r,n,k,b in rows}
        for key,row in self.ledger.rows.items():
            for op,obj in root(row.get('body') or '').entries():
                if op!='add_ownership':continue
                for k,value in obj.entries():
                    f=fields(value);kind=f.get('type');tag=str(f.get('country','')).removeprefix('c:');state=f.get('region')
                    if kind not in (MANOR,FINANCE) or tag not in self.tags or (state,tag) not in self.ledger.population:continue
                    if key in replaced and tag==row['owner']:continue
                    owner='manor' if kind==MANOR else 'finance';n=int(f['levels'])
                    self.hosts[state,tag][owner] += n
                    self.ledger.ownership_jobs[state,tag] += n*self.costs[tag,owner]
        # Rounding occurs over each local sector portfolio, not separately per
        # one-level building (which would erase minority ownership everywhere).
        for (state,tag,category),entries in sorted(grouped.items()):
            weights = self.local_weights(state,tag,category)
            count = sum(n for r,n,k,b in entries)
            desired = apportioned(weights,count)
            quotas = dict(desired)
            for owner in ('manor','finance'):
                actual = min(quotas[owner],self.host_room(state,tag,owner))
                if actual<quotas[owner]:
                    self.denied.append({'state':state,'country':tag,'sector':category,'owner':owner,'requested':quotas[owner],'allocated':actual,'reason':'local_elite_or_safety_staffing_capacity'})
                quotas['self'] += quotas[owner]-actual;quotas[owner] = actual
                self.hosts[state,tag][owner] += actual
                self.ledger.ownership_jobs[state,tag] += actual*self.costs[tag,owner]
            for row,n,kept,before in sorted(entries,key=lambda x:(-x[1],x[0]['building'])):
                allocated,missing = capped_allocation(weights,n,quotas)
                if missing:raise ValueError('Ownership allocation failed conservation')
                for k,v in allocated.items():quotas[k] -= v
                replace_ownership(row,kept,allocated)
                key=row['state'],row['owner'],row['building']
                self.expected[key] = dict(allocated)
                self.before[tag].update(before);self.after[tag].update(allocated)
                self.rows.append({'state':state,'country':tag,'building':row['building'],'sector':category,
                    'private_levels':n,'before':dict(before),'after':dict(allocated),'local_sector_shares':weights})
            if any(quotas.values()):raise ValueError('Unallocated local ownership quota')
        return self.audit()

    def verify(self,rows):
        checked = 0
        for row in rows:
            key=row['state'],row['owner'],row['building']
            if key not in self.expected:continue
            counts=Counter()
            for op,obj in root(row['body']).entries():
                if op!='add_ownership':continue
                for k,value in obj.entries():
                    f=fields(value)
                    if k=='building' and f.get('country')=='c:'+row['owner'] and f.get('type') in (row['building'],MANOR,FINANCE):
                        if f.get('region')!=row['state']:raise ValueError('Nonlocal ownership allocation')
                        counts[{MANOR:'manor',FINANCE:'finance'}.get(f['type'],'self')] += int(f['levels'])
            if counts!=Counter(self.expected[key]):raise ValueError('Ownership readback mismatch: '+str(key))
            checked += 1
        if checked!=len(self.expected):raise ValueError('Missing ownership rows')
        return checked

    def audit(self):
        countries = {}
        for tag in sorted(self.before):
            ps=[p for p in self.provinces.values() if p['country']==tag]
            pop=sum(p['population'] for p in ps)
            countries[tag]={'source_population':pop,'noble_share':sum(p['classes']['nobles'] for p in ps)/max(1,pop),
                'burgher_share':sum(p['classes']['burghers'] for p in ps)/max(1,pop),
                'private_levels_before':dict(self.before[tag]),'private_levels_after':dict(self.after[tag]),
                'owner_building_job_capacity':sum(n for (s,t),n in self.ledger.ownership_jobs.items() if t==tag)}
        hosts = []
        for (s,t),c in sorted(self.hosts.items()):
            if not sum(c.values()):continue
            full = self.ledger.jobs(s,t)
            owners = self.ledger.ownership_jobs[s,t]
            workforce = self.ledger.population[s,t]*self.ledger.config['workforce_share']
            planned = (full-owners)*self.ledger.config.get('formal_staffing_safety_fraction',.75)+owners
            hosts.append({'state':s,'country':t,'referenced_owned_levels':dict(c),'estimated_owner_jobs':owners,
                'full_staffing_excess_jobs':max(0,full-workforce),'safety_staffing_excess_jobs':max(0,planned-workforce)})
        return {'policy':self.policy,'vanilla_reference':self.reference,'countries':countries,'assets':self.rows,'unmet_owner_allocations':self.denied,
            'owner_hosts':hosts,
            'limitations':['Weights are conversion/gameplay assumptions, not measured historic wealth shares.',
                'Province judgments aggregate into V3 state-country ownership scopes; productive buildings cannot be placed at individual province resolution.',
                'Owners receive existing building levels only; domestic allocation never uses a national class average or cross-state investor pool.',
                'The 20% burgher investor fraction is a ceiling; remaining burghers are not forcibly converted into capitalists.',
                'Employment uses the configured 75% productive staffing credit and full owner staffing; full-staffing overhang is reported, not used to force industrial provinces into worker ownership.',
                'Owner employment follows ordinary law-valid PMs and a 1:1 referenced-level proxy; automatic subsistence estates and engine replacements remain runtime checks.',
                'Government, foreign/company holdings, conditional buildings and fallback countries are preserved. Actual owner hiring, dividends and living standards require a new game.']}
