"""Keep geographic capacity independent of population, jobs and political borders."""
from collections import Counter
from economy_model import apportioned
from extract_m3_politics import fields


def preserve_geography(ledger):
    policy = ledger.config.get('geography_policy', 'vanilla_capacity')
    if policy not in ('vanilla_capacity', 'legacy_employment_expansion'):
        raise ValueError('Unknown geography policy: '+policy)
    return policy == 'vanilla_capacity'


def fixed_resource_kinds(target):
    if not hasattr(target, '_fixed_resource_kinds'):
        target._fixed_resource_kinds = {k for state in target.states.values() for k in fields(state.get('capped_resources'))}
    return target._fixed_resource_kinds


def local_limit(ledger, state, tag, kind):
    shares = Counter(ledger.owners[state].values())
    if kind in ledger.arable_kinds:
        total = int(ledger.target.states[state].get('arable_land', 0))
    elif kind in fixed_resource_kinds(ledger.target):
        total = int(fields(ledger.target.states[state].get('capped_resources')).get(kind, 0))
    else:
        return None  # Discoverable resources and urban buildings are separate systems.
    return apportioned(shares, total).get(tag, 0)


def constrain_existing(ledger):
    """Fit inherited buildings to geography before the planner adds new industry.

    Farms share ONE land envelope; each fixed resource has its own envelope.
    Preserve the local farm mix by largest remainders. Do not create compensating
    deposits or silently move people. Every displaced job/level is auditable.
    """
    if not preserve_geography(ledger):
        return []
    result = []
    for state, tag in sorted(ledger.population):
        rows = ledger.local(state, tag)
        farms = {r['building']: r['levels'] for r in rows if r['building'] in ledger.arable_kinds}
        farm_cap = apportioned(Counter(ledger.owners[state].values()), int(ledger.target.states[state].get('arable_land', 0))).get(tag, 0)
        farm_targets = apportioned(farms, min(sum(farms.values()), farm_cap))
        for r in rows:
            kind = r['building']
            limit = farm_targets.get(kind) if kind in farms else local_limit(ledger, state, tag, kind)
            if limit is None or r['levels'] <= limit:
                continue
            jobs = ledger.coefficients(r)['jobs']
            result.append({'state': state, 'country': tag, 'building': kind,
                           'before': r['levels'], 'after': limit,
                           'displaced_job_capacity': (r['levels']-limit)*jobs,
                           'reason': 'original_geographic_capacity'})
            ledger.put(state, tag, kind, limit, 'original_geographic_capacity', r['pms'])
    return result
