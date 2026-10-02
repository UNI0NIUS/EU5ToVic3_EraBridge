"""Bounded, market-wide opening supply chains with explicit unresolved deficits.

Build connected producer/input bundles before checking affordability, so an
iron/tools cycle can bootstrap. Never grant technology or delete existing assets.
"""
from collections import Counter,defaultdict
from pathlib import Path
import math
from copy import deepcopy
from types import SimpleNamespace
from converter_project import read
from pdx_text import root
from build_m2_prototype import objects
from economy_model import Target,definitions,building_rows,render_buildings
from package_m4_population_test import parse_pops
from economy_capacity import Ledger
from build_economy import expand_template_tech
from complete_economy import active_laws,allowed_producer,output_pms,living_requirements
from economy_supply_chain import planning_balance,planning_coefficients
from converter_food_markets import market_membership


def membership(mod,game,tags):
    docs=lambda folder:[p.read_text(encoding='utf-8-sig') for p in sorted((mod/'common/history'/folder).glob('*.txt'))]
    def merged(folder):
        d=definitions(game/'common'/folder);d.update(definitions(mod/'common'/folder));return d
    return market_membership(tags,docs('diplomacy'),docs('power_blocs'),merged('diplomatic_actions'),merged('power_bloc_identities'),merged('power_bloc_principles'))[0]


def combined(ledger,tags):
    net=Counter()
    for tag in sorted(tags):net.update(planning_balance(ledger,tag))
    return net


def production_room(ledger,state,tag,kind,pms):
    room=ledger.capped_room(state,tag,kind,pms)
    local=ledger.local(state,tag);usage=ledger.target.infrastructure_usage(kind)
    if kind in ledger.arable_kinds:
        # Floor quotas remain safe when several parts are later merged. A
        # largest-remainder award can otherwise disappear and overfill farms.
        weights=Counter(ledger.owners[state].values());land=int(ledger.target.states[state].get('arable_land',0))
        cap=land*weights[tag]//sum(weights.values())
        room=min(room,max(0,cap-sum(r['levels'] for r in local if r['building'] in ledger.arable_kinds)))
    if usage>0:
        available=ledger.target.infrastructure(state,ledger.population[state,tag],ledger.techs[tag],local)
        used=sum(ledger.target.infrastructure_usage(r['building'])*r['levels'] for r in local)
        room=min(room,max(0,math.floor((available-used)/usage)))
    return room


def household_targets(ledger,tags):
    """Demand scenarios, counting subsistence's saleable output separately."""
    needs=Counter();subsistence=Counter()
    for tag in sorted(tags):
        n=living_requirements(ledger,tag,10)
        # Keep furniture itself represented instead of assigning its entire need
        # to raw wood. Intoxicants were absent from the previous household plan.
        needs['furniture']+=(n['furniture']*.5+n['household_items']*.5)/ledger.target.prices['furniture']
        basket=ledger.buy_packages['wealth_10']['goods'].fields()
        intoxicants=float(basket.get('popneed_intoxicants',0))*n['equivalent_consumers']/10000
        # Tobacco/opium are substitutes. Reserve their net supply before liquor.
        net=planning_balance(ledger,tag)
        alternative=sum(max(0,net[g])*ledger.target.prices[g] for g in ('tobacco','opium'))
        needs['liquor']+=max(0,intoxicants-alternative)/ledger.target.prices['liquor']
        for (s,t),pop in ledger.population.items():
            if t!=tag:continue
            from converter_project import apportion
            land=apportion(int(ledger.target.states[s].get('arable_land',0)),Counter(ledger.owners[s].values())).get(t,0)
            farms=sum(r['levels'] for r in ledger.local(s,t) if r['building'] in ledger.arable_kinds)
            kind=ledger.target.states[s].get('subsistence_building','building_subsistence_farm')
            c=ledger.target.coefficients(kind,ledger.pms(kind,t),ledger.techs[t])
            levels=min(max(0,land-farms),max(0,pop*ledger.config['workforce_share']-ledger.jobs(s,t))/c['jobs']) if c['jobs'] else 0
            for g,v in c['outputs'].items():subsistence[g]+=v*levels
    for good in needs:needs[good]=max(0,needs[good]-subsistence[good])
    return needs


