"""Build a population-aware, auditable economic/army overlay without installing it."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re
import shutil
from economy_model import Target, apportioned, block, building_rows, closure, definitions, render_buildings
from economy_capacity import Ledger, carry_land, rural_kinds, write_land
from economy_armies import convert as armies
from economy_fleets import convert as fleets, verify as verify_fleets
from economy_naval_source import prepare as prepare_source_navy
from economy_market import land_edges, components, coastal, provision
from extract_m3_politics import fields, sequence
from pdx_text import Object, root
from m3_world import digest
from economy_source_structure import profile as source_profile, seed_resources
from economy_acceptance import british_fiscal_reference, screen as acceptance_screen
from economy_administration import provision as provision_administration
from economy_bureaucracy import AdministrationBudget
from economy_development import DevelopmentPlanner
from economy_geography import preserve_geography, constrain_existing, local_limit
from economy_agriculture import AgriculturePlanner
from economy_ownership import OwnershipPlanner, province_evidence, vanilla_reference


def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value): Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        yield from csv.DictReader(stream)


def active_laws(obj,target,country):
    if not hasattr(target,'_law_definitions'):
        target._law_definitions = definitions(target.game/'common/laws')
        target._law_effects = {k:o for k,o in root((target.game/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(o,Object)}
    defs,effects = target._law_definitions,target._law_effects
    result = {}
    def process(o):
        last_if = None
        for key,value in o.entries():
            if key == 'activate_law':
                law = value.split(':')[-1]
                result[defs[law]['group']] = law
            elif key in effects:
                process(effects[key])
            elif key == 'if':
                conditions = fields(fields(value)['limit'])
                if set(conditions) == {'country_is_islamic'}:
                    last_if = country['religion'] in ('sunni','shiite')
                elif set(conditions) == {'is_country_type'}:
                    last_if = country['country_type'] == conditions['is_country_type']
                else:
                    raise ValueError('Unsupported starting law condition: '+str(conditions))
                if last_if: process(value)
            elif key == 'else':
                if last_if is False: process(value)
    process(obj)
    return set(result.values())


def allowed_producer(ledger,state,tag,kind):
    target = ledger.target
    if not ledger.allowed(kind,tag): return False
    if kind in ledger.arable_kinds and kind not in rural_kinds(target,state): return False
    if fields(target.buildings[kind].get('potential')).get('is_coastal') == 'yes' and not coastal(ledger,state,tag): return False
    group = target.buildings[kind]['building_group']
    if group in ('bg_mining','bg_logging','bg_fishing') or kind in ('building_logging_camp','building_fishing_wharf'):
        if kind not in fields(target.states[state].get('capped_resources')): return False
    return True


def output_pms(ledger,tag,kind,good,current=None):
    chosen = current or ledger.pms(kind,tag)
    # Select an unlocked output variant when the default secondary PM produces none
    # (hardwood, sheep fabric). Automation is still kept at the non-saving default.
    if ledger.target.coefficients(kind,chosen,ledger.techs[tag])['outputs'].get(good,0): return chosen
    for i,group in enumerate(sequence(ledger.target.buildings[kind].get('production_method_groups'))):
        options = [p for p in sequence(ledger.target.groups[group]['production_methods']) if ledger.target.available(p,ledger.techs[tag],ledger.laws[tag])]
        for pm in options:
            candidate = chosen[:i]+[pm]+chosen[i+1:]
            if ledger.target.coefficients(kind,candidate,ledger.techs[tag])['outputs'].get(good,0): return candidate
    return chosen


def support_good(ledger,tag,good,wanted,kinds,reason):
    from economy_supply_chain import improve_existing, planning_balance, planning_coefficients, expansion_room, safe_delta, net_delta
    if getattr(ledger,'supply_chain_policy',None):
        before = planning_balance(ledger,tag)[good]
        improve_existing(ledger,tag,good,kinds)
        wanted = max(0,wanted-(planning_balance(ledger,tag)[good]-before))
    remaining = max(0,wanted)
    for kind in kinds:
        if remaining <= 0: break
        if kind not in ledger.target.buildings: raise ValueError('Unknown support producer: '+kind)
        candidates = [s for s,t in ledger.population if t==tag and allowed_producer(ledger,s,tag,kind)]
        for s in sorted(candidates,key=lambda s:(-ledger.rows.get((s,tag,kind),{}).get('levels',0),-ledger.population[s,tag],s)):
            if remaining <= 0: break
            old = ledger.rows.get((s,tag,kind))
            pms = output_pms(ledger,tag,kind,good,old['pms'] if old else None)
            output = ledger.target.coefficients(kind,pms,ledger.techs[tag])['outputs'].get(good,0)
            if output <= 0: continue
            if old and old['pms'] != pms:
                if getattr(ledger,'supply_chain_policy',None) and not safe_delta(ledger,tag,net_delta(planning_coefficients(ledger,kind,old['pms'],tag),planning_coefficients(ledger,kind,pms,tag),old['levels'])):
                    pms = old['pms']
                    output = ledger.coefficients(old)['outputs'].get(good,0)
                    if output <= 0: continue
                before = ledger.balance(tag)[good]
                ledger.put(s,tag,kind,old['levels'],reason+'_pm',pms)
                remaining -= ledger.balance(tag)[good]-before
            if remaining <= 0: break
            room = ledger.capped_room(s,tag,kind,pms)
            # Check upstream affordability before releasing workers from other assets.
            requested = min(20,math.ceil(remaining/output))
            input_room = expansion_room(ledger,tag,kind,pms,requested,good)
            if input_room == 0: continue
            if room == 0 and reason.startswith(('worker_living_standard_','industrial_input_support_')):
                jobs = ledger.target.coefficients(kind,pms,ledger.techs[tag])['jobs']
                workforce_room(ledger,s,tag,min(20,math.ceil(remaining/output))*jobs,release_surplus_farms=True)
                room = ledger.capped_room(s,tag,kind,pms)
            n = expansion_room(ledger,tag,kind,pms,min(math.ceil(remaining/output),room),good)
            if n:
                ledger.add(s,tag,kind,n,reason,pms)
                remaining -= n*output
    return max(0,remaining)


def provision_food(ledger,baseline,tags,policy):
    foods = {'grain','fish','meat','fruit','groceries'}
    prices = ledger.target.prices
    uk_output = sum(sum(v*prices[g] for g,v in ledger.target.coefficients(r['building'],r['pms'],set(baseline['technologies']))['outputs'].items() if g in foods)*r['levels'] for r in baseline['buildings'])
    national = Counter()
    for (s,t),p in ledger.population.items(): national[t] += p
    result = {}
    ledger.food_reference_floors = {}
    for tag in sorted(tags):
        reference = uk_output/baseline['population']*national[tag]*policy['domestic_food_reference_scale']
        if hasattr(ledger,'development'):
            reference *= ledger.development.profiles[tag]['commercial_food_reference_factor']
        ledger.food_reference_floors[tag] = reference
        goal = max(reference,living_requirements(ledger,tag,policy['target_worker_wealth'])['basic_food']*1.10)
        farms = [k for k in ledger.target.buildings if k.endswith('_farm') and not 'subsistence' in k]
        # Respect native crop suitability: pasture/coastal states can supply food
        # through livestock or fish instead of being forced into grain farming.
        for good,kinds in [('grain',sorted(farms)),('fish',['building_fishing_wharf']),
                           ('meat',['building_livestock_ranch']),('fruit',['building_banana_plantation'])]:
            net = sum(ledger.balance(tag)[g]*prices[g] for g in foods)
            missing = max(0,goal-net)
            if missing <= 0: break
            support_good(ledger,tag,good,missing/prices[good],kinds,'commercial_food_reference_and_reserve')
        actual = sum(ledger.balance(tag)[g]*prices[g] for g in foods)
        result[tag] = {'reference_net_food_base_value':round(goal,2),'estimated_net_commercial_food_base_value':round(actual,2),
                       'reference_gap_base_value':round(max(0,goal-actual),2),
                       'note':'Static food capacity proxy, excludes in-kind subsistence, pop consumption and trade; not a famine guarantee.'}
    return result


def living_requirements(ledger,tag,wealth):
    if not hasattr(ledger,'buy_packages'):
        ledger.buy_packages = definitions(ledger.target.game/'common/buy_packages')
    basket = fields(ledger.buy_packages['wealth_'+str(wealth)]['goods'])
    equivalent_consumers = 0
    for (state,t),pop in ledger.population.items():
        if t!=tag: continue
        workforce = pop*ledger.config['workforce_share']
        # Full formal staffing gives the upper food demand of the proposed capacity.
        formal = min(workforce,ledger.jobs(state,t))
        unfilled = max(0,workforce-formal)
        sub = ledger.target.states[state].get('subsistence_building')
        land = apportioned(Counter(ledger.owners[state].values()),int(ledger.target.states[state].get('arable_land',0))).get(t,0)
        farms = sum(r['levels'] for r in ledger.local(state,t) if r['building'] in ledger.arable_kinds)
        subjobs = ledger.target.coefficients(sub,ledger.pms(sub,t),ledger.techs[t])['jobs'] if sub else 0
        subsistence = min(unfilled,max(0,land-farms)*subjobs)
        unemployed = max(0,unfilled-subsistence)
        households_per_worker = (ledger.config['workforce_share']+(1-ledger.config['workforce_share'])*.5)/ledger.config['workforce_share']
        # Landless people do not receive the in-kind subsistence discount. This
        # is unmet target consumption, not a forecast of their income or wealth.
        equivalent_consumers += (formal+unemployed+subsistence*.05)*households_per_worker
    def needs(*names): return sum(float(basket.get('popneed_'+n,0)) for n in names)*equivalent_consumers/10000
    return {'basic_food':needs('basic_food'),'clothing':needs('simple_clothing','standard_clothing'),
            'simple_clothing':needs('simple_clothing'),'standard_clothing':needs('standard_clothing'),
            'furniture':needs('crude_items'),'heating':needs('heating'),
            'household_items':needs('household_items'),'equivalent_consumers':equivalent_consumers}


def provision_living_goods(ledger,tags,policy):
    if hasattr(ledger,'development'):
        from economy_consumption import provision as provide_household_substitutes
        return provide_household_substitutes(ledger,tags,policy['target_worker_wealth'])
    for tag in sorted(tags):
        need = living_requirements(ledger,tag,policy['target_worker_wealth'])
        # Reserve intermediate inputs first. Separate end goods avoid double-counting
        # scarce fabric/wood as both industrial inputs and household consumption.
        for category,good,kinds in (('clothing','clothes',['building_textile_mill']),
                                   ('furniture','furniture',['building_furniture_manufactory']),
                                   ('heating','coal',['building_coal_mine'])):
            required = need[category]/ledger.target.prices[good]
            support_good(ledger,tag,good,max(0,required-ledger.balance(tag)[good]),kinds,'worker_living_standard_'+category)


def provision_rails(ledger,tags,rounds=3):
    before = len(ledger.changes)
    for (state,tag),pop in sorted(ledger.population.items()):
        if tag not in tags or not ledger.allowed('building_railway',tag): continue
        rs = ledger.local(state,tag)
        usage = sum(ledger.target.infrastructure_usage(r['building'])*r['levels'] for r in rs)
        available = ledger.target.infrastructure(state,pop,ledger.techs[tag],rs)
        transportation = sum((ledger.coefficients(r)['outputs'].get('transportation',0)-ledger.coefficients(r)['inputs'].get('transportation',0))*r['levels'] for r in rs)
        if usage <= available and transportation >= 0: continue
        pms = ledger.pms('building_railway',tag)
        dummy = {'building':'building_railway','levels':1,'pms':pms}
        gain = ledger.target.infrastructure(state,pop,ledger.techs[tag],rs+[dummy])-available-ledger.target.infrastructure_usage('building_railway')
        if gain <= 0: continue
        rail_transport = ledger.target.coefficients('building_railway',pms,ledger.techs[tag])['outputs'].get('transportation',0)
        wanted = max(0,math.ceil((usage-available)/gain),math.ceil(-transportation/rail_transport) if rail_transport>0 else 0)
        jobs = ledger.target.coefficients('building_railway',pms,ledger.techs[tag])['jobs']
        workforce_room(ledger,state,tag,wanted*jobs)
        n = min(wanted,ledger.capped_room(state,tag,'building_railway'))
        ledger.add(state,tag,'building_railway',n,'full_local_economy_infrastructure',pms)
    # Freeing railway workers can itself enable transport-consuming automation.
    # Re-evaluate its new local demand; report any remainder after the bound.
    if rounds>1 and len(ledger.changes)>before:
        provision_rails(ledger,tags,rounds-1)


def workforce_room(ledger,state,tag,reserve=0,release_surplus_farms=False,automation_only=False):
    ceiling = ledger.population[state,tag]*ledger.config['workforce_share']-reserve
    while ledger.jobs(state,tag)>ceiling:
        choices = []
        for r in ledger.local(state,tag):
            if r['building']=='building_barrack' or r.get('guards'): continue
            old = ledger.coefficients(r)
            groups = sequence(ledger.target.buildings[r['building']].get('production_method_groups'))
            for group in groups:
                members = sequence(ledger.target.groups[group]['production_methods'])
                indices = [i for i,p in enumerate(r['pms']) if p in members]
                if len(indices) != 1:
                    raise ValueError('Expected one active PM per group: '+r['building']+'/'+group)
                index = indices[0]
                for pm in members:
                    if not ledger.target.available(pm,ledger.techs[tag],ledger.laws[tag]): continue
                    methods = r['pms'][:index]+[pm]+r['pms'][index+1:]
                    try:
                        c = ledger.target.coefficients(r['building'],methods,ledger.techs[tag])
                    except ValueError as exc:
                        if str(exc).startswith('Unsupported economic PM scaling:'): continue
                        raise
                    if c['jobs']>=old['jobs'] or any(c['outputs'].get(g,0)<v for g,v in old['outputs'].items()): continue
                    saved = (old['jobs']-c['jobs'])*r['levels']
                    additional = sum(ledger.target.prices[g]*(v-old['inputs'].get(g,0)) for g,v in c['inputs'].items())
                    choices.append((additional/max(1,saved),-saved,r['building'],methods,r))
        if choices:
            _,_,kind,methods,r = min(choices,key=lambda x:x[:3])
            ledger.put(state,tag,kind,r['levels'],'unlocked_automation_for_workforce_and_infrastructure',methods)
            continue
        if automation_only: break
        # Transport takes priority over surplus export capacity. Preserve local food
        # and military establishments; only remove a level whose outputs remain surplus.
        balance = ledger.balance(tag)
        needs = living_requirements(ledger,tag,10)
        foods = {'grain','fish','meat','fruit','groceries'}
        food_total = sum(balance[g]*ledger.target.prices[g] for g in foods)
        food_floor = max(needs['basic_food']*1.10,getattr(ledger,'food_reference_floors',{}).get(tag,0))
        protected = {'grain':needs['basic_food']/ledger.target.prices['grain'],
                     'clothes':needs['clothing']/ledger.target.prices['clothes'],
                     'furniture':needs['furniture']/ledger.target.prices['furniture'],
                     'coal':needs['heating']/ledger.target.prices['coal']}
        if hasattr(ledger,'development'):
            from economy_consumption import screen as household_screen
            protected.update(household_screen(ledger,tag,10)['goods_reserved'])
        options = []
        for r in ledger.local(state,tag):
            c = ledger.coefficients(r)
            if (r['building'] in ledger.arable_kinds and not release_surplus_farms) or not c['outputs'] or c['jobs']<=0 or r['levels']<=1: continue
            if r['building'] in ('building_port','building_railway'): continue
            food_removed = sum(v*ledger.target.prices[g] for g,v in c['outputs'].items() if g in foods)
            if (not food_removed or food_total-food_removed>=food_floor) and all(balance[g]-protected.get(g,0)>=v for g,v in c['outputs'].items() if g not in foods):
                options.append((sum(ledger.target.prices[g]*balance[g] for g in c['outputs']),r['building'],r))
        if not options: break
        _,kind,r = max(options,key=lambda x:x[:2])
        ledger.put(state,tag,kind,r['levels']-1,'release_surplus_production_workers_for_basic_needs' if release_surplus_farms else 'release_surplus_production_workers_for_transport')


def provision_nonrural(ledger,tags,baseline):
    """UK production methods/industry mix, but employment scale from this campaign."""
    if not ledger.config['preserve_nonrural_employment_capacity']: return []
    civilian = {'building_textile_mill','building_furniture_manufactory','building_food_industry',
                'building_glassworks','building_paper_mill','building_tooling_workshop'}
    uk = Counter()
    for r in baseline['buildings']:
        if r['building'] in civilian: uk[r['building']] += r['levels']
    report = []
    for (s,t),pop in sorted(ledger.population.items()):
        if t not in tags: continue
        rs = ledger.local(s,t)
        rural = sum(ledger.source_classes[s,t,c] for c in ledger.config['rural_classes'])*ledger.config['workforce_share']
        military = sum(ledger.coefficients(r)['jobs']*r['levels'] for r in rs if r['building'] in ('building_barrack','building_naval_administration'))
        source_goal = sum(ledger.source_classes[s,t,c] for c in ('laborers','burghers'))*ledger.config['workforce_share']
        # Active regular soldiers can exceed the source estate's quarter-workforce proxy.
        goal = min(source_goal,max(0,pop*ledger.config['workforce_share']-rural-military))
        occupied = sum(ledger.coefficients(r)['jobs']*r['levels'] for r in rs if r['building'] not in ledger.arable_kinds and r['building']!='building_barrack')
        gap = max(0,goal-occupied)
        if gap < 2500: continue
        options = {k:n for k,n in uk.items() if ledger.allowed(k,t)}
        if not options:
            report.append({'state':s,'country':t,'unfilled_jobs':round(gap),'reason':'manufacturing_technology_locked'})
            continue
        # Explicit consumer-industry additions avoid multiplying arms and naval output
        # simply because a source realm has a large working population.
        average_jobs = sum(n*ledger.target.coefficients(k,ledger.pms(k,t),ledger.techs[t])['jobs'] for k,n in options.items())/sum(options.values())
        for k,n in apportioned(options,math.floor(gap/average_jobs+.5)).items():
            n = min(n,ledger.capped_room(s,t,k))
            if n: ledger.add(s,t,k,n,'source_nonrural_employment_with_british_civilian_mix')
        report.append({'state':s,'country':t,'source_goal':round(source_goal),'feasible_nonrural_goal':round(goal),'capacity_before':occupied})
    return report


def verify(ledger,output,army_report,land,employment,fleet_report=None):
    actual = building_rows(output/'overlay/common/history/buildings/00_eu5_world.txt')
    errors = []
    seen = set(); resources = Counter()
    for r in actual:
        key = r['state'],r['owner'],r['building']
        if key in seen: errors.append('duplicate '+str(key))
        seen.add(key)
        if r['levels'] != ledger.rows[key]['levels']: errors.append('level mismatch '+str(key))
        if not ledger.allowed(r['building'],r['owner']): errors.append('locked building '+str(key))
        resources[r['state'],r['building']] += r['levels']
        if r['pms'] != ledger.rows[key]['pms']: errors.append('PM readback '+str(key))
        groups = sequence(ledger.target.buildings[r['building']].get('production_method_groups'))
        members = [set(sequence(ledger.target.groups[g]['production_methods'])) for g in groups]
        if any(sum(pm in m for pm in r['pms']) != 1 for m in members) and r['owner'] in army_report['countries'] and not r.get('guards'):
            errors.append('PM group coverage '+str(key))
        if any(not any(pm in m for m in members) for pm in r['pms']):
            errors.append('foreign building PM '+str(key))
        for pm in r['pms']:
            if not set(sequence(ledger.target.pms[pm].get('unlocking_technologies'))) <= ledger.techs[r['owner']]:
                errors.append('locked pm '+str(key)+' '+pm)
    for (s,k),n in resources.items():
        cap = fields(ledger.target.states[s].get('capped_resources')).get(k)
        if cap is not None and n > int(cap): errors.append('resource cap '+s+' '+k)
    doc = root((output/'overlay/common/history/military_formations/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['MILITARY_FORMATIONS']
    totals = Counter(); hqs = set()
    regions = {s:k for k,f in definitions(ledger.target.game/'common/strategic_regions').items() for s in sequence(f.get('states'))}
    for key,obj in doc.entries():
        tag = key[2:]
        if tag not in army_report['countries']: continue
        for op,form in obj.entries():
            if op != 'create_military_formation' or fields(form).get('type') != 'army': continue
            hq = fields(form)['hq_region'][3:]
            if (tag,hq) in hqs: errors.append('duplicate HQ army '+tag+' '+hq)
            hqs.add((tag,hq))
            for operation,unit in form.entries():
                if operation != 'combat_unit': continue
                f = fields(unit); state = f['state_region'][2:]
                if regions[state] != hq: errors.append('foreign HQ state '+state)
                if (state,tag) not in ledger.population: errors.append('foreign army state '+state)
                totals[state,tag] += int(f['count'])
    for (s,t,k),r in ledger.rows.items():
        if k == 'building_barrack' and t in army_report['countries'] and totals[s,t] != r['levels']:
            errors.append('army/barracks mismatch '+s+' '+t)
    for (s,t),n in totals.items():
        if ledger.rows.get((s,t,'building_barrack'),{}).get('levels',0) != n:
            errors.append('unit without barracks '+s+' '+t)
    for path in (output/'overlay/map_data/state_regions').glob('*.txt'):
        for s,obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if s in land and int(fields(obj)['arable_land']) != land[s]: errors.append('arable readback '+s)
            if preserve_geography(ledger) and fields(obj).get('arable_land') != ledger.target.states[s].get('arable_land'):
                errors.append('original arable definition readback '+s)
            caps = fields(fields(obj).get('capped_resources'))
            expected = fields(ledger.target.states[s].get('capped_resources'))
            if caps != expected: errors.append('resource definition readback '+s)
    if preserve_geography(ledger):
        for s,t in ledger.population:
            farms = sum(r['levels'] for r in ledger.local(s,t) if r['building'] in ledger.arable_kinds)
            cap = apportioned(Counter(ledger.owners[s].values()),int(ledger.target.states[s].get('arable_land',0))).get(t,0)
            if farms>cap: errors.append('local arable cap '+s+' '+t)
            for r in ledger.local(s,t):
                limit = local_limit(ledger,s,t,r['building'])
                if r['building'] not in ledger.arable_kinds and limit is not None and r['levels']>limit:
                    errors.append('local resource cap '+s+' '+t+' '+r['building'])
    elif any(r['capacity_gap_full_staffing'] for r in employment): errors.append('employment capacity gap')
    if hasattr(ledger,'agriculture'):
        for r in ledger.agriculture.audit()['states']:
            if r['commercial_job_excess'] or r['commercial_land_excess']:
                errors.append('commercial agriculture envelope '+r['state']+' '+r['country'])
    if errors: raise ValueError('Completion verification failed: '+json.dumps(errors[:30]))
    ownership_count = ledger.ownership.verify(actual) if hasattr(ledger,'ownership') else 0
    fleet_count = verify_fleets(ledger,(output/'overlay/common/history/military_formations/00_eu5_world.txt').read_text(encoding='utf-8-sig'),fleet_report) if fleet_report else 0
    return {'status':'passed_static_runtime_pending','building_rows':len(actual),'source_backed_armies':len(hqs),
            'province_based_ownership_rows_verified':ownership_count,
            'allocated_fleets':fleet_count,
            'employment_gap_parts':sum(r['capacity_gap_full_staffing']>0 for r in employment),
            'employment_gap_workers':sum(r['capacity_gap_full_staffing'] for r in employment),
            'balance_ready':not any(r['capacity_gap_full_staffing'] for r in employment),
            'checks':['building_readback','production_method_group_coverage','resource_caps_and_definition_readback','technology_gates','army_barrack_exact_equality','one_army_per_owned_hq',
                      'land_definition_readback',('original_geography_caps_and_explicit_employment_gaps' if preserve_geography(ledger) else 'employment_capacity_no_structural_gap')]+
                     (['fleet_ship_conservation','one_fleet_per_owned_coastal_hq','fleet_naval_department_capacity'] if fleet_report else []),
            'not_verified':['hiring_and_qualifications','wages_and_treasury','actual_market_access','runtime_food_security']}


def build(economy,package,source_path,military_path,game,eu5,config_path,output,naval_path=None):
    if output.exists(): raise ValueError('Refusing to overwrite completed economy run')
    output.mkdir(parents=True)
    config = load(config_path); source = load(source_path); military = load(military_path)
    p = load(package/'package_report.json'); mod = Path(p['mod_directory'])
    political = load(Path(p['political_run'])/'conversion_report.json')
    if source['source_sha256'] != political['source_sha256']: raise ValueError('Source mismatch')
    if military['source_sha256'] != source['source_sha256']: raise ValueError('Military source mismatch')
    for rel,sha in p['output_sha256'].items():
        if digest(mod/rel) != sha: raise ValueError('Base package changed '+rel)
    for rel,sha in load(economy/'manifest.json')['outputs'].items():
        if digest(economy/rel) != sha: raise ValueError('Economic candidate changed '+rel)
    demographic = Path(p['demographic_run']); stage = demographic/'staging'
    population,classes,links = Counter(),Counter(),defaultdict(Counter)
    for r in csv_rows(demographic/'demographics/resident_population_groups.csv'):
        population[r['state'],r['owner']] += int(r['preview_integer_persons'])
    for r in csv_rows(demographic/'template_fallback/template_population_groups.csv'):
        population[r['state'],r['owner']] += int(r['persons'])
    for r in csv_rows(stage/'province_population_draft.csv'):
        classes[r['target_state'],r['target_owner'],r['source_class']] += int(r['centipersons'])/100
        links[r['source_location']][r['target_state'],r['target_owner']] += int(r['centipersons'])
    links = {k:{pair:n/sum(v.values()) for pair,n in v.items()} for k,v in links.items()}
    print('Population and class ledger loaded',flush=True)
    target = Target(game); baseline = load(economy/'british_baseline.json')
    target._law_definitions = definitions(game/'common/laws')
    target._law_definitions.update(definitions(mod/'common/laws'))
    target._law_effects = {k:o for k,o in root((game/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(o,Object)}
    owners = load(Path(p['political_run'])/'province_owners.json')
    history = fields(root((economy/'overlay/common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    history = {k[2:]:o for k,o in history.entries()}
    techs = {t:{v for k,v in o.entries() if k=='add_technology_researched'} for t,o in history.items()}
    # Fallback country effects can still contain era shorthand.
    from build_economy import expand_template_tech
    effects = {k:o for k,o in root((game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(o,Object)}
    techs = {t:expand_template_tech(o,effects,target) for t,o in history.items()}
    target.global_technologies = set().union(*techs.values())
    laws = {t:active_laws(o,target,political['countries'][t]) for t,o in history.items()}
    tags = {t for t,c in political['countries'].items() if c['source_id'] is not None}
    british_pms = defaultdict(set)
    for r in baseline['buildings']: british_pms[r['building']].update(r['pms'])
    ledger = Ledger(target,building_rows(economy/'overlay/common/history/buildings/00_eu5_world.txt'),population,techs,laws,owners,british_pms,config['employment'])
    if 'supply_chain' in config:
        ledger.supply_chain_policy = dict(config['supply_chain'])
    ledger.source_classes = classes
    ledger.source_paid_agriculture,source_extraction,source_structure = source_profile(source,eu5,links)
    army_text,army_report = armies(ledger,source,military,political,links,classes,mod,config['military'])
    print('Army establishments mapped',flush=True)
    edges,ledger.coastal_provinces = land_edges(game,output.parent/'land_edges.json',owners)
    graph = components(owners,edges,population)
    source_ships,source_navy_report = None,None
    if naval_path:
        source_ships,source_navy_report = prepare_source_navy(ledger,source,load(naval_path),political,links)
    army_text,fleet_report = fleets(ledger,army_text,tags,classes,config['military'],source_ships)
    print('Fleet naval departments allocated',flush=True)
    # Complete law resolution prevents retained, mutually exclusive farming PMs.
    for r in list(ledger.rows.values()):
        if r['owner'] not in tags: continue
        if not r.get('guards'):
            methods = target.complete_methods(r['building'],r['pms'],ledger.pms(r['building'],r['owner']))
            ledger.put(r['state'],r['owner'],r['building'],r['levels'],'explicit_default_production_methods',methods)
            r = ledger.rows[r['state'],r['owner'],r['building']]
        if any(not target.available(pm,techs[r['owner']],laws[r['owner']]) for pm in r['pms']):
            # Conditional monuments are left to their existing in-game guards.
            if r.get('guards'): continue
            ledger.put(r['state'],r['owner'],r['building'],r['levels'],'resolved_starting_law_pm_compatibility',ledger.pms(r['building'],r['owner']))
    geography_changes = constrain_existing(ledger)
    agriculture_changes = []
    if 'agriculture' in config:
        if not preserve_geography(ledger):
            raise ValueError('Source agriculture policy requires finite geographic capacity')
        ledger.agriculture = AgriculturePlanner(ledger,source,links,tags,config['agriculture'])
        agriculture_changes = ledger.agriculture.constrain_existing()
    development_changes = []
    if 'development' in config:
        ledger.development = DevelopmentPlanner(ledger,source,links,source_structure,load(economy/'country_economy.json'),political,config['development'])
        for state,tag in population:
            if tag in tags: workforce_room(ledger,state,tag,automation_only=True)
        development_changes = ledger.development.normalize_overloaded_states(tags)
        print('Source-relative development envelopes prepared',flush=True)
    # Discretionary universities/construction are not population-scaled. Administration
    # addresses actual tax-capacity gaps with a transparent reference-cost screen.
    national = Counter()
    for (s,t),pop in population.items(): national[t] += pop
    fiscal_baseline = next(Path(p) for p in load(economy/'economy_report.json')['input_sha256'] if Path(p).name=='vic3-start.txt')
    fiscal_reference = british_fiscal_reference(fiscal_baseline)
    administration = provision_administration(ledger,tags,political,fiscal_reference,baseline)
    bureaucracy = AdministrationBudget(ledger,tags,history,mod/'common/history/states/00_eu5_world.txt',config['bureaucracy'])
    bureaucracy_changes = bureaucracy.provision(administration)
    print('National administration floor provisioned',flush=True)
    resource_changes = seed_resources(ledger,source_extraction,tags)
    print('Territorial market graph loaded',flush=True)
    market = provision(ledger,political,graph,tags,baseline,config['market'])
    nonrural = provision_nonrural(ledger,tags,baseline)
    food = provision_food(ledger,baseline,tags,config['food'])
    print('Food capacity provisioned',flush=True)
    from economy_supply_chain import apply as screen_supply, planning_balance, audit as supply_audit
    if 'supply_chain' in config:
        screen_supply(ledger,tags,config['supply_chain'],config['input_support']['goods'])
    for iteration in range(config['input_support']['iterations']):
        print('Input support pass '+str(iteration+1),flush=True)
        before = len(ledger.changes)
        bureaucracy_changes.extend(r for r in bureaucracy.provision(administration) if r['added_levels'])
        for tag in sorted(tags):
            for good,kinds in config['input_support']['goods'].items():
                support_good(ledger,tag,good,max(0,-planning_balance(ledger,tag)[good]),kinds,'industrial_input_support_'+good)
        food = provision_food(ledger,baseline,tags,config['food'])
        provision_living_goods(ledger,tags,config['food'])
        provision_rails(ledger,tags)
        market = provision(ledger,political,graph,tags,baseline,config['market'])
        if len(ledger.changes)==before: break
    provision_rails(ledger,tags)
    for s,t in population:
        if t in tags: workforce_room(ledger,s,t)
    if 'ownership' in config:
        ledger.ownership = OwnershipPlanner(ledger,province_evidence(csv_rows(stage/'province_population_draft.csv'),source),tags,config['ownership'],vanilla_reference(target,config['ownership']))
        ledger.ownership.apply()
        print('Province-based private ownership allocated',flush=True)
        for tag in tags:
            goal = max(ledger.food_reference_floors[tag],living_requirements(ledger,tag,config['food']['target_worker_wealth'])['basic_food']*1.10)
            actual = sum(ledger.balance(tag)[g]*target.prices[g] for g in ('grain','fish','meat','fruit','groceries'))
            food[tag].update(reference_net_food_base_value=round(goal,2),estimated_net_commercial_food_base_value=round(actual,2),reference_gap_base_value=round(max(0,goal-actual),2))
    ledger.isolated_states = {(s,g['country']) for g in market if not g['has_local_port_connection'] for s in g['states']}
    land,employment = carry_land(ledger,classes,tags)
    shutil.copytree(economy/'overlay',output/'overlay')
    overlay = output/'overlay'
    (overlay/'common/history/buildings/00_eu5_world.txt').write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    army_path = overlay/'common/history/military_formations/00_eu5_world.txt'
    army_path.parent.mkdir(parents=True,exist_ok=True); army_path.write_text(army_text,encoding='utf-8-sig')
    country_blocks = []
    for tag,obj in history.items():
        body = obj.text()
        if tag in tags:
            body = re.sub(r'(?m)^\s*add_technology_researched\s*=\s*\w+\s*$','',body)
            body = ''.join(f'add_technology_researched = {t}\n' for t in sorted(techs[tag]))+body
        country_blocks.append(block('c:'+tag,body).replace(' = {',' ?= {',1))
    (overlay/'common/history/countries/00_eu5_world.txt').write_text(block('COUNTRIES',''.join(country_blocks)),encoding='utf-8-sig')
    if preserve_geography(ledger):
        # Emit explicit geographic definitions so packaging over an older inflated
        # economic mod cannot leave its land or deposits behind.
        land_files = write_land(target,mod,overlay,
            {s:int(f['arable_land']) for s,f in target.states.items() if 'arable_land' in f},
            {s:True for s in target.states})
    else:
        land_files = write_land(target,mod,overlay,land,resource_changes)
    infrastructure = []
    transportation_gaps = []
    for (s,t),pop in sorted(population.items()):
        if t not in tags: continue
        rs = ledger.local(s,t)
        usage = sum(target.infrastructure_usage(r['building'])*r['levels'] for r in rs)
        if hasattr(ledger,'ownership'):
            usage += sum(target.infrastructure_usage({'manor':'building_manor_house','finance':'building_financial_district'}[k])*n for k,n in ledger.ownership.hosts[s,t].items())
        capacity = target.infrastructure(s,pop,techs[t],rs)
        transport = sum((ledger.coefficients(r)['outputs'].get('transportation',0)-ledger.coefficients(r)['inputs'].get('transportation',0))*r['levels'] for r in rs)
        if transport < -.001: transportation_gaps.append({'state':s,'country':t,'deficit':-transport})
        if usage > capacity+.001: infrastructure.append({'state':s,'country':t,'usage':usage,'capacity':capacity,'deficit':usage-capacity})
    summary = {}
    industry = {r['building'] for r in baseline['buildings'] if target.buildings[r['building']]['building_group'] in ('bg_manufacturing',)}
    for tag in sorted(tags):
        es = [r for r in employment if r['country']==tag]
        levels,jobs = Counter(),Counter()
        for r in ledger.rows.values():
            if r['owner']==tag:
                levels[r['building']] += r['levels'];jobs[r['building']] += ledger.coefficients(r)['jobs']*r['levels']
        nonrural_goal = max(0,sum(classes[s,tag,c] for s,t in population if t==tag for c in ('laborers','burghers'))-sum(ledger.source_paid_agriculture[s,tag] for s,t in population if t==tag))*config['employment']['workforce_share']
        rural_jobs = sum(r['commercial_agricultural_jobs'] for r in es)
        nonrural_jobs = sum(jobs.values())-rural_jobs-jobs['building_barrack']-jobs['building_naval_administration']
        owner_jobs = sum(n for (s,t),n in getattr(ledger,'ownership_jobs',{}).items() if t==tag)
        summary[tag] = {'population':national[tag],'building_levels':dict(levels),'formal_jobs_by_building':dict(jobs),
                        'formal_job_capacity':sum(jobs.values())+owner_jobs,'owner_building_job_capacity':owner_jobs,'source_nonrural_workforce_proxy':round(nonrural_goal),
                        'nonrural_job_capacity_excluding_automatic_urban_centers':nonrural_jobs,
                        'nonrural_job_proxy_gap':max(0,round(nonrural_goal-nonrural_jobs)),
                        'source_rural_persons':sum(r['source_rural_persons'] for r in es),
                        'old_arable_share':sum(r['old_arable_share'] for r in es),'new_arable_share':sum(r['new_arable_share'] for r in es),
                        'subsistence_job_capacity':sum(r['new_subsistence_job_capacity'] for r in es),
                        'additional_fallback_jobs_beyond_source_rural':sum(r['fallback_beyond_source_rural_jobs'] for r in es),
                        'industrial_input_gaps':{g:round(-n,2) for g,n in ledger.balance(tag).items() if n<-.001},
                        'armies':army_report['countries'][tag], 'fleets':fleet_report['countries'][tag], 'food_capacity':food[tag]}
    write(output/'country_capacity.json',summary);write(output/'employment.json',employment)
    write(output/'army_mapping.json',army_report);write(output/'market_connections.json',market)
    write(output/'fleet_mapping.json',fleet_report)
    if source_navy_report: write(output/'source_navy_mapping.json',source_navy_report)
    write(output/'changes.json',ledger.changes);write(output/'infrastructure_gaps.json',infrastructure)
    write(output/'local_transportation_gaps.json',transportation_gaps)
    write(output/'nonrural_employment.json',nonrural)
    write(output/'source_industry_structure.json',source_structure)
    write(output/'source_resource_capacity.json',resource_changes)
    write(output/'geography_building_adjustments.json',geography_changes)
    if hasattr(ledger,'ownership'):
        write(output/'ownership.json',ledger.ownership.audit())
        write(output/'ownership_provinces.json',list(ledger.ownership.provinces.values()))
    if hasattr(ledger,'agriculture'):
        write(output/'agriculture.json',ledger.agriculture.audit())
        write(output/'agriculture_adjustments.json',agriculture_changes)
    write(output/'source_resource_requests.json',ledger.source_resource_requests)
    if 'supply_chain' in config:
        write(output/'supply_chain.json',supply_audit(ledger,tags))
    acceptance = acceptance_screen(ledger,baseline,fiscal_reference,army_report,market,infrastructure,config['food']['target_worker_wealth'])
    write(output/'living_standards_and_fiscal_screen.json',acceptance)
    write(output/'administration.json',administration)
    write(output/'bureaucracy.json',bureaucracy.audit())
    write(output/'bureaucracy_changes.json',bureaucracy_changes)
    if hasattr(ledger,'development'):
        write(output/'development.json',ledger.development.audit())
        write(output/'development_normalization.json',development_changes)
    write(output/'effective_laws.json',{t:sorted(v) for t,v in laws.items()})
    write(output/'verification.json',verify(ledger,output,army_report,land,employment,fleet_report))
    write(output/'report.json',{'status':'candidate_static_verified_runtime_pending','source_sha256':source['source_sha256'],
          'base_package':str(package.resolve()),'economy_candidate':str(economy.resolve()),'changed_land_states':len(land),
          'land_files':land_files,'warnings':ledger.warnings,'unresolved_market_components':sum(not g['has_local_port_connection'] for g in market),
          'infrastructure_gaps':len(infrastructure),'policy':config,
          'limitations':['No guaranteed hiring, wages, solvency, food security or actual market access before game testing.',
                         'Non-rural occupational gaps are explicit and not erased by counting fallback subsistence as industry.',
                         'Original geographic capacity is retained by default; unmet employment is a balance issue, not authorization to create land or deposits.',
                         'Province-count shares approximate the engine split-state allocation; runtime confirmation required.',
                         'Military/society template technology remains compatible; standing_army is added only for existing regular troops.',
                         'Source warship counts use vanilla hull types; transports are recorded separately.' if naval_path else 'No naval source ledger supplied; ship counts retain the territorial template.',
                         'Ships without coastal manpower capacity or unlocked technology are reported as unallocated; landlocked transit is not fabricated.']})
    inputs = [config_path,source_path,military_path,package/'package_report.json',economy/'manifest.json',stage/'province_population_draft.csv',fiscal_baseline]
    if naval_path: inputs.append(naval_path)
    tool_paths = set(Path(__file__).parent.glob('economy_*.py')) | {Path(__file__)}
    tool_paths.update(Path(__file__).parent/n for n in ('pdx_text.py','extract_m3_politics.py','extract_military_source.py','extract_economy_source.py','technology_mapping.py','build_economy.py'))
    definition_paths = [p for folder in ('common/buildings','common/building_groups','common/production_methods','common/production_method_groups','common/technology/technologies','common/goods','common/pop_types','common/buy_packages','common/laws','common/combat_unit_types','common/ship_types','common/ship_modifications','common/strategic_regions','common/state_traits','common/static_modifiers','common/defines','common/scripted_effects','map_data/state_regions') for p in sorted((game/folder).glob('*.txt'))]
    definition_paths += [p for folder in ('in_game/common/building_types','in_game/common/production_methods') for p in sorted((eu5/folder).glob('*.txt'))]
    if 'ownership' in config:
        definition_paths += sorted((game/'common/history/buildings').glob('*.txt'))
    write(output/'manifest.json',{'inputs':{str(p.resolve()):digest(p) for p in inputs},
          'tools':{str(p.resolve()):digest(p) for p in sorted(tool_paths)},
          'game_definitions':{str(p.resolve()):digest(p) for p in definition_paths},
          'outputs':{p.relative_to(output).as_posix():digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return {'status':'candidate_static_verified_runtime_pending','states':len(employment),'changed_land_states':len(land),'armies':len(army_report['formations']),'fleets':len(fleet_report['formations'])}


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    for name in ('economy','package','source','military','game','eu5','config','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--naval',type=Path,help='Extracted source hull ledger; omit only for legacy template fleet runs')
    a = parser.parse_args()
    print(json.dumps(build(a.economy,a.package,a.source,a.military,a.game,a.eu5,a.config,a.output,a.naval)))
