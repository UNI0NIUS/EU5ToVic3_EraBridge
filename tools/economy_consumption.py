"""Conservative household substitution screen with no double-counted raw goods.

Shares are planning choices, not the engine's supply-weight parameters. Native
pop-needs permits these substitutes; demand, prices and shares remain dynamic.
"""
from collections import Counter

OPTIONS = {
    'standard_clothing': [('clothes', 1)],
    'simple_clothing': [('fabric', .5), ('clothes', 1)],
    'furniture': [('wood', .5), ('furniture', 1)],
    'household_items': [('furniture', .75), ('glass', .75), ('paper', .5)],
    'heating': [('wood', .75), ('coal', 1), ('fabric', .25)],
}
PRODUCERS = {
    'fabric': ['building_cotton_plantation','building_livestock_ranch'],
    'wood': ['building_logging_camp'], 'coal': ['building_coal_mine'],
    'clothes': ['building_textile_mill'], 'furniture': ['building_furniture_manufactory'],
    'glass': ['building_glassworks'], 'paper': ['building_paper_mill'],
}


def allocate(needs, balance, prices):
    stock = Counter({g:max(0,v) for g,v in balance.items()})
    reserved, allocations, missing = Counter(), {}, {}
    for category, options in OPTIONS.items():
        goal = needs[category]; left = goal; assigned = {}
        for good, fraction in options:
            value = min(left, goal*fraction, stock[good]*prices[good])
            units = value/prices[good]
            stock[good] -= units; reserved[good] += units
            assigned[good] = value; left -= value
        allocations[category] = assigned
        missing[category] = max(0,left)
    return {'allocations':allocations, 'shortfalls':missing, 'goods_reserved':dict(reserved)}


def screen(ledger,tag,wealth):
    from complete_economy import living_requirements
    from economy_supply_chain import planning_balance
    return allocate(living_requirements(ledger,tag,wealth), planning_balance(ledger,tag), ledger.target.prices)


def provision(ledger,tags,wealth):
    from complete_economy import living_requirements, support_good
    for tag in sorted(tags):
        for category, options in OPTIONS.items():
            for good, fraction in options:
                needs = living_requirements(ledger,tag,wealth)
                plan = screen(ledger,tag,wealth)
                missing = plan['shortfalls'][category]
                if missing <= .001: break
                room = max(0,needs[category]*fraction-plan['allocations'][category].get(good,0))
                value = min(missing,room)
                if value > 0:
                    support_good(ledger,tag,good,value/ledger.target.prices[good],PRODUCERS[good],'worker_living_standard_'+category)
