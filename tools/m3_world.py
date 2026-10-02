"""Deterministic world geometry and political model for the pinned personal campaign."""
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from pdx_text import Object, root
from build_m2_prototype import objects, strings, state_owners


def fields(obj):
    return dict(obj.entries())


def province(value):
    return 'x' + value[1:].upper()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def owner_vote(anchors, locations, valid):
    weights = Counter()
    for name in sorted(set(anchors)):
        row = locations[name]
        owner = str(row['owner'])
        if owner in valid:
            weights[owner] += max(1, int(Decimal(row['population_persons']) * 100))
    return min(weights, key=lambda k: (-weights[k], int(k))) if weights else None


def shift_birth(birth, source_date, target_date):
    parse = lambda value: date(*map(int, value.split('.')[:3]))
    shifted = parse(birth) + (parse(target_date) - parse(source_date))
    return f'{shifted.year}.{shifted.month}.{shifted.day}'


def base36(n):
    result = ''
    while n:
        n, digit = divmod(n, 36)
        result = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'[digit] + result
    return result or '0'


def assign_country_tags(source, represented, target_defs, matches, overrides):
    assigned = {}
    for n, sid in enumerate(sorted(represented, key=int)):
        match = matches.get(sid)
        if match and match['source_tag'] != source[sid]['tag']:
            raise ValueError('Country identity changed since tag review: ' + sid)
        target = overrides.get(sid) or (match['target_tag'] if match else None)
        if target and target not in target_defs:
            raise ValueError('Mapped TAG absent from installed V3: ' + target)
        tag = target or 'E' + base36(n).zfill(2)
        if not target and (len(tag) > 3 or tag in target_defs or tag in assigned.values() or tag in {r['target_tag'] for r in matches.values()} or tag in overrides.values()):
            from native_country_tags import allocate
            reserved = set(target_defs) | set(assigned.values()) | {r['target_tag'] for r in matches.values()} | set(overrides.values())
            tag = allocate([sid], reserved, preferred_prefix='E')[sid]
        if tag in assigned.values() or (not target and tag in target_defs):
            raise ValueError('Country tag collision: ' + tag)
        assigned[sid] = tag
    return assigned


def centroids(path, cache):
    """Compute actual target province centroids; cache tied to the map bitmap hash."""
    import numpy as np
    from PIL import Image
    signature = digest(path)
    if cache.exists():
        cached = load_json(cache)
        if cached['sha256'] == signature:
            return cached['points']
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.uint32)
    values = (rgb[:, :, 0] << 16) | (rgb[:, :, 1] << 8) | rgb[:, :, 2]
    colors, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    h, w = values.shape
    sx = np.bincount(inverse.ravel(), weights=np.tile(np.arange(w), h))
    sy = np.bincount(inverse.ravel(), weights=np.repeat(np.arange(h), w))
    points = {f'x{int(c):06X}': [float(x/n), float(y/n)] for c, x, y, n in zip(colors, sx, sy, counts)}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({'sha256': signature, 'points': points}), encoding='utf-8')
    return points