def balance_market(ledger,tags,producers,max_passes=12):
    before=combined(ledger,tags);start=deepcopy(ledger.rows);changes=len(ledger.changes)
    demand=household_targets(ledger,tags);wanted=Counter(demand)
    # Existing intermediate deficits plus household goods; a small reserve for
    # hiring/throughput differences, without imposing exact price equality.
    for tag in tags:
        for key in ledger.by_country[tag]:
            r=ledger.rows[key]
            if r.get('guards'):continue
            for g,n in planning_coefficients(ledger,r['building'],r['pms'],tag)['inputs'].items():wanted[g]+=n*r['levels']*.10
    targeted=set(producers)&{g for g in producers if before[g]<wanted[g]}
    foods=('grain','fish','meat','fruit','groceries')
    food_before=sum(before[g]*ledger.target.prices[g] for g in foods)
    food_need=sum(living_requirements(ledger,t,10)['basic_food'] for t in tags)*1.1
    food_floor=min(food_before,food_need)
    wanted['grain']=max(wanted['grain'],(food_floor-sum(before[g]*ledger.target.prices[g] for g in foods if g!='grain'))/ledger.target.prices['grain'])
    for iteration in range(max_passes):
        moved=0
        for good in producers:
            net=combined(ledger,tags);missing=wanted[good]-net[good]
            if missing<=.01:continue
            for kind in producers[good]:
                candidates=[]
                for (s,t),pop in ledger.population.items():
                    if t not in tags or not allowed_producer(ledger,s,t,kind):continue
                    old=ledger.rows.get((s,t,kind));pms=output_pms(ledger,t,kind,good,old['pms'] if old else None)
                    # Changing existing PMs can remove a co-product. Keep existing
                    # choices; only choose a recipe for a new plant.
                    if old and pms!=old['pms']:continue
                    co=planning_coefficients(ledger,kind,pms,t);output=co['outputs'].get(good,0)-co['inputs'].get(good,0)
                    if output<=0:continue
                    room=production_room(ledger,s,t,kind,pms)
                    if room:candidates.append((-(old or {}).get('levels',0),-pop,s,t,pms,output))
                for _,__,s,t,pms,output in sorted(candidates):
                    room=production_room(ledger,s,t,kind,pms)
                    n=min(room,math.ceil(missing/output),200)
                    if n<=0:continue
                    ledger.add(s,t,kind,n,'market_opening_supply_chain_'+good,pms);moved+=n;missing-=n*output
                    if missing<=0:break
                if missing<=0:break
        if not moved:break
    # A constrained upstream producer may be unable to support the bundle.
    # Remove only newly proposed consumers until no input deficit worsens.
    rejected=0
    for _ in range(1000):
        net=combined(ledger,tags);floors={g:min(0,before[g]) for g in net}
        floors['grain']=max(floors.get('grain',0),(food_floor-sum(net[g]*ledger.target.prices[g] for g in foods if g!='grain'))/ledger.target.prices['grain'])
        bad={g for g,v in net.items() if v<floors[g]-1e-6}
        if not bad:break
        choices=[]
        for k,r in ledger.rows.items():
            extra=r['levels']-start.get(k,{}).get('levels',0)
            if extra<=0 or r['owner'] not in tags:continue
            c=planning_coefficients(ledger,r['building'],r['pms'],r['owner'])
            for g in bad:
                consume=c['inputs'].get(g,0)-c['outputs'].get(g,0)
                if consume>0:choices.append((g,k,min(extra,math.ceil((floors[g]-net[g])/consume))))
        if not choices:raise ValueError('Cannot reconcile proposed supply chain inputs')
        g,k,n=max(choices,key=lambda x:(x[2],x[1]));r=ledger.rows[k]
        ledger.put(r['state'],r['owner'],r['building'],r['levels']-n,'constrained_upstream_'+g,r['pms']);rejected+=n
    else:raise ValueError('Opening supply-chain reconciliation did not converge')
    after=combined(ledger,tags)
    # Counts here are capacity, not projected market prices.
    return dict(members=sorted(tags),before={g:before[g] for g in producers},after={g:after[g] for g in producers},household_demand=dict(demand),food_floor=food_floor,food_after=sum(after[g]*ledger.target.prices[g] for g in foods),
                remaining={g:round(max(0,wanted[g]-after[g]),3) for g in producers if wanted[g]-after[g]>.01},
                added_levels=sum(r['levels']-start.get(k,{}).get('levels',0) for k,r in ledger.rows.items() if r['owner'] in tags),rejected_unsupported_levels=rejected)


