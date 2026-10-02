"""Target population tax capacity, with an explicit reference-cost screen."""
from collections import Counter
import math
from economy_model import definitions
from extract_m3_politics import fields


def pm_modifier(target,pms,scope,key):
    return sum(float(fields(obj).get(key,0)) for pm in pms for obj in fields(target.pms[pm].get(scope)).values())


def provision(ledger,tags,political,reference,baseline):
    laws = definitions(ledger.target.game/'common/laws')
    poptypes = definitions(ledger.target.game/'common/pop_types')
    report = []
    for (state,tag),pop in sorted(ledger.population.items()):
        if tag not in tags or political['countries'][tag]['country_type'] in ('decentralized','colonial','company'): continue
        kind = 'building_government_administration'
        if not ledger.allowed(kind,tag): continue
        pms = ledger.pms(kind,tag)
        old = ledger.rows.get((state,tag,kind))
        if old:
            ledger.put(state,tag,kind,old['levels'],'unlocked_administration_for_tax_capacity',pms)
        modifiers = Counter({'state_tax_capacity_add':float(ledger.target.base_modifiers.get('state_tax_capacity_add',0))})
        for f in [*(ledger.target.techs[t] for t in ledger.techs[tag]),*(laws[l] for l in ledger.laws[tag])]:
            for k,v in fields(f.get('modifier')).items():
                if k in ('state_tax_capacity_add','state_tax_capacity_mult'): modifiers[k] += float(v)
        for trait in ledger.target.states[state].get('traits',()).entries() if hasattr(ledger.target.states[state].get('traits'),'entries') else ():
            for k,v in fields(ledger.target.traits[trait[1]].get('modifier')).items():
                if k in ('state_tax_capacity_add','state_tax_capacity_mult'): modifiers[k] += float(v)
        base = modifiers['state_tax_capacity_add']
        mult = max(.01,1+modifiers['state_tax_capacity_mult'])
        per_level = pm_modifier(ledger.target,pms,'state_modifiers','state_tax_capacity_add')*mult
        if per_level<=0: continue
        existing = ledger.rows.get((state,tag,kind),{}).get('levels',0)
        capacity = base*mult+existing*per_level
        need = max(0,math.ceil((pop/10000-capacity)/per_level))
        values = ledger.target.numeric(pms)
        wages = sum(v*float(poptypes.get(k[20:-4],{}).get('wage_weight',1)) for k,v in values.items() if k.startswith('building_employment_'))*reference['weekly_base_wage_per_10000']/10000
        c = ledger.target.coefficients(kind,pms,ledger.techs[tag])
        cost = wages+sum(ledger.target.prices[g]*v for g,v in c['inputs'].items())
        benefit_reference = per_level*10000/baseline['population']*reference['weekly_income']
        added = min(need,ledger.capped_room(state,tag,kind)) if benefit_reference>=cost else 0
        if added: ledger.add(state,tag,kind,added,'tax_capacity_with_reference_cost_screen',pms)
        report.append({'state':state,'country':tag,'population':pop,'tax_capacity_before':capacity,
                       'required_tax_capacity':pop/10000,'added_levels':added,'tax_capacity_per_level':per_level,
                       'remaining_tax_capacity_gap':max(0,pop/10000-capacity-added*per_level),
                       'weekly_cost_per_level_at_reference_wage':cost,'reference_revenue_per_added_capacity':benefit_reference,
                       'note':'Reference-cost screen for discretionary local tax capacity. National bureaucracy floor is provisioned separately.'})
    return report
