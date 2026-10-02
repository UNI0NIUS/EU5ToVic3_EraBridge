"""Extract existing EU5 land subunits, never army templates or fleet ship counts."""
import argparse
from collections import Counter
import json
from pathlib import Path
from economy_model import definitions
from extract_m3_politics import fields
from m3_world import digest
from pdx_text import Object, root


def inherited(defs, key, active=()):
    if key in active:
        raise ValueError('Cyclic unit inheritance: '+key)
    f = defs[key]
    return {**(inherited(defs, f['copy_from'], active+(key,)) if 'copy_from' in f else {}), **f}


def extract(save, eu5, output):
    if output.exists():
        raise ValueError('Refusing to overwrite military ledger')
    sha = digest(save)
    defs = definitions(eu5/'in_game/common/unit_types')
    doc = root(save.read_text(encoding='utf-8')).fields()
    units = fields(fields(doc['unit_manager'])['database'])
    subunits = fields(fields(doc['subunit_manager'])['database'])
    result, excluded = [], Counter()
    for uid, obj in subunits.items():
        if not isinstance(obj, Object):
            continue
        f = fields(obj)
        d = inherited(defs, f['type'])
        category = d.get('category', '')
        if not category.startswith('army_'):
            excluded['naval_subunits'] += 1
            continue
        if f.get('prisoner') not in (None, 'no', '0', '4294967295'):
            excluded['prisoners'] += 1
            continue
        size = float(d['max_strength'])*1000
        if size <= 0:
            raise ValueError('Nonpositive unit establishment: '+f['type'])
        result.append({'id': uid, 'owner': f.get('owner'), 'controller': f.get('controller'),
                       'home': f.get('home'), 'unit': f.get('unit'), 'type': f['type'],
                       'category': category, 'establishment_persons': size,
                       # Missing serialized strength is unknown, not zero casualties.
                       'serialized_strength': float(f['strength'])*1000 if 'strength' in f else None,
                       'levies': isinstance(f.get('levies'), Object) and bool(list(f['levies'].entries())),
                       'mercenary': f.get('mercenary') not in (None, 'no', '0', '4294967295')})
    data = {'source_sha256': sha, 'subunits': result, 'excluded': dict(excluded),
            'establishment_basis': 'Inherited unit_type.max_strength * REGIMENT_SIZE (1000); no temporary casualties or templates.',
            'unit_definition_sha256': {str(p): digest(p) for p in sorted((eu5/'in_game/common/unit_types').glob('*.txt'))}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'land_subunits': len(result), 'excluded': dict(excluded), 'source_sha256': sha}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('save', 'eu5', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(extract(a.save, a.eu5, a.output)))
