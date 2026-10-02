"""Preserve populated state-parts while conserving the globally rounded total."""
from collections import Counter,defaultdict

def preserve_populated_parts(exact,rounded):
    out=Counter(rounded);parts=Counter();keys=defaultdict(list)
    for k,n in exact.items():
        if n:keys[k[:2]].append(k)
        parts[k[:2]]+=out[k]
    changes=[]
    for part in sorted(keys):
        if parts[part]:continue
        recipient=min(keys[part],key=lambda k:(-exact[k],k))
        donors=[k for k,n in out.items() if n>1]
        if not donors:raise ValueError('Cannot retain positive state parts within source total')
        donor=min(donors,key=lambda k:(-(out[k]*100-exact[k]),k))
        out[donor]-=1;out[recipient]+=1;parts[donor[:2]]-=1;parts[part]+=1
        changes.append(dict(recipient=recipient,donor=donor,persons=1,reason='integer representation of a source-positive state part; global population unchanged'))
    assert sum(out.values())==sum(rounded.values())
    assert all(parts[p]>0 for p in keys)
    return out,changes
