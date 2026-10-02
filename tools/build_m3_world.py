"""Export a complete political-map test mod, using pinned V3 economic templates.

This is the personal staging exporter, not the unfinished upstream C++ output path.
All writes go to a fresh run directory; installed games and source saves are read-only.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import uuid

from pdx_text import Object, root
from build_m2_prototype import objects, walk, strings, scalars, patch, replace_body, allocate
from m3_world import World, fields, load_json, digest, shift_birth, province

ROOT = Path(__file__).resolve().parents[1]


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def block(key, body):
    if key.endswith(' ?'):
        return f'{key[:-2]} ?= {{\n{body}\n}}\n'
    return f'{key} = {{\n{body}\n}}\n'


def entry(key, value):
    if isinstance(value, Object):
        return block(key, value.text())
    # Enums such as set_tax_level are not string literals in the game engine.
    scalar = str(value)
    token = scalar if re.fullmatch(r'[A-Za-z0-9_:.+/@-]+', scalar) else quote(scalar)
    return f'{key} = {token}\n'


def history_replace_paths(game):
    # V3 history databases load individual directories; the parent is insufficient.
    history = game / 'common/history'
    return sorted(p.relative_to(game).as_posix() for p in history.rglob('*') if p.is_dir())


def load_localization(directory):
    result = {}
    for p in sorted(directory.rglob('*.yml')):
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            m = re.match(r'^\s*([^\s:#]+):\d*\s*"(.*)"\s*(?:#.*)?$', line)
            if m:
                result[m[1]] = m[2]
    return result


class Exporter:
    def __init__(self, world):
        self.w = world
        self.outputs = {}
        self.binary_assets = {}
        self.localization = {lang: {} for lang in ('english', 'simp_chinese')}
        self.source_loc = {lang: load_localization(world.eu5 / 'main_menu/localization' / lang) for lang in self.localization}
        self.name_warnings, self.character_report, self.building_pm_conflicts = [], [], []
        self.investor_repairs = []
        self.pop_before, self.pop_after, self.build_before, self.build_after = Counter(), Counter(), Counter(), Counter()
        self.units_before, self.units_after = Counter(), Counter()
        self.ships_before, self.ships_after, self.fleet_transfers = Counter(), Counter(), []
        self.history = {}
        for category in ('countries', 'population', 'characters'):
            rows = {}
            for p in sorted((world.game / 'common/history' / category).glob('*.txt')):
                doc = root(world.read(p.relative_to(world.game)))
                for _, container in objects(doc):
                    for k, o in objects(container):
                        if k.startswith('c:'):
                            rows[k[2:]] = o
            self.history[category] = rows
        self.valid_cultures, self.valid_religions = {}, {}
        for category, dest in (('cultures', self.valid_cultures), ('religions', self.valid_religions)):
            for p in sorted((world.game / 'common' / category).glob('*.txt')):
                dest.update(dict(objects(root(world.read(p.relative_to(world.game))))))

    def write(self, path, text):
        if path in self.outputs:
            raise ValueError('Duplicate generated path: ' + path)
        self.outputs[path] = text

    def localize(self, token, lang, depth=0):
        if not token:
            return ''
        if depth > 8:
            return token
        database = self.source_loc[lang]
        value = database.get(token, self.source_loc['english'].get(token, token))
        if value == token and '.name_' in token:
            return ' '.join(self.localize(v, lang, depth+1) for v in token.split('.'))
        return re.sub(r'\$([^$|]+)(?:\|[^$]+)?\$', lambda m: self.localize(m[1], lang, depth+1), value)

    def names(self):
        for tag, c in self.w.countries.items():
            if c.get('generated_uncolonized'):
                for lang in self.localization:
                    if not hasattr(self,'target_labels'):self.target_labels={}
                    if lang not in self.target_labels:self.target_labels[lang]=load_localization(self.w.game/'localization'/lang)
                    labels=self.target_labels[lang]
                    culture=labels.get(c['culture'],self.localize(c['source_culture'],lang))
                    name=culture
                    self.localization[lang][tag]=name;self.localization[lang][tag+'_ADJ']=culture
                    c['name_'+lang]=name
                continue
            if not c['source_id']:
                for lang in self.localization:
                    if c.get('name_' + lang):
                        self.localization[lang][tag] = c['name_' + lang]
                        self.localization[lang][tag + '_ADJ'] = c['name_' + lang]
                continue
            src = self.w.politics['countries'][c['source_id']]
            from source_country_names import source_name_parts, opening_name
            custom, token, adjective = source_name_parts(src, c['source_tag'])
            for lang in self.localization:
                name = custom or self.localize(token, lang)
                if '[' in name or '$' in name:
                    self.name_warnings.append({'tag': tag, 'language': lang, 'source': name})
                    name = self.localize(src.get('definition') or c['source_tag'], lang)
                self.localization[lang][tag] = name
                self.localization[lang][tag + '_ADJ'] = name if custom else self.localize(adjective, lang)
                if self.localization[lang][tag + '_ADJ'].endswith('_ADJ'):
                    self.localization[lang][tag + '_ADJ'] = name
                c['name_' + lang] = name
                c['opening_name_' + lang] = opening_name(src,name,lang)

    def country_setup(self):
        from m3_cultures import resolve_culture, source_culture_info
        country_blocks, population_blocks, custom_defs = [], [], []
        definition_edits = defaultdict(list)
        for tag, c in sorted(self.w.countries.items()):
            template = c['template']; original = fields(self.w.country_defs[template])
            culture = strings(original['cultures'])[0]
            religion = original.get('religion', fields(self.valid_cultures[culture]).get('religion'))
            src = self.w.politics['countries'].get(c['source_id'])
            if src:
                c['source_culture'] = src['culture']; c['source_religion'] = src['religion']
                culture, c['culture_mapping'] = resolve_culture(src['culture'], self.w.profile, self.valid_cultures)
                c['source_culture_details'] = source_culture_info(self, src['culture'])
                c['source_accepted_cultures'] = src.get('accepted_cultures', [])
                c['source_tolerated_cultures'] = src.get('tolerated_cultures', [])
                candidate = self.w.profile['religion_aliases'].get(src['religion'], src['religion'])
                if candidate in self.valid_religions:
                    religion = candidate
                    c['religion_mapping'] = 'source_exact' if candidate == src['religion'] else 'explicit_alias'
                else:
                    raise ValueError('Unreviewed source religion: ' + str(src['religion']))
            if c.get('generated_uncolonized'):
                culture=c['culture'];religion=c['religion']
                if culture not in self.valid_cultures or religion not in self.valid_religions:
                    raise ValueError('Uncolonized identity definitions missing; generate identity assets before political export: '+tag)
            c['culture'] = culture; c['religion'] = religion
            c['cultures'] = [culture] if src or c.get('generated_uncolonized') else strings(original['cultures'])
            color = ' '.join(src['color']) if src and len(src['color']) == 3 else '100 130 160'
            tier = original.get('tier', 'principality')
            body = f'color = {{ {color} }}\ncountry_type = {c["country_type"]}\ntier = {tier}\ncultures = {{ {culture} }}\ncapital = {c["capital"]}\n'
            if religion:
                body += f'religion = {religion}\n'
            if tag in self.w.country_defs:
                old = self.w.country_defs[tag]
                if not src:
                    # Keep the vanilla fallback definition, only relocate its capital if necessary.
                    body = re.sub(r'\bcapital\s*=\s*\w+', 'capital = ' + c['capital'], old.text())
                    body = re.sub(r'\bcountry_type\s*=\s*\w+', 'country_type = ' + c['country_type'], body)
                definition_edits[self.w.definition_files[tag]].append(replace_body(old, '\n' + body))
            else:
                custom_defs.append(block(tag, body))
            country = self.history['countries'].get(template)
            setup = []
            if country:
                for k, v in country.entries():
                    if c.get('generated_uncolonized') and k and k.startswith('effect_native_conscription_'):
                        c.setdefault('excluded_template_military_effects',[]).append(k)
                        continue
                    if k and (k.startswith(('effect_starting_technology_', 'effect_starting_politics_', 'effect_native_conscription_'))
                              or k in ('activate_law', 'add_technology_researched', 'set_tax_level', 'add_taxed_goods',
                                       'set_institution_investment_level', 'set_import_tariff_level', 'set_export_tariff_level')):
                        setup.append(entry(k, v))
            if not any('effect_starting_technology_' in s for s in setup):
                setup.insert(0, 'effect_starting_technology_tier_5_tech = yes\n')
            if not any('effect_starting_politics_' in s for s in setup):
                setup.insert(0, 'effect_starting_politics_traditional = yes\n')
            if src:
                policies = {k: dict(v).get('object') for k, v in src['laws']}
                power = 'law_autocracy'
                if src['government'] == 'republic':
                    power = 'law_oligarchy'
                    if policies.get('republican_electorate_law') in ('dynastic_rule_policy',) or policies.get('republican_power_law') == 'absolute_presidential_power_policy':
                        power = 'law_autocracy'
                    if src['succession'] == 'republic_4_year_terms':
                        power = 'law_landed_voting'
                c['power_law'] = power
                # All source constitutional overrides occur after the regional template.
                setup += ['add_technology_researched = democracy\n', f'activate_law = law_type:{c["government_law"]}\n',
                          f'activate_law = law_type:{power}\n']
                ig = 'ig_devout' if src['government'] == 'theocracy' else ('ig_intelligentsia' if src['government'] == 'republic' else 'ig_landowners')
                if c['country_type'] in ('colonial', 'company'):
                    ig = 'ig_armed_forces'
                c['ruler_interest_group'] = ig
                setup.append(block('ig:' + ig + ' ?', 'add_ruling_interest_group = yes'))
            country_blocks.append(block('c:' + tag + ' ?', ''.join(setup)))
            pop = self.history['population'].get(template)
            effects = [entry(k, v) for k, v in pop.entries() if k and k.startswith(('effect_starting_pop_wealth_', 'effect_starting_pop_literacy_'))] if pop else []
            if not effects:
                effects = ['effect_starting_pop_wealth_medium = yes\neffect_starting_pop_literacy_very_low = yes\n']
            population_blocks.append(block('c:' + tag + ' ?', ''.join(effects)))
        for file, edits in definition_edits.items():
            self.write(file, patch(self.w.read(file), edits))
        self.write('common/country_definitions/zz_eu5_world.txt', ''.join(custom_defs))
        self.write('common/history/countries/00_eu5_world.txt', block('COUNTRIES', ''.join(country_blocks)))
        self.write('common/history/population/00_eu5_world.txt', block('POPULATION', ''.join(population_blocks)))

    def state_setup(self):
        states = []
        for state, owners in sorted(self.w.owners.items()):
            groups = defaultdict(list)
            for p, tag in owners.items():
                groups[tag].append(p)
            body = []
            for tag, provinces in sorted(groups.items()):
                kind = self.w.countries[tag]['country_type']
                status = 'unincorporated' if kind in ('decentralized', 'colonial', 'company') else 'incorporated'
                body.append(block('create_state', f'country = c:{tag}\nowned_provinces = {{ {" ".join(sorted(provinces))} }}\nstate_type = {status}'))
            body.extend(entry(k, v) for k, v in self.w.states[state].entries() if k == 'add_homeland')
            states.append(block('s:' + state, ''.join(body)))
        self.write('common/history/states/00_eu5_world.txt', block('STATES', ''.join(states)))

    def pops(self):
        result = defaultdict(lambda: defaultdict(list))
        for file in sorted((self.w.game / 'common/history/pops').glob('*.txt')):
            container = fields(root(self.w.read(file.relative_to(self.w.game))))['POPS']
            for statekey, state in objects(container):
                s = statekey.removeprefix('s:')
                for subkey, sub in objects(state):
                    old = subkey.removeprefix('region_state:')
                    for k, pop in objects(sub):
                        if k != 'create_pop':
                            raise ValueError('Unexpected template pop operation')
                        f = fields(pop); amount = int(f['size'])
                        identity = (s, f.get('culture'), f.get('religion'))
                        self.pop_before[identity] += amount
                        for tag, size in allocate(amount, self.w.transfers[s, old]).items():
                            if size:
                                body = re.sub(r'\bsize\s*=\s*\d+', 'size = ' + str(size), pop.text())
                                result[s][tag].append(block('create_pop', body))
                                self.pop_after[identity] += size
        self.write('common/history/pops/00_eu5_world.txt', block('POPS', ''.join(block('s:' + s, ''.join(block('region_state:' + t, ''.join(pops)) for t, pops in sorted(rows.items()))) for s, rows in sorted(result.items()))))
        self.pop_states = {(s, t) for s, ts in result.items() for t in ts}

    def investor_references(self, body, state, old):
        edits = []
        for _, obj in walk(root(body)):
            data = scalars(obj)
            investor = data.get('country', '').removeprefix('c:')
            if investor and 'levels' in data:
                region = data.get('region', state)
                if (region, investor) not in self.w.transfers:
                    capital = fields(self.w.country_defs[investor]).get('capital')
                    if (capital, investor) not in self.w.transfers:
                        raise ValueError(f'Unresolved investor: {region}/{investor}')
                    self.investor_repairs.append({'country': investor, 'from_region': region, 'to_region': capital, 'building_state': state})
                    region = capital
                new = self.w.transfer(region, investor)
                replaced = re.sub(r'(\bcountry\s*=\s*)"?c:' + re.escape(investor) + r'"?', r'\g<1>c:' + new, obj.text())
                if 'region' in data:
                    replaced = re.sub(r'(\bregion\s*=\s*)"?STATE_\w+"?', r'\g<1>' + region, replaced)
                edits.append(replace_body(obj, replaced))
        return patch(body, edits)

    def buildings(self):
        grouped = defaultdict(list)
        def collect(node, state=None, country=None, guards=()):
            for k, obj in objects(node):
                if k.startswith('s:'):
                    yield from collect(obj, k[2:], country, guards)
                elif k.startswith('region_state:'):
                    yield from collect(obj, state, k.removeprefix('region_state:'), guards)
                elif k == 'if':
                    condition = fields(obj)['limit'].text()
                    yield from collect(obj, state, country, guards + (condition,))
                elif k == 'limit':
                    continue
                elif k == 'create_building' and state and country:
                    yield state, country, obj, guards
                else:
                    raise ValueError('Unexpected building scope: ' + k)
        for file in sorted((self.w.game / 'common/history/buildings').glob('*.txt')):
            container = fields(root(self.w.read(file.relative_to(self.w.game))))['BUILDINGS']
            for s, old, building, guards in collect(container):
                new = self.w.transfer(s, old)
                f = fields(building); kind = f['building']
                body = self.investor_references(building.text(), s, old)
                grouped[s, new, kind, guards].append(body)
                level = sum(int(scalars(o)['levels']) for _, o in walk(building) if 'levels' in scalars(o))
                level += int(f.get('level', 0))
                self.build_before[s, kind] += level
        result = defaultdict(lambda: defaultdict(list))
        for (state, tag, kind, guards), bodies in sorted(grouped.items()):
            ownership, pms, levels, reserves, subsidized = [], [], 0, '1', None
            for body in bodies:
                for k, v in root(body).entries():
                    if k == 'add_ownership':
                        ownership.extend(entry(a, b) for a, b in v.entries())
                    elif k == 'level': levels += int(v)
                    elif k == 'activate_production_methods': pms.append(v.text())
                    elif k == 'reserves': reserves = v
                    elif k == 'subsidized': subsidized = v
            body = f'building = {kind}\n'
            if ownership: body += block('add_ownership', ''.join(ownership))
            if levels: body += f'level = {levels}\n'
            if pms:
                body += block('activate_production_methods', pms[0])
                if len({tuple(strings(root(pm))) for pm in pms}) > 1:
                    self.building_pm_conflicts.append({'state': state, 'country': tag, 'building': kind, 'selected': pms[0].strip()})
            body += f'reserves = {reserves}\n'
            if subsidized: body += f'subsidized = {subsidized}\n'
            rendered = block('create_building', body)
            for guard in reversed(guards):
                rendered = block('if', block('limit', guard) + rendered)
            result[state][tag].append(rendered)
            self.build_after[state, kind] += levels + sum(int(scalars(o)['levels']) for _, o in walk(root(body)) if 'levels' in scalars(o))
        self.write('common/history/buildings/00_eu5_world.txt', block('BUILDINGS', ''.join(block('s:' + s, ''.join(block('region_state:' + t, ''.join(bs)) for t, bs in sorted(rows.items()))) for s, rows in sorted(result.items()))))

    def military(self):
        result = defaultdict(list)
        regions = {}
        for p in sorted((self.w.game / 'common/strategic_regions').glob('*.txt')):
            for key, region in objects(root(self.w.read(p.relative_to(self.w.game)))):
                f = fields(region)
                if 'states' in f:
                    for state in strings(f['states']): regions[state] = key
        fleet_scopes, pending_ships = {}, []
        for file in sorted((self.w.game / 'common/history/military_formations').glob('*.txt')):
            doc = fields(root(self.w.read(file.relative_to(self.w.game))))
            if not doc: continue
            container = doc['MILITARY_FORMATIONS']
            for key, country in objects(container):
                old = key.removeprefix('c:')
                for k, formation in objects(country):
                    if k == 'create_ship':
                        pending_ships.append(fields(formation)); continue
                    if k == 'create_character' or k == 'activate_production_method' or k.startswith('scope:'):
                        continue # Old generals and their named assignments belong to the vanilla timeline.
                    if k != 'create_military_formation':
                        raise ValueError('Unexpected military operation: ' + k)
                    f = fields(formation); grouped = defaultdict(list)
                    if f['type'] == 'fleet':
                        candidates = [s for s in self.w.states if old in self.w.original[s].values() and 'naval_exit_id' in fields(self.w.defs[s])]
                        local = [s for s in candidates if regions[s] == f['hq_region'].removeprefix('sr:')]
                        pool = local or candidates
                        if not pool: raise ValueError('No coastal template state for fleet: ' + old)
                        s = min(pool, key=lambda s: (-sum(t == old for t in self.w.original[s].values()), s))
                        port = province(fields(self.w.defs[s])['port'])
                        tag = self.w.owners[s][port]
                        hq = 'sr:' + regions[s]
                        ships = [o for ck, o in objects(formation) if ck == 'ship']
                        body = f'type = fleet\nhq_region = {hq}\n' + ''.join(block('ship', o.text()) for o in ships)
                        scope = f.get('save_scope_as', f.get('save_temporary_scope_as'))
                        if scope:
                            new_scope = 'eu5_' + scope
                            fleet_scopes[scope] = (tag, new_scope)
                            body += f'save_scope_as = {new_scope}\n'
                        result[tag].append(block('create_military_formation', body))
                        self.fleet_transfers.append({'old_country': old, 'new_country': tag, 'coastal_state': s, 'hq': hq})
                        for ship in ships:
                            sf = fields(ship)
                            self.ships_before[sf['type']] += int(sf.get('count', 1))
                            self.ships_after[sf['type']] += int(sf.get('count', 1))
                        continue
                    for ck, unit in objects(formation):
                        if ck != 'combat_unit': continue
                        u = fields(unit); s = u['state_region'].removeprefix('s:')
                        tag = self.w.transfer(s, old)
                        grouped[tag].append(block('combat_unit', unit.text()))
                        self.units_before[f['type'], s, u['type']] += int(u['count'])
                        self.units_after[f['type'], s, u['type']] += int(u['count'])
                    for tag, units in grouped.items():
                        result[tag].append(block('create_military_formation', f'type = {f["type"]}\nhq_region = {f["hq_region"]}\n' + ''.join(units)))
        for ship in pending_ships:
            tag, scope = fleet_scopes[ship['fleet'].removeprefix('scope:')]
            body = f'type = {ship["type"]}\nfleet = scope:{scope}\n'
            if ship.get('name'): body += 'name = ' + quote(ship['name']) + '\n'
            result[tag].append(block('create_ship', body))
            self.ships_before[ship['type']] += 1
            self.ships_after[ship['type']] += 1
        self.write('common/history/military_formations/00_eu5_world.txt', block('MILITARY_FORMATIONS', ''.join(block('c:' + tag + ' ?', ''.join(forms)) for tag, forms in sorted(result.items()))))

    def characters(self):
        blocks = []
        self.shared_union_rulers = []
        union_subjects = {e['target_subject']: e for e in self.w.edges if e['target_type'] == 'personal_union'}
        for tag, c in sorted(self.w.countries.items()):
            if c['country_type'] == 'decentralized':
                continue
            if not c['source_id']:
                # Vanilla uncolonized fallback countries retain their ordinary historical roster.
                original = self.history['characters'].get(tag)
                if original:
                    clean = []
                    for k, o in objects(original):
                        if k == 'create_character' and 'template' in fields(o):
                            clean.append(block(k, 'template = ' + fields(o)['template']))
                    blocks.append(block('c:' + tag + ' ?', ''.join(clean)))
                continue
            person = self.w.politics['characters'].get(c['ruler_id'])
            if not person or not person['alive']:
                raise ValueError('Missing live ruler or regent: ' + tag)
            first = 'EU5_FIRST_' + c['ruler_id']; last = 'EU5_LAST_' + c['ruler_id']
            for lang in self.localization:
                self.localization[lang][first] = self.localize(person['first_name'], lang)
                self.localization[lang][last] = self.localize(person['last_name'] or person['dynasty'], lang)
            birth = shift_birth(person['birth_date'], self.w.profile['source_date'], self.w.profile['start_date'])
            from m3_cultures import resolve_culture
            culture, culture_mode = resolve_culture(person['culture'], self.w.profile, self.valid_cultures)
            body = f'first_name = {first}\nlast_name = {last}\nhistorical = yes\nruler = yes\nculture = {culture}\nbirth_date = {birth}\nhome_region = {c["capital"]}\ninterest_group = {c["ruler_interest_group"]}\nideology = ideology_moderate\ntrait_generation = {{ }}\n'
            if person['female'] == 'yes': body += 'female = yes\n'
            if tag in union_subjects:
                self.shared_union_rulers.append({'subject': tag, 'overlord': union_subjects[tag]['target_overlord'], 'source_ruler': c['ruler_id']})
            else:
                blocks.append(block('c:' + tag + ' ?', block('create_character', body)))
            self.character_report.append({'tag': tag, 'source_id': c['ruler_id'], 'first_name': self.localization['simp_chinese'][first],
                                          'last_name': self.localization['simp_chinese'][last], 'source_birth': person['birth_date'],
                                          'target_birth': birth, 'regent_used': c['regent_used'], 'culture': culture,
                                          'source_culture': person['culture'], 'culture_mapping': culture_mode})
        self.write('common/history/characters/00_eu5_world.txt', block('CHARACTERS', ''.join(blocks)))

    def diplomacy(self):
        rows = defaultdict(list)
        for e in self.w.edges:
            rows[e['target_overlord']].append(block('create_diplomatic_pact', f'country = c:{e["target_subject"]}\ntype = {e["target_type"]}'))
        self.vanilla_fallback_subjects = []
        original = fields(root(self.w.read('common/history/diplomacy/00_subject_relationships.txt')))['DIPLOMACY']
        subject_definitions = fields(root(self.w.read('common/subject_types/00_subject_types.txt')))
        subject_actions = {fields(v)['diplomatic_action'] for k, v in subject_definitions.items() if isinstance(v, Object)}
        for key, country in objects(original):
            overlord = key[2:]
            if overlord not in self.w.countries: continue
            for k, pact in objects(country):
                if k != 'create_diplomatic_pact': continue
                f = fields(pact); subject = f['country'][2:]
                if subject in self.w.countries and self.w.countries[subject]['source_id'] is None and f['type'] in subject_actions:
                    rows[overlord].append(block(k, pact.text()))
                    self.vanilla_fallback_subjects.append({'target_overlord': overlord, 'target_subject': subject, 'target_type': f['type']})
        self.write('common/history/diplomacy/00_eu5_subjects.txt', block('DIPLOMACY', ''.join(block('c:' + tag + ' ?', ''.join(pacts)) for tag, pacts in sorted(rows.items()))))
        # EU5 permits multilevel vassal trees. Preserve them instead of flattening to the top overlord.
        path = 'common/subject_types/00_subject_types.txt'
        text = self.w.read(path); edits = []
        # It is the intermediate country's own subject type whose permission matters.
        intermediate = {e['overlord'] for e in self.w.edges} & {e['subject'] for e in self.w.edges}
        kinds = {e['target_type'] for e in self.w.edges if e['subject'] in intermediate}
        self.nested_subject_types = []
        for key, obj in objects(root(text)):
            if key.removeprefix('subject_type_') in kinds and fields(obj).get('can_have_subjects') == 'no':
                edits.append(replace_body(obj, re.sub(r'can_have_subjects\s*=\s*no', 'can_have_subjects = yes', obj.text())))
                self.nested_subject_types.append(key)
        if edits: self.write(path, patch(text, edits))

    def flags(self):
        from m3_flags import FlagExporter
        FlagExporter(self.w.eu5).export(self)

    def organizations(self):
        from m3_organizations import export_organizations
        export_organizations(self)

    def cultures(self):
        from m3_cultures import prepare_cultures, preserve_source_names
        prepare_cultures(self)
        preserve_source_names(self)

    def finish(self):
        from regional_claims import export as export_regional_claims
        export_regional_claims(self)
        # Replace each history database explicitly, including databases we leave empty.
        self.write('common/history/global/00_eu5_world.txt', block('GLOBAL', '# Political map test: original country-specific journals and wars are intentionally omitted.'))
        for lang, entries in self.localization.items():
            # Existing country tags need the engine's explicit localization override path.
            existing = {key: value for key, value in entries.items()
                        if key.removesuffix('_ADJ') in self.w.country_defs}
            new = {key: value for key, value in entries.items() if key not in existing}
            for directory, values in ((lang, new), ('replace/' + lang, existing)):
                if values:
                    self.write(f'localization/{directory}/eu5_world_l_{lang}.yml', f'l_{lang}:\n' + ''.join(f' {key}:0 {quote(value)}\n' for key, value in sorted(values.items())))
        self.validate()
        metadata = {'name': 'EU5 M3 - World 1780 - Political Map TEST', 'id': 'eu5-personal-m3-world', 'version': '0.3.11',
                    'supported_game_version': '1.13.11', 'short_description': 'EU5 1780 world, governments, rulers, colonies and subjects. V3 economic templates.',
                    'tags': ['Alternative History'], 'relationships': [],
                    'game_custom_data': {'multiplayer_synchronized': True, 'replace_paths': history_replace_paths(self.w.game)}}
        self.write('.metadata/metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))

    def validate(self):
        from m3_shogunate_law import assert_union_laws, COUNTRIES
        self.personal_union_law_checks = assert_union_laws(
            self.outputs[COUNTRIES], self.w.edges + self.vanilla_fallback_subjects)
        if self.pop_before != self.pop_after: raise ValueError('Template population conservation failed')
        if self.build_before != self.build_after: raise ValueError('Template building levels changed')
        if self.units_before != self.units_after: raise ValueError('Template unit conservation failed')
        if self.ships_before != self.ships_after: raise ValueError('Template ship conservation failed')
        missing_pop = {(s, t) for s, ts in self.w.substates.items() for t in ts} - self.pop_states
        if missing_pop: raise ValueError('Target substates without template population: ' + str(sorted(missing_pop)))
        for tag, c in self.w.countries.items():
            if tag not in self.w.substates[c['capital']]: raise ValueError('Unowned country capital')
        subject_defs = dict(objects(root(self.w.read('common/subject_types/00_subject_types.txt'))))
        for e in self.w.edges + self.vanilla_fallback_subjects:
            rules = fields(subject_defs['subject_type_' + e['target_type']])
            for field, who in (('valid_overlord_country_types', 'target_overlord'), ('valid_subject_country_types', 'target_subject')):
                if self.w.countries[e[who]]['country_type'] not in strings(rules[field]):
                    raise ValueError('Incompatible subject country type: ' + str(e))
        # Read output back, validate scopes/references, not just the objects used to write it.
        province_owners = {}
        for s, o in objects(fields(root(self.outputs['common/history/states/00_eu5_world.txt']))['STATES']):
            state = s[2:]
            for key, item in objects(o):
                if key != 'create_state': continue
                f = fields(item); tag = f['country'][2:]
                for p in strings(f['owned_provinces']):
                    if p in province_owners: raise ValueError('Duplicate output province: ' + p)
                    if self.w.province_state[p] != state: raise ValueError('Wrong state for province')
                    province_owners[p] = tag
        if set(province_owners) != set(self.w.province_state): raise ValueError('Incomplete target land coverage')
        for path, text in self.outputs.items():
            if not path.startswith('common/history/') or not path.endswith('.txt'): continue
            # Force a full recursive parse, catching malformed generated scripts.
            for key, obj in walk(root(text)):
                data = scalars(obj)
                if key and key.startswith('c:') and key[2:] not in self.w.countries:
                    raise ValueError('Unknown country scope: ' + key)
                if 'region' in data and 'country' in data and 'levels' in data:
                    if data['country'][2:] not in self.w.substates[data['region']]:
                        raise ValueError('Investor has no state: ' + str(data))

    def report(self):
        return {'schema': 1, 'status': 'offline_validated_game_test_pending', 'source_sha256': self.w.profile['source_sha256'],
                'source_date': self.w.profile['source_date'], 'target_version': '1.13.11', 'start_date': self.w.profile['start_date'],
                'scope': self.w.profile['notes'], 'mapping_sha256': self.w.mapping_sha256,
                'countries': self.w.countries, 'subjects': self.w.edges, 'rulers': self.character_report,
                'country_tag_matches': {i: row for i, row in self.w.tag_matches.items() if i in self.w.represented},
                'flags': self.flag_report,
                'organizations': self.organization_report,
                'treaties': self.treaty_report,
                'custom_cultures': self.custom_culture_report,
                'source_culture_inputs_sha256': self.source_culture_inputs,
                'source_name_overrides': self.source_name_overrides,
                'flag_asset_sources': {p: {'source': str(src), 'sha256': digest(src)} for p, src in self.binary_assets.items()},
                'omitted_countries': self.w.microstates, 'omitted_subjects': self.w.omitted_edges,
                'union_engine_limits': self.w.union_limits, 'shared_union_rulers': self.shared_union_rulers,
                'personal_union_law_checks': self.personal_union_law_checks,
                'regional_claims': self.regional_claims_report,
                'vanilla_fallback_subjects': self.vanilla_fallback_subjects,
                'unmapped_source_locations': self.w.unmapped_locations, 'map_repairs': self.w.repairs,
                'vanilla_fallbacks': self.w.fallbacks, 'name_warnings': self.name_warnings,
                'uncolonized_tribes': getattr(self.w,'uncolonized_report',None),
                'terrain_finalization': getattr(self.w,'terrain_finalization',None),
                'frontier_finalization': getattr(self.w,'frontier_finalization',None),
                'nested_subject_type_changes': self.nested_subject_types, 'building_pm_conflicts': self.building_pm_conflicts,
                'template_investor_repairs': self.investor_repairs,
                'fleet_transfers': self.fleet_transfers,
                'validation': {'land_states': len(self.w.owners), 'land_provinces': len(self.w.province_state),
                               'source_countries_with_land': len(self.w.source), 'represented_source_countries': len(self.w.represented),
                               'exported_countries': len(self.w.countries), 'subject_edges': len(self.w.edges),
                               'template_population_preserved': sum(self.pop_after.values()),
                               'template_building_levels_preserved': sum(self.build_after.values()),
                               'template_combat_units_preserved': sum(self.units_after.values()),
                               'template_ships_preserved': sum(self.ships_after.values())}, 'target_inputs_sha256': self.w.inputs}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--audit', type=Path, required=True)
    p.add_argument('--politics', type=Path, required=True)
    p.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    p.add_argument('--eu5', type=Path, default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--profile', type=Path, default=ROOT / 'config/personal/m3_world.json')
    p.add_argument('--out-root', type=Path, default=ROOT / '.local/m3/runs')
    p.add_argument('--uncolonized-population-source',type=Path,help='Validated source population ledger; enables source-native decentralized countries')
    p.add_argument('--uncolonized-culture-map',type=Path,help='Reviewed source_culture/target_culture CSV')
    p.add_argument('--uncolonized-religion-map',type=Path,help='Reviewed source_religion/target_religion CSV')
    p.add_argument('--uncolonized-population-stage',type=Path,help='Reviewed province population geography; preserve prior location corrections')
    p.add_argument('--uncolonized-policy',type=Path,default=ROOT/'config/personal/uncolonized_tribes.json')
    a = p.parse_args()
    launcher = load_json(a.game.parent / 'launcher/launcher-settings.json')
    if '1.13.11' not in str(launcher.get('rawVersion')): raise ValueError('Unsupported installed V3 version')
    w = World(a.game, a.eu5, load_json(a.audit), load_json(a.politics), load_json(a.profile), ROOT / '.local/m3/cache')
    w.geometry(); w.politics_model()
    native_args=(a.uncolonized_population_source,a.uncolonized_culture_map,a.uncolonized_religion_map)
    if any(native_args) or load_json(a.uncolonized_policy).get('enabled'):
        if not all(native_args):raise ValueError('Uncolonized conversion requires population evidence and both reviewed identity crosswalks')
        from m3_uncolonized import prepare
        prepare(w,*native_args,a.uncolonized_policy,ROOT/'.local/m3/cache/tribal_land_edges.json',a.uncolonized_population_stage)
    from m3_terrain_finalization import prepare as finalize_terrain
    finalize_terrain(w,a.uncolonized_population_stage)
    if a.uncolonized_population_source and a.uncolonized_population_stage:
        from m3_colonial_frontier import prepare as finalize_frontier
        # Source identities are normally populated by Exporter.cultures(),
        # which runs later. Colonial evidence needs the source primary culture
        # now; do not infer it from a V3 template or regional migrant label.
        for country in w.countries.values():
            if country.get('source_id'):
                country['source_culture']=w.politics['countries'][country['source_id']]['culture']
        finalize_frontier(w,a.uncolonized_population_source,a.uncolonized_population_stage,
                          ROOT/'config/personal/m3_frontier_review.json',a.uncolonized_culture_map)
    exporter = Exporter(w)
    for method in ('names', 'cultures', 'country_setup', 'state_setup', 'pops', 'buildings', 'military', 'characters', 'diplomacy', 'organizations', 'flags', 'finish'):
        print(method, flush=True); getattr(exporter, method)()
    run = a.out_root / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    mod = run / 'eu5_m3_world_1780'; mod.mkdir(parents=True, exist_ok=False)
    for relative, text in exporter.outputs.items():
        path = mod / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8-sig' if path.suffix in ('.yml', '.txt') else 'utf-8')
    for relative, source in exporter.binary_assets.items():
        path = mod / relative; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, path)
    report = exporter.report()
    report['mod_directory'] = str(mod.resolve())
    report['output_sha256'] = {str(p.relative_to(mod)): digest(p) for p in mod.rglob('*') if p.is_file()}
    report['politics_sha256'] = digest(a.politics); report['audit_sha256'] = digest(a.audit); report['profile_sha256'] = digest(a.profile)
    (run / 'conversion_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (run / 'province_owners.json').write_text(json.dumps(w.owners, indent=2), encoding='utf-8')
    print(json.dumps({'run': str(run), 'validation': report['validation']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
