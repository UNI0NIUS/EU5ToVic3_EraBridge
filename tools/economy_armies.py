"""One formation per owned strategic HQ; source establishments determine battalions."""
from collections import Counter, defaultdict
import math
from economy_capacity import capped_allocation
from economy_model import apportioned, block, closure, definitions
from extract_m3_politics import fields, sequence
from pdx_text import Object, root


def convert(ledger, source, military, political, links, classes, mod, policy):
    target = ledger.target
    if source['source_sha256'] != military['source_sha256']:
        raise ValueError('Military and economic source mismatch')
    regions = {state:key for key,f in definitions(target.game/'common/strategic_regions').items()
               for state in sequence(f.get('states'))}
    laws = definitions(target.game/'common/laws')
    unitdefs = definitions(target.game/'common/combat_unit_types')
    source_to_tag = {str(c['source_id']):t for t,c in political['countries'].items() if c['source_id'] is not None}
    types = {'infantry':['combat_unit_type_irregular_infantry','combat_unit_type_line_infantry','combat_unit_type_skirmish_infantry'],
             'artillery':['combat_unit_type_cannon_artillery','combat_unit_type_mobile_artillery'],
             'cavalry':['combat_unit_type_hussars','combat_unit_type_dragoons']}
    establishments, home, excluded = defaultdict(Counter),defaultdict(Counter),defaultdict(Counter)
    for u in military['subunits']:
        tag = source_to_tag.get(u['owner'])
        if not tag:
            continue
        if u['levies'] or u['mercenary'] or u['category'] == 'army_auxiliary':
            reason = 'levies' if u['levies'] else 'mercenaries' if u['mercenary'] else 'auxiliary'
            excluded[tag][reason] += u['establishment_persons']
            continue
        category = 'artillery' if u['category'] == 'army_artillery' else 'cavalry' if 'cavalry' in u['category'] else 'infantry'
        establishments[tag][category] += u['establishment_persons']
        location = source['locations'].get(u['home'],{}).get('name')
        for (state,owner),weight in links.get(location,{}).items():
            if owner == tag:
                home[tag][state] += u['establishment_persons']*weight
    # Preserve fleets for the subsequent naval department allocation pass.
    forms = defaultdict(list)
    history = root((mod/'common/history/military_formations/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['MILITARY_FORMATIONS']
    for key,country in history.entries():
        tag = key[2:]
        for op,obj in country.entries():
            if tag not in source_to_tag.values() or op != 'create_military_formation' or fields(obj).get('type') != 'army':
                forms[tag].append(block(op,obj.text()) if isinstance(obj,Object) else f'{op} = {obj}\n')
    for key in list(ledger.rows):
        if key[1] in source_to_tag.values() and key[2] in ('building_barrack','building_conscription_center'):
            del ledger.rows[key]
    report, all_units, formations = {}, [], []
    for tag in sorted(source_to_tag.values()):
        amounts = establishments[tag]
        count = math.floor(sum(amounts.values())*policy['regular_manpower_scale']/1000+0.5)
        states = [s for (s,t) in ledger.population if t == tag]
        if count:
            # A standing regular army in the source is direct evidence of this baseline.
            ledger.techs[tag] = closure(ledger.techs[tag] | {'standing_army'},target.techs)
        lawcap = max([0]+[int(fields(laws[l].get('modifier')).get('state_building_barrack_max_level_add',0)) for l in ledger.laws[tag]])
        military_pops = {s:classes[s,tag,'soldiers'] for s in states}
        def normalized(values):
            total = sum(values.values())
            return {s:v/total for s,v in values.items()} if total else {}
        a,b = normalized(military_pops),normalized(home[tag])
        weights = {s:policy['military_population_weight']*a.get(s,0)+(1-policy['military_population_weight'])*b.get(s,0) for s in states}
        if not sum(weights.values()):
            weights = {s:ledger.population[s,tag] for s in states}
        caps = {s:min(lawcap,math.floor(ledger.population[s,tag]*policy['state_military_population_ceiling']/1000)) for s in states}
        allocation,unallocated = capped_allocation(weights,count,caps)
        actual = sum(allocation.values())
        categories = apportioned(amounts,actual)
        remaining = dict(allocation)
        by_hq = defaultdict(list)
        selected, downgraded = {}, []
        for category in ('artillery','cavalry','infantry'):
            eligible = [u for u in types[category] if u in unitdefs and set(sequence(unitdefs[u].get('unlocking_technologies'))) <= ledger.techs[tag]]
            if not eligible:
                # Preserve manpower when a source weapon branch has no supported V3 equivalent.
                unit = 'combat_unit_type_irregular_infantry'
                if categories.get(category,0): downgraded.append(category)
            else:
                unit = eligible[-1]
            selected[category] = unit
            if int(unitdefs[unit]['max_manpower']) != 1000:
                raise ValueError('Unexpected target battalion manpower')
            part,_ = capped_allocation(remaining,categories.get(category,0),remaining)
            for state,n in sorted(part.items()):
                if not n: continue
                remaining[state] -= n
                item = {'country':tag,'state':state,'hq':regions[state],'type':unit,'count':n}
                all_units.append(item); by_hq[regions[state]].append(item)
                for key,val in fields(unitdefs[unit].get('upkeep_modifier')).items():
                    if key.startswith('goods_input_') and key.endswith('_add'):
                        ledger.military_demand[tag][key[12:-4]] += float(val)*n
        for state,n in sorted(allocation.items()):
            if n:
                ledger.put(state,tag,'building_barrack',n,'source_regular_establishment_and_local_military_population')
        for hq,units in sorted(by_hq.items()):
            body = f'type = army\nhq_region = sr:{hq}\n'
            body += ''.join(block('combat_unit',f'type = unit_type:{u["type"]}\nstate_region = s:{u["state"]}\ncount = {u["count"]}') for u in units)
            forms[tag].append(block('create_military_formation',body))
            formations.append({'country':tag,'hq':hq,'battalions':sum(u['count'] for u in units)})
        report[tag] = {'regular_establishment_persons':sum(amounts.values()),'source_combat_categories':dict(amounts),
                       'excluded_establishment_persons':dict(excluded[tag]),'source_soldier_population':round(sum(military_pops.values())),
                       'requested_battalions':count,'exported_battalions':actual,'unallocated_battalions':unallocated,
                       'state_law_cap':lawcap,'state_allocation':allocation,'combat_types':selected,'downgraded_categories':downgraded,
                       'formation_count':len(by_hq),'unit_goods_inputs':dict(ledger.military_demand[tag])}
    text = block('MILITARY_FORMATIONS',''.join(block('c:'+t, ''.join(fs)).replace(' = {',' ?= {',1) for t,fs in sorted(forms.items())))
    return text,{'countries':report,'units':all_units,'formations':formations,
                 'policy':policy,'note':'Existing regular establishment, not arbitrary army stack count. Levy/mercenary/auxiliary manpower is reported separately; fleets retain prior conversion.'}
