"""Local M2 format prototype: EU5 territorial anchors, V3 1.13.11 setup templates.

The C++ importer remains authoritative. This staging tool consumes its validated
P001 report; it does not claim population/economy conversion or in-game acceptance.
Only changed vanilla files are shadowed, at their original relative paths.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import uuid

from pdx_text import Object, root
from collect_m0_baseline import digest

ROOT = Path(__file__).resolve().parents[1]


def objects(obj):
    return [(key, value) for key, value in obj.entries() if isinstance(value, Object)]


def walk(obj):
    for key, value in objects(obj):
        yield key, value
        yield from walk(value)


def patch(text, changes):
    """Apply disjoint source-span edits, preserving all unrelated text."""
    changes = sorted(changes)
    last = 0
    parts = []
    for start, end, replacement in changes:
        if not 0 <= start <= end <= len(text) or start < last:
            raise ValueError('Overlapping or invalid script edits')
        parts.extend([text[last:start], replacement])
        last = end
    return ''.join(parts) + text[last:]


def replace_body(obj, body):
    return obj.start, obj.end, body


def whole_entry(key, obj):
    prefix_start = max(0, obj.start - len(key) - 100)
    match = re.search(re.escape(key) + r'\s*\??=\s*\{$', obj.source[prefix_start:obj.start])
    if not match:
        raise ValueError('Cannot locate entry start: ' + key)
    return prefix_start + match.start(), obj.end + 1


def scalars(obj):
    return {k: v for k, v in obj.entries() if k is not None and not isinstance(v, Object)}


def strings(obj):
    values = list(obj.entries())
    if any(k is not None or isinstance(v, Object) for k, v in values):
        raise ValueError('Expected scalar list')
    return [v for k, v in values]


def allocate(amount, weights):
    """Deterministic largest-remainder split of existing integer template pops."""
    if amount < 0 or not weights or any(v <= 0 for v in weights.values()):
        raise ValueError('Invalid population allocation')
    total = sum(weights.values())
    parts = {k: amount * v // total for k, v in sorted(weights.items())}
    order = sorted(weights, key=lambda k: (-(amount * weights[k] % total), k))
    for key in order[:amount - sum(parts.values())]:
        parts[key] += 1
    return parts


def replace_country(text, old, new):
    return re.sub(r'(?<![\w:])c:' + re.escape(old) + r'(?![\w])', 'c:' + new, text)


def remap_local_investors(text, state, old, new):
    changes = []
    for _, item in walk(root(text)):
        data = scalars(item)
        if data.get('country') == 'c:' + old and data.get('region', state) == state:
            changes.append(replace_body(item, replace_country(item.text(), old, new)))
    return patch(text, changes)


def state_owners(state, strict=True):
    result = {}
    for key, item in objects(state):
        if key != 'create_state':
            continue
        fields = item.fields()
        country = fields['country'].removeprefix('c:')
        for province in strings(fields['owned_provinces']):
            if province in result and strict:
                raise ValueError('Duplicate province ownership: ' + province)
            result[province] = country
    return result


def resolve_mapping(profile, audit, definitions):
    countries = {c['id']: c['tag'] for c in audit['countries']}
    locations = {loc['name']: loc for loc in audit['locations']}
    resolved = {}
    for state, province_map in profile['states'].items():
        expected = set(strings(definitions[state].fields()['provinces']))
        if set(province_map) != expected:
            raise ValueError('Mapping must cover every province exactly: ' + state)
        resolved[state] = {}
        for province, anchors in province_map.items():
            if not anchors:
                raise ValueError('Empty territorial anchor')
            owners = {countries.get(locations[name]['owner']) for name in anchors}
            if len(owners) != 1 or next(iter(owners)) not in profile['country_tags']:
                raise ValueError(f'Mixed/unmapped EU5 ownership at {state}/{province}: {owners}')
            resolved[state][province] = profile['country_tags'][next(iter(owners))]
    return resolved


class Prototype:
    def __init__(self, game, profile, audit):
        self.game, self.profile, self.audit = game, profile, audit
        self.inputs, self.outputs, self.changes = {}, {}, []
        self.definitions = {}
        for path in sorted((game / 'map_data/state_regions').glob('*.txt')):
            for key, obj in objects(root(self.read(path.relative_to(game)))):
                if key in profile['states']:
                    if key in self.definitions:
                        raise ValueError('Duplicate target state definition')
                    self.definitions[key] = obj
        self.owners = resolve_mapping(profile, audit, self.definitions)
        self.original = {}
        self.pop_before = Counter()
        self.pop_after = Counter()
        self.moved_units = []

    def read(self, relative):
        relative = Path(relative).as_posix()
        path = self.game / relative
        text = path.read_text(encoding='utf-8-sig')
        self.inputs[relative] = digest(path)
        return text

    def write_changed(self, relative, before, after):
        if before != after:
            self.outputs[Path(relative).as_posix()] = after

    def states(self):
        relative = 'common/history/states/00_states.txt'
        text = self.read(relative)
        container = root(text).fields()['STATES']
        changes = []
        for key, obj in objects(container):
            state = key.removeprefix('s:')
            if state not in self.owners:
                continue
            self.original[state] = state_owners(obj)
            if set(self.original[state]) != set(self.owners[state]):
                raise ValueError('State history and map definition differ')
            groups = defaultdict(list)
            for province, owner in self.owners[state].items():
                groups[owner].append(province)
            body = '\n'
            for owner, provinces in sorted(groups.items()):
                body += f'\t\tcreate_state = {{ country = c:{owner} owned_provinces = {{ {" ".join(sorted(provinces))} }} }}\n'
            for field, value in obj.entries():
                if field == 'add_homeland':
                    body += f'\t\tadd_homeland = {value}\n'
                elif field != 'create_state':
                    raise ValueError('Unhandled state-history field: ' + str(field))
            changes.append(replace_body(obj, body + '\t'))
        if set(self.original) != set(self.owners):
            raise ValueError('Missing source state history')
        self.write_changed(relative, text, patch(text, changes))

    def destinations(self, state, old):
        return Counter(self.owners[state][p] for p, c in self.original[state].items() if c == old)

    def pops(self):
        for path in sorted((self.game / 'common/history/pops').glob('*.txt')):
            relative = path.relative_to(self.game)
            text = self.read(relative)
            changes = []
            for key, state_obj in objects(root(text).fields()['POPS']):
                state = key.removeprefix('s:')
                if state not in self.owners:
                    continue
                groups = defaultdict(list)
                for subkey, substate in objects(state_obj):
                    old = subkey.removeprefix('region_state:')
                    weights = self.destinations(state, old)
                    for popkey, pop in objects(substate):
                        if popkey != 'create_pop':
                            raise ValueError('Unexpected pop initializer')
                        data = pop.fields()
                        amount = int(data['size'])
                        identity = (state, data['culture'], data.get('religion', '<culture_default>'))
                        self.pop_before[identity] += amount
                        for country, share in allocate(amount, weights).items():
                            if share:
                                body, count = re.subn(r'\bsize\s*=\s*\d+', 'size = ' + str(share), pop.text())
                                if count != 1:
                                    raise ValueError('Ambiguous pop size')
                                groups[country].append('create_pop = {' + body + '}')
                                self.pop_after[identity] += share
                body = '\n' + ''.join(f'\t\tregion_state:{tag} = {{\n' + '\n'.join(rows) + '\n\t\t}\n' for tag, rows in sorted(groups.items()))
                changes.append(replace_body(state_obj, body + '\t'))
            self.write_changed(relative, text, patch(text, changes))
        if not self.pop_before or self.pop_before != self.pop_after:
            raise ValueError('Template population conservation failed')

    def economic_owner(self, state, old):
        weights = self.destinations(state, old)
        return sorted(weights, key=lambda c: (-weights[c], c))[0]

    def buildings(self):
        for path in sorted((self.game / 'common/history/buildings').glob('*.txt')):
            relative = path.relative_to(self.game)
            text = self.read(relative)
            changes = []
            for key, state_obj in objects(root(text).fields()['BUILDINGS']):
                state = key.removeprefix('s:')
                if state not in self.owners:
                    continue
                groups = defaultdict(list)
                for subkey, substate in objects(state_obj):
                    old = subkey.removeprefix('region_state:')
                    dest = self.economic_owner(state, old)
                    groups[dest].append(remap_local_investors(substate.text(), state, old, dest))
                    self.changes.append({'kind': 'template_buildings', 'state': state, 'from': old, 'to': dest})
                body = '\n' + ''.join(f'\t\tregion_state:{tag} = {{\n' + '\n'.join(rows) + '\n\t\t}\n' for tag, rows in sorted(groups.items()))
                changes.append(replace_body(state_obj, body + '\t'))
            updated = patch(text, changes)
            # Also repair investor references to a substate that changed hands,
            # including references inside buildings outside the test region.
            repairs = []
            for key, item in walk(root(updated)):
                data = scalars(item)
                state, owner = data.get('region'), data.get('country', '').removeprefix('c:')
                if state in self.owners and owner in set(self.original[state].values()):
                    dest = self.economic_owner(state, owner)
                    if owner != dest:
                        repairs.append(replace_body(item, replace_country(item.text(), owner, dest)))
            self.write_changed(relative, text, patch(updated, repairs))

    def military(self):
        transferred = defaultdict(list)
        for path in sorted((self.game / 'common/history/military_formations').glob('*.txt')):
            relative = path.relative_to(self.game)
            text = self.read(relative)
            changes = []
            for topkey, top in objects(root(text)):
                for country_key, country in objects(top):
                    old = country_key.removeprefix('c:')
                    for key, unit in walk(country):
                        if key != 'combat_unit':
                            continue
                        data = scalars(unit)
                        state = data.get('state_region', '').removeprefix('s:')
                        if state not in self.owners:
                            continue
                        dest = self.economic_owner(state, old)
                        if dest != old:
                            start, end = whole_entry(key, unit)
                            changes.append((start, end, ''))
                            transferred[dest].append('combat_unit = {' + unit.text() + '}')
                            self.moved_units.append({'state': state, 'from': old, 'to': dest, 'count': int(data['count']), 'type': data['type']})
            updated = patch(text, changes)
            empty = []
            for key, item in walk(root(updated)):
                if key == 'create_military_formation' and scalars(item).get('type') == 'army':
                    if not any(k == 'combat_unit' for k, v in objects(item)):
                        start, end = whole_entry(key, item)
                        empty.append((start, end, ''))
            self.write_changed(relative, text, patch(updated, empty))
        body = 'MILITARY_FORMATIONS = {\n'
        for tag, units in sorted(transferred.items()):
            body += f'c:{tag} ?= {{ create_military_formation = {{ type = army hq_region = sr:region_southern_europe name = M2_Test_Army\n'
            body += '\n'.join(units) + '\n} }\n'
        self.outputs['common/history/military_formations/99_m2_formations.txt'] = body + '}\n'

    def countries(self):
        relative = 'common/country_definitions/00_countries.txt'
        text = self.read(relative)
        defs = root(text).fields()
        edits = []
        for tag, state in self.profile['capital_overrides'].items():
            body, count = re.subn(r'\bcapital\s*=\s*STATE_\w+', 'capital = ' + state, defs[tag].text())
            if count != 1:
                raise ValueError('Missing/ambiguous capital: ' + tag)
            edits.append(replace_body(defs[tag], body))
        self.write_changed(relative, text, patch(text, edits))
        for group in ['countries', 'population']:
            source = f'common/history/{group}/sar - sardinia.txt'
            self.outputs[f'common/history/{group}/zzz_m2_italy.txt'] = replace_country(self.read(source), 'SAR', 'ITA')

    def validate(self):
        # Parse every output and verify state/substate dependencies in the effective
        # overlaid history, rather than trusting the code that performed the edits.
        effective_owners = {}
        all_state_text = self.outputs['common/history/states/00_states.txt']
        emitted_states = root(all_state_text).fields()['STATES'].fields()
        for key, obj in emitted_states.items():
            name = key.removeprefix('s:')
            effective_owners[name] = state_owners(obj, strict=name in self.owners)
        for state, expected in self.owners.items():
            if effective_owners[state] != expected:
                raise ValueError('Emitted province ownership differs from resolved mapping')
        original_states = root(self.read('common/history/states/00_states.txt')).fields()['STATES'].fields()
        for state, owners in effective_owners.items():
            if state not in self.owners:
                original = original_states['s:' + state]
                current = emitted_states['s:' + state]
                if original.text() != current.text():
                    raise ValueError('Unexpected ownership change outside test region')
        for relative, text in self.outputs.items():
            doc = root(text)
            list(walk(doc))
            if '/pops/' in relative or '/buildings/' in relative:
                for _, top in objects(doc):
                    for state_key, state in objects(top):
                        name = state_key.removeprefix('s:')
                        if name not in effective_owners:
                            raise ValueError('Unknown state in output: ' + name)
                        for subkey, sub in objects(state):
                            if subkey.startswith('region_state:') and subkey.removeprefix('region_state:') not in effective_owners[name].values():
                                raise ValueError(f'Dangling output substate: {name}/{subkey}')
                        for _, obj in walk(state):
                            data = scalars(obj)
                            region = data.get('region')
                            owner = data.get('country', '').removeprefix('c:')
                            if region and owner and owner not in effective_owners[region].values():
                                raise ValueError(f'Dangling investor substate: {region}/{owner}')
            if '/military_formations/' in relative:
                for _, top in objects(doc):
                    for tag_key, country in objects(top):
                        tag = tag_key.removeprefix('c:')
                        for key, obj in walk(country):
                            if key == 'combat_unit':
                                state = scalars(obj).get('state_region', '').removeprefix('s:')
                                if state and tag not in effective_owners[state].values():
                                    raise ValueError('Army references foreign/nonexistent substate')
        defs = root(self.outputs['common/country_definitions/00_countries.txt']).fields()
        for tag, capital in self.profile['capital_overrides'].items():
            if tag not in effective_owners[capital].values() or defs[tag].fields()['capital'] != capital:
                raise ValueError('Capital not owned by country')

    def build(self):
        self.states()
        self.pops()
        self.buildings()
        self.military()
        self.countries()
        self.validate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-run', type=Path, required=True)
    parser.add_argument('--profile', type=Path, default=ROOT / 'config/personal/m2_italy_provence.json')
    parser.add_argument('--vic3-dir', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding='utf-8'))
    audit_path = args.audit_run / 'report/import_report.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    provenance = json.loads((args.audit_run / 'inputs.json').read_text(encoding='utf-8'))
    if audit['errors'] or audit['status'] not in ['validated_import', 'validated_import_with_skips'] or audit['policies']['missing_building_pop'] != 'P001':
        raise ValueError('Requires a successful P001 C++ import')
    if provenance['exit_code'] != 0 or not provenance['source_unchanged'] or digest(Path(provenance['source'])) != profile['source_sha256']:
        raise ValueError('Source save differs from approved M2 sample')
    if provenance['source_sha256'] != profile['source_sha256'] or Path(audit['source']).resolve() != Path(provenance['source']).resolve():
        raise ValueError('Audit provenance mismatch')
    launcher = args.vic3_dir / 'launcher/launcher-settings.json'
    if json.loads(launcher.read_text(encoding='utf-8-sig'))['rawVersion'] != profile['target_version']:
        raise ValueError('M2 prototype requires exact V3 1.13.11')
    game = args.vic3_dir / 'game'
    for relative, expected in profile['target_fingerprints'].items():
        if digest(game / relative) != expected:
            raise ValueError('Target files changed; review mapping: ' + relative)
    output = args.output or ROOT / '.local/m2/runs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    if output.exists():
        raise ValueError('Output exists; choose a fresh directory')
    prototype = Prototype(game, profile, audit)
    prototype.build()
    prototype.outputs['localization/english/m2_l_english.yml'] = 'l_english:\n M2_Test_Army:0 "M2 Test Army"\n'
    prototype.outputs['localization/simp_chinese/m2_l_simp_chinese.yml'] = 'l_simp_chinese:\n M2_Test_Army:0 "M2测试军团"\n'
    output.mkdir(parents=True, exist_ok=False)
    mod = output / 'eu5_m2_italy_provence'
    for relative, text in prototype.outputs.items():
        path = mod / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8-sig')
    metadata = {'name': 'EU5 M2 - Italy and Provence - TEST', 'id': 'eu5-personal-m2', 'version': '0.2.0',
                'supported_game_version': '1.13.11', 'short_description': 'Regional test: EU5 territorial anchors with vanilla 1836 population/economy templates.',
                'tags': ['Alternative History'], 'relationships': [], 'game_custom_data': {'multiplayer_synchronized': True, 'replace_paths': []}}
    (mod / '.metadata').mkdir()
    (mod / '.metadata/metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    report = {'stage': 'M2 regional prototype', 'status': 'static_checks_passed_game_test_pending',
              'profile': profile, 'audit_report_sha256': digest(audit_path), 'source_sha256': provenance['source_sha256'],
              'source_date': audit['date'], 'target_date': '1836.1.1', 'target_version': profile['target_version'],
              'province_owners': prototype.owners, 'template_population_before': sum(prototype.pop_before.values()),
              'template_population_after': sum(prototype.pop_after.values()), 'building_template_changes': prototype.changes,
              'transferred_combat_units': prototype.moved_units, 'p001_skipped_source_buildings': audit['building_selection']['skipped'],
              'input_hashes': prototype.inputs, 'output_hashes': {str(p.relative_to(mod)): digest(p) for p in sorted(mod.rglob('*')) if p.is_file()},
              'limitations': ['Territorial anchors are a coarse explicit mapping, not pixel-exact borders.',
                              'Population, culture, religion, buildings and politics use V3 1836 test templates, not EU5 conversion.',
                              'Within former French Provence, template pops split by province count; buildings and land units follow the largest successor.',
                              'EU5 buildings are not used in this format prototype; subsequent economic conversion must use the C++ P001 included set.',
                              'Outside-region state ownership is unchanged; necessary investor references and old-owner capital/army references are repaired.',
                              'No game launch, one-year simulation or save/reload validation has been performed.']}
    (output / 'conversion_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'INSTALL.txt').write_text('M2 局部格式测试，目标 V3 1.13.11\n\n将 eu5_m2_italy_provence 文件夹复制到“文档/Paradox Interactive/Victoria 3/mod/”。\n在启动器新建测试播放集，只启用 EU5 M2 - Italy and Provence - TEST。\n新建 1836 年沙盒游戏，选择地图上的意大利，不要加载旧 V3 存档。\n预期：皮埃蒙特归意大利；普罗旺斯由意大利和教宗国分占；撒丁首都在萨伏依。\n人口与经济仍是 V3 原版测试模板，不是完整 EU5 战役转换。\n先暂停保存 M2_start；推进到 1837.1.1 保存 M2_year1；退出到菜单再载入 M2_year1。\n若失败，记录失败阶段。将存档名和同会话 error.log 留给转换器核验。\n停用测试播放集即可恢复原版开局；不要覆盖原战役存档。\n', encoding='utf-8-sig')
    print(json.dumps({'output': str(output), 'mod': str(mod), 'files': len(prototype.outputs), 'status': report['status'], 'template_population': report['template_population_after']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
