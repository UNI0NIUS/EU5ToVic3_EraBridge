"""Explicit conversation-approved corrections, separate from workstation reviews."""
def apply_overrides(inverse, weights, entries, source_names, valid_provinces):
    records = []
    for name, entry in entries.items():
        if name not in source_names or entry['operation'] not in ('add','replace'):
            raise ValueError('Invalid explicit location correction: '+name)
        before = dict(weights.get(name, {p:1 for p in inverse[name]}))
        if before != entry['expected_weights']:
            raise ValueError('Location correction baseline changed: '+name)
        targets = entry['targets']
        if not targets or any(p not in valid_provinces or type(n) is not int or n<=0 for p,n in targets.items()):
            raise ValueError('Invalid corrected targets: '+name)
        if entry['operation']=='add' and set(targets)&before.keys():
            raise ValueError('Add correction repeats existing target: '+name)
        after = {**before,**targets} if entry['operation']=='add' else dict(targets)
        inverse[name] = set(after); weights[name] = after
        records.append({'source_location':name,'operation':entry['operation'],'before':before,'after':after,'reason':entry['reason']})
    return records
