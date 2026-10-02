"""Read-only, hash-pinned political supplement to the C++ M1 import report."""
import argparse
import hashlib
import json
from pathlib import Path
from pdx_text import Object, root
from source_flag_context import rank_evidence


def fields(obj):
    return dict(obj.entries()) if isinstance(obj, Object) else {}


def sequence(obj):
    return [v for k, v in obj.entries()] if isinstance(obj, Object) else []


def plain(obj):
    if not isinstance(obj, Object):
        return obj
    return [[k, plain(v)] for k, v in obj.entries()]


def international_organizations(manager):
    result = []
    for i, obj in fields(fields(manager)['database']).items():
        if not isinstance(obj, Object):
            continue
        f = fields(obj)
        statuses = fields(f.get('countries_with_special_status_v2'))
        result.append({'id': i, 'type': f.get('type'), 'members': sequence(f.get('all_members')),
                       'senior': sequence(statuses.get('senior_partner')),
                       'junior': sequence(statuses.get('junior_partner')),
                       'leader': f.get('leader'), 'created': f.get('creation_date'),
                       'special_statuses': {k: sequence(v) for k,v in statuses.items()},
                       'constitution': {
                           'laws': {k: fields(v).get('object') for k,v in fields(f.get('implemented_laws')).items()},
                           'parliament_type': fields(f.get('parliament')).get('parliament_type'),
                           'circles_active': f.get('circles_active') == 'yes',
                           'imperial_circles': sequence(f.get('imperial_circles')),
                           'raw_implemented_laws': plain(f.get('implemented_laws'))},
                       'variables': plain(f.get('variables'))})
    return result


def validate_audit_document(doc, audit):
    """Check a decoded save against the independent import, without a campaign ID."""
    if audit['errors'] or fields(doc.get('metadata')).get('date') != audit['date']:
        raise ValueError('Source save and validated audit do not agree')
    locations = fields(fields(doc['locations'])['locations'])
    if set(locations) != {str(r['id']) for r in audit['locations']}:
        raise ValueError('Source/audit location inventory differs')
    for r in audit['locations']:
        if str(fields(locations[str(r['id'])]).get('owner', '0')) != str(r['owner']):
            raise ValueError('Source/audit owner differs: '+r['name'])
    countries = fields(fields(doc['countries'])['database'])
    tags = fields(fields(doc['countries']).get('tags'))
    for r in audit['countries']:
        country = countries.get(str(r['id']))
        if not isinstance(country, Object) or fields(country).get('definition', '') != r['definition']:
            raise ValueError('Source/audit country identity differs: '+str(r['id']))
        if str(r['id']) in tags and tags[str(r['id'])] != r['tag']:
            raise ValueError('Source/audit current country tag differs: '+str(r['id']))


def extract(save, audit):
    source = save.read_bytes()
    sha = hashlib.sha256(source).hexdigest()
    doc = root(source.decode('utf-8')).fields()
    validate_audit_document(doc, audit)
    del source
    def db(key):
        return fields(fields(doc[key])['database'])
    cultures = {i: fields(o).get('culture_definition', i) for i, o in db('culture_manager').items() if isinstance(o, Object)}
    religions = {i: fields(o).get('definition', i) for i, o in db('religion_manager').items() if isinstance(o, Object)}
    countries = {}
    wanted = set()
    for i, o in db('countries').items():
        if not isinstance(o, Object):
            continue
        f = fields(o)
        g = fields(f.get('government'))
        color = []
        entries = list(o.entries())
        for n, (k, v) in enumerate(entries):
            if k == 'color' and v == 'rgb':
                color = sequence(entries[n + 1][1])
        reforms = [fields(v).get('object') for v in sequence(g.get('implemented_reforms'))]
        countries[i] = {
            'name': plain(f.get('country_name')), 'definition': f.get('definition'), 'flag': f.get('flag'),
            'previous_tags': sequence(f.get('previous_tags')),
            'type': f.get('type'), 'capital': f.get('capital'), 'color': color,
            'culture': cultures.get(f.get('primary_culture')),
            'accepted_cultures': [cultures[c] for c in sequence(f.get('accepted_cultures'))],
            'tolerated_cultures': [cultures[c] for c in sequence(f.get('tolerated_cultures'))],
            'religion': religions.get(f.get('primary_religion')),
            'government': g.get('type'), 'succession': g.get('heir_selection'),
            'ruler': g.get('ruler'), 'regent': g.get('active_regent'), 'heir': g.get('heir'),
            'regency': g.get('regency'), 'reforms': reforms,
            'laws': plain(g.get('implemented_laws')),
            'great_power_rank': f.get('great_power_rank'), 'great_power_points': f.get('great_power_points'),
            'country_rank': rank_evidence(dict(plain(o)), audit['date'])['rank'],
            'rank_evidence': rank_evidence(dict(plain(o)), audit['date']),
            'variable_names': [fields(v).get('flag') for v in sequence(fields(f.get('variables')).get('data'))],
        }
        wanted.update(g[k] for k in ('ruler', 'active_regent', 'heir') if g.get(k))
    characters = {}
    dynasties = db('dynasty_manager')
    for i, o in db('character_db').items():
        if i not in wanted or not isinstance(o, Object):
            continue
        f = fields(o)
        dyn = fields(dynasties.get(f.get('dynasty')))
        characters[i] = {k: f.get(k) for k in ('first_name', 'last_name', 'birth_date', 'female', 'country')}
        characters[i].update(culture=cultures.get(f.get('culture')), religion=religions.get(f.get('religion')),
                             dynasty=dyn.get('name'), alive='alive_data' in f,
                             traits=sequence(f.get('traits')))
    subjects, relations = [], []
    for key, o in doc['diplomacy_manager'].entries():
        if key in ('scripted_mutual', 'scripted_oneway'):
            f = fields(o)
            types = [fields(fields(t)['target']).get('object') for t in sequence(f.get('named_targets'))
                     if fields(t).get('flag') == 'scripted_relation_type']
            for kind in types:
                relations.append({'first': f['first'], 'second': f['second'], 'type': kind,
                                  'mutual': key == 'scripted_mutual', 'start_date': f.get('start_date')})
        if key != 'dependency':
            continue
        f = fields(o)
        types = [fields(fields(t)['target']).get('object') for t in sequence(f['named_targets'])
                 if fields(t).get('flag') == 'subject_type']
        if len(types) != 1:
            raise ValueError('Ambiguous subject type')
        subjects.append({'overlord': f['first'], 'subject': f['second'], 'type': types[0]})
    return {'schema': 1, 'source_sha256': sha, 'date': audit['date'], 'current_age': doc.get('current_age'), 'countries': countries,
            'characters': characters, 'subjects': subjects,
            'relations': relations,
            'international_organizations': international_organizations(doc['international_organization_manager'])}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--save', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Refusing to overwrite an existing extraction')
    result = extract(a.save, json.loads(a.audit.read_text(encoding='utf-8')))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: len(result[k]) for k in ('countries', 'characters', 'subjects')}))
