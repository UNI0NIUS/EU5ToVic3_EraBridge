"""Bound culture expansion using actual candidate assets and population groups."""
from collections import Counter, defaultdict
from pathlib import Path
from build_m3_world import load_localization
from m4_religions import definitions

METRICS=('used_cultures','resident_assets','migrant_assets','political_assets',
         'resident_heritage_groups','resident_language_groups','population_groups','effective_culture_definitions')

def enforce(limits,counts):
    if set(limits)-{'policy'} != {'max_'+k for k in METRICS}:
        raise ValueError('Incomplete or unknown global culture budget')
    for key in METRICS:
        limit=limits['max_'+key]
        if type(limit) is not int or limit<0:raise ValueError('Invalid culture budget: '+key)
        if counts[key]>limit:raise ValueError('Culture budget exceeded: '+key+' = '+str(counts[key])+' > '+str(limit))

def check_and_catalog(out,game,political,profile,ready,crosswalk,migrants,write_csv):
    limits=profile.get('culture_budget')
    if not limits:return None
    residents=definitions(out/'identity_assets/common/cultures')
    migrant_defs=definitions(out/'migrant_assets/common/cultures')
    groups=definitions(out/'identity_assets/common/discrimination_trait_groups')
    # Religion assets share this directory. Include reviewed resident groups
    # without accidentally counting separate religion heritage groups.
    resident_groups={k:v for k,v in groups.items() if k.startswith(('eu5_resident_','eu5_aggregate_','eu5_reviewed_'))}
    native=definitions(game/'common/cultures')
    political_defs={c['target'] for c in political['custom_cultures']}
    used={k[2] for k in ready}
    counts={'used_cultures':len(used),'resident_assets':len(residents),'migrant_assets':len(migrant_defs),
            'political_assets':len(political_defs),'resident_heritage_groups':sum(v['type']=='heritage' for v in resident_groups.values()),
            'resident_language_groups':sum(v['type']=='language' for v in resident_groups.values()),'population_groups':len(ready),
            'effective_culture_definitions':len(native.keys()|political_defs|residents.keys()|migrant_defs.keys())}
    enforce(limits,counts)
    labels={}
    for base in (game,Path(political['mod_directory']),out/'identity_assets',out/'migrant_assets'):
        labels.update(load_localization(base/'localization/simp_chinese'))
    source_members=defaultdict(set)
    for source,(target,method,reason) in crosswalk.items():source_members[target].add(source)
    for c in migrants['cultures']:source_members[c['target']].add(c['source'])
    totals=Counter();popgroups=Counter()
    for (_,_,culture,_),n in ready.items():totals[culture]+=n;popgroups[culture]+=1
    write_csv(out/'active_culture_catalog.csv',['culture','name','kind','source_identity_count','source_identities','centipersons','population_groups'],
        ((c,labels.get(c,c),'migrant' if c in migrant_defs else 'resident_aggregate_or_exception' if c in residents else 'political' if c in political_defs else 'vanilla',
          len(source_members[c]),'|'.join(sorted(source_members[c])),totals[c],popgroups[c]) for c in sorted(used,key=lambda c:-totals[c])))
    return {'status':'passed','limits':limits,'counts':counts,'scope':'Culture definitions and state/owner/culture/religion groups; not an in-game tick benchmark.'}
