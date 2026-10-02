"""Hash-pinned, read-only political evidence and installed definition catalogs."""
import argparse
import hashlib
import json
from pathlib import Path
from pdx_text import Object, root
from extract_m3_politics import fields, plain, sequence


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog(directory):
    out = {}
    for path in sorted(directory.glob('*.txt')):
        for key, obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if key and isinstance(obj, Object):
                f = fields(obj)
                out[key] = {'file': str(path), 'sha256': digest(path), 'script': obj.text(),
                            'group': f.get('group') if isinstance(f.get('group'), str) else None,
                            'institution': f.get('institution'),
                            'technologies': sequence(f.get('unlocking_technologies')),
                            'disallowing_laws': sequence(f.get('disallowing_laws'))}
    return out


def extract(save, politics):
    data = save.read_bytes()
    if hashlib.sha256(data).hexdigest() != politics['source_sha256']:
        raise ValueError('Source save does not match reviewed political snapshot')
    doc = root(data.decode('utf-8')).fields()
    result = {}
    for cid, obj in fields(fields(doc['countries'])['database']).items():
        if cid not in politics['countries'] or not isinstance(obj, Object):
            continue
        f = fields(obj)
        g = fields(f.get('government'))
        result[cid] = {
            'advances': [k for k, v in fields(f.get('researched_advances')).items() if v == 'yes'],
            'institutions': [k for k, v in fields(f.get('institutions')).items() if v == 'yes'],
            'privileges': plain(g.get('implemented_privileges')),
            'societal_values': plain(g.get('societal_values')),
            'estates': plain(g.get('estates')),
            'bureaucracies': plain(g.get('bureaucracies')),
            'parliament_type': fields(g.get('parliament')).get('parliament_type'),
        }
    return {'schema': 1, 'source_sha256': politics['source_sha256'], 'countries': result}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--save', type=Path, required=True)
    p.add_argument('--politics', type=Path, required=True)
    p.add_argument('--eu5', type=Path, required=True)
    p.add_argument('--v3', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    evidence = extract(a.save, json.loads(a.politics.read_text(encoding='utf-8')))
    (a.output/'features.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    definitions = {'eu5': {}, 'v3': {}}
    for kind in ('laws', 'government_reforms', 'advances', 'estate_privileges', 'societal_values', 'institution'):
        definitions['eu5'][kind] = catalog(a.eu5/'in_game/common'/kind)
    for kind in ('laws', 'institutions', 'technology/technologies'):
        definitions['v3'][kind] = catalog(a.v3/'common'/kind)
    (a.output/'definitions.json').write_text(json.dumps(definitions, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'countries': len(evidence['countries']), 'definitions': {g: {k: len(v) for k,v in d.items()} for g,d in definitions.items()}}))
