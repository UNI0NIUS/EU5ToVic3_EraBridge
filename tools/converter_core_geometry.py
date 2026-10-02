"""Conservative province projection, separate from whole-state claim policy."""
from collections import Counter, defaultdict
from fractions import Fraction
from pdx_text import root
from build_m2_prototype import objects, strings

CLAIM_PERCENT = 30
PROVINCE_PERCENT = 50


def province_states(mod):
    path=mod/'common/history/states/00_eu5_world.txt'
    result={}
    for state,obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['STATES']):
        for key,value in obj.entries():
            if key=='create_state':
                for p in strings(value.fields()['owned_provinces']):
                    if p in result:raise ValueError('Duplicate owned province: '+p)
                    result[p]=state.removeprefix('s:')
    return result


def project(cores, geography, province_state, province_percent=PROVINCE_PERCENT):
    """Each mapped source location supplies one vote; ambiguous slivers do not win."""
    reverse=defaultdict(set)
    for sid,names in cores.items():
        for name in set(names):reverse[name].add(sid)
    support=defaultdict(dict,{sid:{} for sid in cores});ambiguous=0
    for p,names in geography.items():
        if p not in province_state:continue
        names=set(names)
        if not names:continue
        counts=Counter(sid for n in names for sid in reverse[n])
        ambiguous+=len(names)>1
        for sid,n in counts.items():
            if n*100>=len(names)*province_percent:support[sid][p]=[n,len(names)]
    return {sid:dict(sorted(ps.items())) for sid,ps in support.items()},ambiguous


def coverage(provinces, province_state, threshold=CLAIM_PERCENT):
    """Denominator is all inhabited/owned land provinces of the whole state."""
    totals=Counter(province_state.values())
    counts=Counter(province_state[p] for p in provinces if p in province_state)
    return [dict(state=s,core_provinces=n,state_provinces=totals[s],
                 share=float(Fraction(n,totals[s])),claim=n*100>=totals[s]*threshold)
            for s,n in sorted(counts.items())]
