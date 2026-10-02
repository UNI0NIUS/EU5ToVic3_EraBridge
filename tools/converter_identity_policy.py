"""Cross-save identity settings. No saved countries, populations or owner IDs."""
from collections import Counter, defaultdict
import re


def clean_label(value):
    # Remove workflow annotations only; internal identifiers and audit records stay stable.
    return re.sub(r'\s*[（(](?:审查映射|审核映射|暂定|待审核|reviewed mapping|provisional)[）)]', '', value, flags=re.I)


def dated_mapping(mapping, policy, source_date):
    result=dict(mapping)
    year=int(source_date.split('.')[0])
    for source,rule in policy.get('dated_mappings',{}).items():
        if year>=rule['from_year']:result[source]=rule['target']
    return result


def homelands(history, rounded, source_rows, mapping, inverse, lookup, existing):
    home=defaultdict(set, {s:set(cs) for s,cs in existing.items()})
    counts=Counter();totals=Counter();evidence=Counter();reasons=[]
    for (state,owner,culture,religion),n in rounded.items():
        counts[state,culture]+=n;totals[state]+=n
    active={c for (s,c),n in counts.items() if n}
    for (s,c),n in counts.items():
        if c.startswith('eu5_migrant_') and 2*n>totals[s]:
            home[s].add(c);reasons.append(dict(state=s,culture=c,basis='strict_whole_state_majority'))
    for r in source_rows:
        evidence[r['location'],mapping[r['source_culture']]]+=int(r['centipersons'])
    for r in history['entries']:
        culture=r['culture']
        if r['status']!='candidate_core' or culture not in active:continue
        for anchor,allowed in r.get('anchors',{}).items():
            # Presence is a cross-save applicability check, not proof of history.
            if not evidence[anchor,culture]:continue
            linked={lookup[p][0] for p in inverse.get(anchor,()) if p in lookup}
            for state in linked & set(r['states']) & set(allowed):
                home[state].add(culture)
                reasons.append(dict(state=state,culture=culture,anchor=anchor,basis='curated_historical_core_and_current_source_presence'))
    return home,reasons
