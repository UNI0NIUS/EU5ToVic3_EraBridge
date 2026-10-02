"""Add source organization constitutions without replacing reviewed political data."""
import argparse
import hashlib
import json
from pathlib import Path

from pdx_text import root
from extract_m3_politics import international_organizations


def enrich(politics, source):
    if hashlib.sha256(source).hexdigest() != politics['source_sha256']:
        raise ValueError('Political input and source save hashes differ')
    orgs = international_organizations(root(source.decode('utf-8')).fields()['international_organization_manager'])
    actual = {o['id']: o for o in orgs}
    result = json.loads(json.dumps(politics))
    for org in result['international_organizations']:
        fresh = actual[org['id']]
        for key, value in org.items():
            if key != 'constitution' and fresh.get(key) != value:
                raise ValueError(f'Existing organization field changed: {org["id"]}/{key}')
        org['constitution'] = fresh['constitution']
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--save', type=Path, required=True)
    p.add_argument('--politics', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists(): raise ValueError('Refusing to overwrite political snapshot')
    result = enrich(json.loads(a.politics.read_text(encoding='utf-8')), a.save.read_bytes())
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(a.output), 'organizations': len(result['international_organizations'])}))