def install(mod,game,rules,countries,run=None):
    mod,game,rules=map(Path,(mod,game,rules));target=Target(game)
    for key,folder in [('states','map_data/state_regions'),('buildings','common/buildings'),('pms','common/production_methods'),('groups','common/production_method_groups')]:getattr(target,key).update(definitions(mod/folder))
    target._law_definitions=definitions(game/'common/laws');target._law_definitions.update(definitions(mod/'common/laws'))
    target._law_effects=dict(objects(root((game/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig'))))
    effects=dict(objects(root((game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig'))))
    history=dict(objects(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['COUNTRIES']))
    techs={k[2:]:expand_template_tech(o,effects,target) for k,o in history.items()};laws={k[2:]:active_laws(o,target,countries[k[2:]]) for k,o in history.items()}
    target.global_technologies=set().union(*techs.values());pops=Counter()
    for (s,t,_,__),n in parse_pops(mod/'common/history/pops/00_eu5_world.txt').items():pops[s,t]+=n
    from build_m2_prototype import state_owners
    owners={k[2:]:state_owners(o) for k,o in objects(root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['STATES'])}
    policy=read(rules/'config/personal/economy_capacity.json');path=mod/'common/history/buildings/00_eu5_world.txt';original=building_rows(path)
    ledger=Ledger(target,original,pops,techs,laws,owners,defaultdict(set),policy['employment']);ledger.supply_chain_policy=policy['supply_chain']
    if run is not None:
        import csv
        with (Path(run)/'demographic/staging/province_population_draft.csv').open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):ledger.source_classes[r['target_state'],r['target_owner'],r['source_class']]+=int(r['centipersons'])/100
    producers={g:policy['input_support']['goods'][g] for g in ('wood','hardwood','coal','iron','tools','steel','engines','paper','sugar','fabric','dye','lead','sulfur','fertilizer','silk')}
    producers['grain']=['building_wheat_farm','building_rye_farm','building_maize_farm','building_rice_farm']
    producers.update(furniture=['building_furniture_manufactory'],liquor=['building_food_industry'])
    markets=defaultdict(set)
    for t,m in membership(mod,game,set(techs)).items():markets[m].add(t)
    reports={}
    for m,tags in sorted(markets.items()):
        if not any(countries[t].get('source_id') for t in tags):continue
        reports[m]=balance_market(ledger,tags,producers)
    # Keep old investors when resizing; new factories use native local self ownership.
    from converter_edits import resize_building
    rows=[];originals={(r['state'],r['owner'],r['building']):r for r in original}
    for k,r in ledger.rows.items():
        old=originals.get(k)
        if old and old['levels']!=r['levels']:r=resize_building(old,r['levels'])
        rows.append(r)
    path.write_text(render_buildings(rows),encoding='utf-8-sig')
    return dict(markets=reports,added_levels=sum(r['added_levels'] for r in reports.values()),
                limitations=['Full staffing capacity and wealth-10 household scenario; runtime hiring, qualifications and trade affect prices.',
                'Shared markets follow subject/customs-union rules. Local market access and infrastructure can constrain actual supply.',
                'Existing buildings and technology are preserved. Upstream shortages, resources, infrastructure and labor can leave unresolved gaps.'])