class World:
    def __init__(self, game, eu5, audit, politics, profile, cache):
        self.game, self.eu5, self.audit, self.politics, self.profile = game, eu5, audit, politics, profile
        if politics['source_sha256'] != profile['source_sha256'] or audit['date'] != profile['source_date']:
            raise ValueError('Source provenance mismatch')
        if audit['status'] not in ('validated_import', 'validated_import_with_skips') or audit['errors']:
            raise ValueError('Expected validated P001 import')
        self.inputs = {}
        self.source = {str(c['id']): c for c in audit['countries'] if c['owned_locations']}
        self.locations = {l['name']: l for l in audit['locations']}
        self.location_ids = {str(l['id']): l['name'] for l in audit['locations']}
        self.states = dict(objects(root(self.read('common/history/states/00_states.txt')).fields()['STATES']))
        self.states = {k.removeprefix('s:'): v for k, v in self.states.items()}
        self.original = {s: {province(p): c for p, c in state_owners(o, strict=False).items()} for s, o in self.states.items()}
        self.country_defs = {}
        self.definition_files = {}
        for path in sorted((game / 'common/country_definitions').glob('*.txt')):
            relative = path.relative_to(game).as_posix()
            for k, o in objects(root(self.read(relative))):
                self.country_defs[k] = o
                self.definition_files[k] = relative
        self.defs = {}
        for path in sorted((game / 'map_data/state_regions').glob('*.txt')):
            self.defs.update({k: o for k, o in objects(root(self.read(path.relative_to(game)))) if k in self.states})
        self.provinces = {s: [province(v) for v in strings(fields(o)['provinces'])] for s, o in self.defs.items()}
        self.province_state = {p: s for s, ps in self.provinces.items() for p in ps}
        self.points = centroids(game / 'map_data/provinces.png', cache / 'centroids.json')
        self.inputs['map_data/provinces.png'] = digest(game / 'map_data/provinces.png')
        self.mapping = defaultdict(list)
        path = Path(__file__).resolve().parents[1] / 'EU5ToVic3/Data_Files/configurables/province_mappings.txt'
        self.mapping_sha256 = digest(path)
        for key, link in objects(root(path.read_text(encoding='utf-8-sig')).fields()['0.0.0']):
            if key != 'link':
                continue
            src = [v for k, v in link.entries() if k == 'eu5']
            for k, v in link.entries():
                if k == 'vic3':
                    self.mapping[province(v)].extend(src)
        self.mapping = {p: sorted(set(v)) for p, v in self.mapping.items()}
        regional = load_json(Path(__file__).resolve().parents[1] / profile['regional_anchor_profile'])
        for state, overrides in regional['states'].items():
            for p, anchors in overrides.items():
                self.mapping[province(p)] = anchors
        for p, anchors in profile.get('province_anchor_overrides', {}).items():
            if province(p) not in self.province_state or any(n not in self.locations for n in anchors):
                raise ValueError('Invalid reviewed province anchor: ' + p)
            self.mapping[province(p)] = anchors
        default = fields(root((eu5 / 'in_game/map_data/default.map').read_text(encoding='utf-8-sig')))
        self.uninhabitable = {v for k in ('sea_zones', 'lakes', 'impassable_mountains', 'non_ownable') for v in strings(default[k])}
        self.repairs, self.fallbacks, self.microstates = [], [], []
        self.owners, self.countries = {}, {}

    def read(self, relative):
        relative = Path(relative).as_posix()
        path = self.game / relative
        self.inputs[relative] = digest(path)
        return path.read_text(encoding='utf-8-sig')

    def distance(self, a, b):
        ax, ay = self.points[a]
        bx, by = self.points[b]
        dx = min(abs(ax-bx), 8192-abs(ax-bx))
        return dx*dx + (ay-by)**2

    def geometry(self):
        valid = set(self.source)
        for state, provinces in sorted(self.provinces.items()):
            result = {}
            for p in provinces:
                anchors = self.mapping.get(p, [])
                if not anchors and state in self.profile['unmapped_state_anchors']:
                    anchors = self.profile['unmapped_state_anchors'][state]
                    self.mapping[p] = anchors
                    self.repairs.append({'province': p, 'state': state, 'anchors': anchors, 'rule': 'explicit_island'})
                winner = owner_vote(anchors, self.locations, valid)
                if winner:
                    result[p] = winner
                elif anchors and any(n not in self.uninhabitable for n in anchors):
                    original = self.original[state].get(p)
                    if original:
                        result[p] = 'v:' + original
                        self.fallbacks.append({'province': p, 'state': state, 'owner': original, 'rule': 'uncolonized_vanilla'})
            # Do not propagate an arbitrary source owner from another region across oceans.
            if not result:
                for p in provinces:
                    if p in self.original[state]:
                        result[p] = 'v:' + self.original[state][p]
                        self.fallbacks.append({'province': p, 'state': state, 'owner': self.original[state][p], 'rule': 'unmapped_vanilla'})
            known = sorted(result)
            for p in sorted(set(provinces) - result.keys()):
                if known:
                    neighbor = min(known, key=lambda q: (self.distance(p, q), q))
                    result[p] = result[neighbor]
                    self.repairs.append({'province': p, 'state': state, 'neighbor': neighbor,
                                         'rule': 'wasteland' if self.mapping.get(p) else 'new_target_province'})
                elif self.original[state].get(p):
                    result[p] = 'v:' + self.original[state][p]
                    self.fallbacks.append({'province': p, 'state': state, 'owner': self.original[state][p], 'rule': 'unmapped_vanilla'})
                else:
                    raise ValueError(f'No mapped or vanilla owner: {state}/{p}')
            override = self.profile.get('uncolonized_region_overrides', {}).get(state)
            if override:
                for p, owner in list(result.items()):
                    if owner.startswith('v:') and owner[2:] in override['from']:
                        result[p] = 'v:' + override['to']
                        self.repairs.append({'province': p, 'state': state, 'old_owner': owner,
                                             'new_owner': result[p], 'rule': 'uncolonized_decentralized_region'})
            self.owners[state] = result
        represented = {c for ps in self.owners.values() for c in ps.values() if not c.startswith('v:')}
        self.microstates = [{'id': i, 'tag': c['tag'], 'owned_locations': c['owned_locations'], 'population': c['population_persons']}
                            for i, c in self.source.items() if i not in represented]
        mapped_names = {n for p in self.province_state for n in self.mapping.get(p, [])}
        self.unmapped_locations = [l for l in self.audit['locations'] if str(l['owner']) in valid and l['name'] not in mapped_names]
        self.represented = represented

    def politics_model(self):
        represented = self.represented
        source_edges = [dict(e) for e in self.politics['subjects']]
        self.union_limits = []
        direct = {e['subject']: e for e in source_edges}
        for union in self.politics['international_organizations']:
            if union['type'] != 'union': continue
            if len(union['senior']) != 1:
                self.union_limits.append(dict(union, reason='no_unique_senior_partner')); continue
            senior = union['senior'][0]
            for junior in union['junior']:
                previous = direct.get(junior)
                if previous and previous['overlord'] != senior:
                    self.union_limits.append(dict(union, subject=junior, formal_overlord=previous['overlord'], reason='formal_dependency_retained_shared_ruler_only'))
                    continue
                if previous:
                    previous['original_type'] = previous['type']
                    previous['type'] = 'personal_union'
                    previous['union_id'] = union['id']
                else:
                    edge = {'overlord': senior, 'subject': junior, 'type': 'personal_union', 'union_id': union['id']}
                    source_edges.append(edge); direct[junior] = edge
        self.edges = [e for e in source_edges if e['overlord'] in represented and e['subject'] in represented]
        self.omitted_edges = [e for e in source_edges if e not in self.edges]
        involved = {e[k] for e in self.edges for k in ('overlord', 'subject')}
        subjects = {e['subject']: e for e in self.edges}
        if len(subjects) != len(self.edges):
            raise ValueError('Multiple overlords for a surviving country')
        self.tag_matches = {}
        mapping_file = self.profile.get('country_tag_mapping_file')
        if mapping_file:
            mapping = load_json(Path(__file__).resolve().parents[1] / mapping_file)
            if mapping['source_sha256'] != self.profile['source_sha256'] or mapping['target_version'] != self.profile['target_version']:
                raise ValueError('Country TAG mapping provenance mismatch')
            self.tag_matches = mapping['matches']
        self.tags = assign_country_tags(self.source, represented, self.country_defs, self.tag_matches,
                                        self.profile['country_tag_overrides'])
        for i in sorted(represented, key=int):
            src = self.politics['countries'][i]
            owned = [(s, p) for s, ps in self.owners.items() for p, c in ps.items() if c == i]
            by_state = Counter(s for s, p in owned)
            capital_name = self.location_ids.get(str(src['capital']))
            capital_matches = [(s, p) for s, p in owned if capital_name in self.mapping.get(p, [])]
            capital = sorted(capital_matches)[0][0] if capital_matches else min(by_state, key=lambda s: (-by_state[s], s))
            templates = Counter(self.original[s][p] for s, p in owned if s == capital and p in self.original[s])
            template = min(templates, key=lambda t: (-templates[t], t))
            target = fields(self.country_defs[template])
            gov = src['government']
            target_type = target.get('country_type', 'recognized')
            if target_type in ('colonial', 'company', 'decentralized'):
                target_type = 'unrecognized'
            reason = 'regional_template'
            edge = subjects.get(i)
            if edge and edge['type'] == 'colonial_nation':
                target_type, reason = 'colonial', 'source_colonial_subject'
            elif edge and edge['type'] in ('trade_company', 'state_bank'):
                target_type, reason = 'company', 'source_company'
            elif gov == 'tribe' and (target.get('country_type') == 'decentralized' or i in self.profile['decentralize_source_countries']) and i not in involved:
                target_type, reason = 'decentralized', 'tribal_government_in_native_region_without_dependencies'
            if i == '1481' and self.profile['source_sha256'] == 'd4e6bcb5f0c9d91f3d5abe73a5644b6bd99364060f3c76120c60529ad3ac6f74':
                target_type = 'recognized'
            law = 'law_colonial_administration' if target_type in ('colonial', 'company') else self.profile['government_laws'][gov]
            self.countries[self.tags[i]] = {
                'source_id': i, 'source_tag': self.source[i]['tag'], 'tag': self.tags[i],
                'capital': capital, 'source_capital': capital_name, 'capital_exact': bool(capital_matches),
                'template': template, 'country_type': target_type, 'type_reason': reason,
                'government_law': law, 'source_government': gov, 'provinces': len(owned),
                'ruler_id': src['ruler'] or src.get('regent'), 'regent_used': not src['ruler'] and bool(src.get('regent')),
            }
        # Retain vanilla native/uncolonized countries only where source territory was unowned.
        vanilla = {c[2:] for ps in self.owners.values() for c in ps.values() if c.startswith('v:')}
        for tag in sorted(vanilla):
            owned = [(s, p) for s, ps in self.owners.items() for p, c in ps.items() if c == 'v:' + tag]
            if tag in self.countries:
                self.countries[tag]['vanilla_uncolonized_provinces'] = len(owned)
                self.countries[tag]['provinces'] += len(owned)
                continue
            fs = fields(self.country_defs[tag]); by_state = Counter(s for s, p in owned)
            capital = fs['capital'] if fs.get('capital') in by_state else min(by_state, key=lambda s: (-by_state[s], s))
            self.countries[tag] = {'source_id': None, 'tag': tag, 'capital': capital, 'template': tag,
                                   'country_type': fs.get('country_type', 'recognized'), 'provinces': len(owned),
                                   'type_reason': 'uncolonized_vanilla', 'capital_exact': fs.get('capital') == capital}
            adjustment = self.profile.get('fallback_country_overrides', {}).get(tag)
            if adjustment:
                self.countries[tag].update(adjustment, type_reason='reviewed_uncolonized_decentralized_region')
        self.owners = {s: {p: (c[2:] if c.startswith('v:') else self.tags[c]) for p, c in ps.items()} for s, ps in self.owners.items()}
        self.substates = {s: Counter(ps.values()) for s, ps in self.owners.items()}
        self.transfers = {}
        for s in self.owners:
            old = set(self.original[s].values())
            for tag in old:
                overlap = Counter(self.owners[s][p] for p, t in self.original[s].items() if t == tag and p in self.owners[s])
                if not overlap:
                    raise ValueError(f'Vanilla substate has no target provinces: {s}/{tag}')
                self.transfers[s, tag] = overlap
        for edge in self.edges:
            edge['target_overlord'] = self.tags[edge['overlord']]
            edge['target_subject'] = self.tags[edge['subject']]
            kind = self.profile['subject_types'][edge['type']]
            # Vanilla puppet/tributary categories depend on recognition, not EU5 terminology.
            overlord_type = self.countries[edge['target_overlord']]['country_type']
            if kind in ('vassal', 'puppet'):
                kind = 'vassal' if overlord_type == 'unrecognized' else 'puppet'
            if kind in ('tributary', 'protectorate'):
                kind = 'tributary' if overlord_type == 'unrecognized' else 'protectorate'
            if kind == 'dominion' and self.countries[edge['target_subject']]['country_type'] != 'colonial':
                kind = 'tributary' if overlord_type == 'unrecognized' else 'protectorate'
            edge['target_type'] = kind
        for i in subjects:
            seen = set(); cursor = i
            while cursor in subjects:
                if cursor in seen:
                    raise ValueError('Subject dependency cycle')
                seen.add(cursor); cursor = subjects[cursor]['overlord']

    def transfer(self, state, old):
        weights = self.transfers[state, old]
        return min(weights, key=lambda t: (-weights[t], t))
