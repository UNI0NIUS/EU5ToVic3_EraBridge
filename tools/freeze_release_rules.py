"""Freeze authored rules and game-resource references, never game resource bodies."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from converter_project import read, write, digest
from initialize_converter import KINDS, InstalledResources, game_paths, semantic, semantic_hash, config_digest
from pdx_text import root as parse, Object
from build_m3_world import load_localization
from converter_identity_policy import clean_label


def freeze(root, rules, out, eu5, game):
    root, rules, out = map(lambda p: Path(p).resolve(), (root, rules, out))
    if out.exists():
        raise ValueError('Recipe output already exists')
    manifest = read(rules / 'manifest.json')
    for rel, expected in manifest['files'].items():
        if not (rules / rel).resolve().is_relative_to(rules) or digest(rules / rel) != expected:
            raise ValueError('Changed or invalid source rule: ' + rel)
    installed = InstalledResources(game_paths(eu5, game))
    index = {}
    for kind in KINDS:
        for domain in ('v3', 'eu5'):
            if domain == 'eu5' and kind != 'cultures':
                continue
            for name, obj in installed.definitions_for(domain, kind).items():
                for field, value in obj.entries():
                    if field:
                        index.setdefault((kind, semantic_hash(value)), dict(game=domain, kind=kind, key=name, field=field, sha256=semantic_hash(value)))
    recipe = {'schema': 1, 'definitions': {}, 'labels': {}, 'icons': {}}
    counts = Counter()
    for kind in KINDS:
        recipe['definitions'][kind] = {}
        for p in sorted((rules / 'assets/common' / kind).glob('*.txt')):
            for name, obj in parse(p.read_text(encoding='utf-8-sig')).entries():
                if not name or not isinstance(obj, Object):
                    raise ValueError('Unexpected generated definition')
                fields = {}
                for field, value in obj.entries():
                    reference = index.get((kind, semantic_hash(value)))
                    if reference:
                        fields[field] = {'reference': reference}; counts['referenced_fields'] += 1
                    else:
                        # Only small authored rule values. Name pools, appearance and
                        # arbitrary script blocks must be reconstructed from installed games.
                        allowed = {'color', 'language', 'heritage', 'type', 'trait_group', 'icon', 'taboos'}
                        literal = semantic(value)
                        if field not in allowed or len(json.dumps(literal)) > 350:
                            raise ValueError('Unreferenced resource field: ' + kind + '/' + name + '/' + str(field))
                        fields[field] = {'value': literal}; counts['authored_fields'] += 1
                recipe['definitions'][kind][name] = fields
    for language in ('english', 'simp_chinese'):
        labels = {}
        for domain in ('v3', 'eu5'):
            for key, value in installed.labels_for(domain, language).items():
                for cleaned, text in ((False, value), (True, clean_label(value))):
                    labels.setdefault(text, dict(game=domain, language=language, key=key, clean=cleaned))
        values = load_localization(rules / 'assets/localization/replace' / language)
        recipe['labels'][language] = {}
        for key, value in sorted(values.items()):
            reference = labels.get(value)
            if reference is None:
                for suffix in (' Heritage', ' Tradition', ' Language', '传承', '传统', '语'):
                    if value.endswith(suffix) and value[:-len(suffix)] in labels:
                        reference = dict(labels[value[:-len(suffix)]], suffix=suffix)
                        break
            if reference:
                recipe['labels'][language][key] = {'reference': dict(reference, sha256=hashlib.sha256(value.encode('utf-8')).hexdigest())}
                counts['referenced_labels'] += 1
            else:
                if len(value) > 120 or '\n' in value:
                    raise ValueError('Unreviewed long localization: ' + key)
                recipe['labels'][language][key] = {'value': value}; counts['authored_labels'] += 1
    for icon in sorted((rules / 'assets/gfx/interface/icons/religion_icons').glob('*.dds')):
        relative = 'main_menu/gfx/interface/icons/religion/' + icon.name.removeprefix('eu5_religion_')
        source = installed.paths['eu5'] / relative
        recipe['icons'][icon.relative_to(rules / 'assets').as_posix()] = {'source': relative, 'sha256': digest(source)}
    out.mkdir(parents=True)
    write(out / 'assets.json', recipe)
    for name in ('culture_mapping.json', 'identity_policy.json'):
        write(out / name, read(rules / name))
    history = read(rules / 'identity_homelands.json')
    write(out / 'identity_homelands.json', {'schema': 1, 'entries': [{key: entry[key] for key in ('culture', 'status', 'states', 'anchors') if key in entry} for entry in history['entries']]})
    terrain = read(rules / 'terrain_reviews.json')
    for entry in terrain['entries'].values():
        entry['note'] = ''
    write(out / 'terrain_reviews.json', terrain)
    profile = {'files': {}, 'overrides': {}}
    for source in sorted((rules / 'config').rglob('*')):
        if not source.is_file():
            continue
        rel = source.relative_to(rules).as_posix()
        profile['files'][rel] = config_digest(root / rel)
        if digest(source) != digest(root / rel):
            content = read(source)
            content.pop('notes', None)
            profile['overrides'][rel] = content
    write(out / 'config_profile.json', profile)
    output = {key: manifest[key] for key in ('source_map_sha256', 'target_map_sha256', 'terrain_override_provinces')}
    output.update(schema=1, game_versions={'eu5':'1.3.11', 'v3':'1.13.11'},
                  files={p.relative_to(out).as_posix(): digest(p) for p in out.rglob('*') if p.is_file()})
    write(out / 'manifest.json', output)
    return dict(counts, icons_referenced=len(recipe['icons']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'rules', 'out', 'eu5', 'game'):
        parser.add_argument('--' + name, type=Path, required=True)
    print(json.dumps(freeze(**vars(parser.parse_args())), indent=2))
