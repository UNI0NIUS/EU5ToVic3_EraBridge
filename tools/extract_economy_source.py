"""Read-only economic ledger, checked against the C++ P001 import selection."""
import argparse
import json
from pathlib import Path
from pdx_text import Object, root
from extract_m3_politics import validate_audit_document, fields
from m3_world import digest


def extract(save, audit_path, output):
    if output.exists():
        raise ValueError('Refusing to overwrite economic source ledger')
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    if audit['errors'] or audit['policies']['missing_building_pop'] != 'P001':
        raise ValueError('Economy requires a successful P001 audit')
    sha = digest(save)
    doc = root(save.read_text(encoding='utf-8')).fields()
    validate_audit_document(doc, audit)
    db = lambda name: fields(fields(doc[name])['database'])
    countries = {}
    for cid, obj in db('countries').items():
        if not isinstance(obj, Object):
            continue
        f = fields(obj)
        countries[cid] = {
            'definition': f.get('definition'),
            'advances': sorted(k for k, v in fields(f.get('researched_advances')).items() if v == 'yes'),
            'institutions': sorted(k for k, v in fields(f.get('institutions')).items() if v == 'yes')}
    excluded = {str(b['id']) for b in audit['building_selection']['skipped']}
    buildings, skipped = [], []
    for bid, obj in db('building_manager').items():
        if not isinstance(obj, Object):
            continue
        f = fields(obj)
        row = {'id': bid, **{k: v for k, v in f.items() if k and not isinstance(v, Object)},
               'pms': sorted(k for k, v in f.items() if isinstance(v, Object))}
        (skipped if bid in excluded else buildings).append(row)
    if len(buildings) != audit['building_selection']['included_count'] or {b['id'] for b in skipped} != excluded:
        raise ValueError('Building selection differs from C++ audit')
    audited = {str(x['id']): x for x in audit['locations']}
    locations = {}
    for lid, obj in fields(fields(doc['locations'])['locations']).items():
        f = fields(obj)
        stats = fields(fields(f.get('population')).get('pop_stats'))
        a = audited[lid]
        locations[lid] = {
            'name': a['name'], 'owner': str(a['owner']), 'population': float(a['population_persons']),
            'rank': f.get('rank', 'rural_settlement'), 'raw_material': f.get('raw_material'),
            'development': float(f.get('development', 0)),
            'class_employment': {k: {a: float(b)*1000 for a,b in fields(v).items()
                                     if a in ('population_ratio','produced','unemployed','employed_in_rgo')}
                                 for k,v in stats.items()},
            'rgo_workers': sum(float(fields(v).get('employed_in_rgo', 0)) * 1000 for v in stats.values())}
    result = {'schema': 1, 'source_sha256': sha, 'audit_sha256': digest(audit_path),
              'date': audit['date'], 'countries': countries, 'locations': locations,
              'buildings': buildings, 'p001_skipped': skipped}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return {'included': len(buildings), 'p001_skipped': len(skipped), 'countries': len(countries)}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for flag in ('save', 'audit', 'output'):
        p.add_argument('--'+flag, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(extract(a.save, a.audit, a.output)))
