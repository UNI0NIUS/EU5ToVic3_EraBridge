"""Rebuild private identity resources from the player's own game installations."""
from converter_i18n import Message
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid
from pdx_text import root as parse, Object
from converter_project import read, write, digest
from build_m3_world import load_localization
from converter_identity_policy import clean_label

KINDS = ('cultures', 'religions', 'discrimination_traits', 'discrimination_trait_groups')


def semantic(value):
    return [[key, semantic(child)] for key, child in value.entries()] if isinstance(value, Object) else value


def config_digest(path):
    """Hash text configs identically with Git LF or Windows CRLF checkouts."""
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def semantic_hash(value):
    data = json.dumps(semantic(value), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def render(value):
    if isinstance(value, Object):
        return '{' + value.text() + '}'
    if isinstance(value, list):
        return '{ ' + ' '.join((key + ' = ' if key else '') + render(child) for key, child in value) + ' }'
    value = str(value)
    return value if re.fullmatch(r'[\w.:-]+', value) else json.dumps(value, ensure_ascii=False)


def safe_child(parent, relative):
    parent = Path(parent).resolve()
    path = (parent / relative).resolve()
    if not path.is_relative_to(parent) or path == parent:
        raise ValueError(Message('资源路径越界：{0}', str(relative)))
    return path


def game_paths(eu5, game):
    eu5, game = Path(eu5).resolve(), Path(game).resolve()
    if (eu5 / 'game/in_game').is_dir():
        eu5 = eu5 / 'game'
    if (game / 'game/common').is_dir():
        game = game / 'game'
    if not (eu5 / 'in_game/common/cultures').is_dir() or not (game / 'common/cultures').is_dir():
        raise ValueError(Message('请选择有效的 EU5 安装目录及 Victoria 3 game 目录。'))
    return {'eu5': eu5, 'v3': game}


class InstalledResources:
    def __init__(self, paths):
        self.paths = paths
        self.definitions = {}
        self.labels = {}

    def definitions_for(self, game, kind):
        key = game, kind
        if key not in self.definitions:
            folder = self.paths[game] / ('in_game/common' if game == 'eu5' else 'common') / kind
            self.definitions[key] = {name: obj for path in sorted(folder.glob('*.txt'))
                                     for name, obj in parse(path.read_text(encoding='utf-8-sig')).entries()
                                     if name and isinstance(obj, Object)}
        return self.definitions[key]

    def labels_for(self, game, language):
        key = game, language
        if key not in self.labels:
            folder = self.paths[game] / ('main_menu/localization' if game == 'eu5' else 'localization')
            self.labels[key] = load_localization(folder / language)
            self.labels[key].update(load_localization(folder / 'replace' / language))
        return self.labels[key]

    def field(self, reference):
        try:
            obj = self.definitions_for(reference['game'], reference['kind'])[reference['key']]
            value = obj.fields()[reference['field']]
        except KeyError as error:
            raise ValueError(Message('游戏资源缺少定义：{0}', str(reference))) from error
        if semantic_hash(value) != reference['sha256']:
            raise ValueError(Message('游戏定义与规则版本不符：{0}/{1}', reference['key'], reference['field']))
        return value

    def label(self, reference):
        value = self.labels_for(reference['game'], reference['language']).get(reference['key'])
        if value is None:
            raise ValueError(Message('游戏缺少本地化：{0}', reference['key']))
        if reference.get('clean'):
            value = clean_label(value)
        value += reference.get('suffix', '')
        if hashlib.sha256(value.encode('utf-8')).hexdigest() != reference['sha256']:
            raise ValueError(Message('游戏本地化与规则版本不符：{0}', reference['key']))
        return value


def materialize_assets(recipe, installed, out):
    out = Path(out)
    for kind, definitions in recipe['definitions'].items():
        if kind not in KINDS:
            raise ValueError('Unsupported identity definition kind')
        bodies = []
        for name, fields in definitions.items():
            body = []
            for key, spec in fields.items():
                value = installed.field(spec['reference']) if 'reference' in spec else spec['value']
                body.append('\t' + key + ' = ' + render(value))
            bodies.append(name + ' = {\n' + '\n'.join(body) + '\n}\n')
        dest = out / 'common' / kind / 'zz_converter_identity.txt'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(''.join(bodies), encoding='utf-8-sig')
    for language, labels in recipe['labels'].items():
        values = {key: installed.label(spec['reference']) if 'reference' in spec else spec['value']
                  for key, spec in labels.items()}
        dest = safe_child(out, 'localization/replace/' + language + '/zz_converter_identity_l_' + language + '.yml')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text('l_' + language + ':\n' + ''.join(' ' + key + ':0 ' + json.dumps(value, ensure_ascii=False) + '\n'
                                                       for key, value in sorted(values.items())), encoding='utf-8-sig')
    from religion_icon_texture import compile_icon
    for target, spec in recipe['icons'].items():
        source = safe_child(installed.paths['eu5'], spec['source'])
        if digest(source) != spec['sha256']:
            raise ValueError(Message('宗教图标与规则版本不符：{0}', spec['source']))
        compile_icon(source, safe_child(out, target))


def validate_baseline(path, game):
    """Accept a player's fresh save, not one developer-specific file hash."""
    from economy_model import british_baseline, Target
    text = Path(path).read_text(encoding='utf-8-sig')
    doc = parse(text).fields()
    meta = doc.get('meta_data')
    if not isinstance(meta, Object):
        raise ValueError(Message('基准存档缺少 meta_data；请提供 V3 1.13.11 的原版开局存档。'))
    info = meta.fields()
    if info.get('version') != '1.13.11' or doc.get('date') != '1836.1.1':
        raise ValueError(Message('基准须为 V3 1.13.11、1836.1.1，保存前不要推进时间。'))
    for key in ('mods', 'enabled_mods', 'mods_used', 'mod_list'):
        value = info.get(key) or doc.get(key)
        if value and (not isinstance(value, Object) or list(value.entries())):
            raise ValueError(Message('基准存档包含模组记录；请禁用模组后新开局。'))
    reference = british_baseline(path, Target(game))
    return {'date': doc['date'], 'version': info['version'], 'british_population': reference['population'],
            'mod_free_requirement': 'User must create an unmodified fresh start; absence of mod metadata alone is not proof.'}


def initialize(root, workspace, eu5, game, baseline, progress=None):
    root, workspace, baseline = Path(root).resolve(), Path(workspace).resolve(), Path(baseline).resolve()
    paths = game_paths(eu5, game)
    seed = root / 'config/release_rules'
    manifest = read(seed / 'manifest.json')
    if manifest.get('schema') != 1:
        raise ValueError('Unsupported rule recipe schema')
    for rel, expected in manifest['files'].items():
        if digest(safe_child(seed, rel)) != expected:
            raise ValueError(Message('初始化规则文件已变化：{0}', rel))
    for domain, rel, key in [('eu5', 'in_game/map_data/locations.png', 'source_map_sha256'),
                              ('v3', 'map_data/provinces.png', 'target_map_sha256')]:
        if digest(paths[domain] / rel) != manifest[key]:
            raise ValueError(Message('游戏地图版本与规则不匹配：{0}', domain))
    if not baseline.is_file():
        raise ValueError(Message('请选择自己的 V3 原版 1836.1.1 开局存档。'))
    # Never touch existing rules. An incomplete attempt remains separate and has no manifest.
    out = workspace / 'initialized-rules' / uuid.uuid4().hex
    out.mkdir(parents=True, exist_ok=False)
    notify = progress or (lambda message: None)
    notify(Message('读取 Victoria 3 基准存档'))
    private = out / 'private/vic3-start.txt'
    private.parent.mkdir()
    header = baseline.open('rb')
    with header:
        prefix = header.read(64)
    if baseline.suffix.lower() == '.txt' and (prefix.startswith(b'SAV') or prefix.lstrip().startswith(b'meta_data')):
        shutil.copyfile(baseline, private)
    else:
        from inspect_save_metadata import inspect
        library = root / 'native/rakaly.dll'
        if not library.is_file():
            library = root / 'build/Release-Windows/EU5ToVic3/rakaly.dll'
        result = inspect(baseline, 'vic3', library, private)
        if result.get('unknown_tokens') or result.get('full_save', {}).get('unknown_tokens'):
            raise ValueError(Message('基准存档包含未知词元，不能用于转换。'))
    baseline_report = validate_baseline(private, paths['v3'])
    notify(Message('从本机游戏生成文化、宗教和图标'))
    materialize_assets(read(seed / 'assets.json'), InstalledResources(paths), out / 'assets')
    for name in ('culture_mapping.json', 'identity_homelands.json', 'identity_policy.json', 'terrain_reviews.json'):
        shutil.copy2(seed / name, out / name)
    profile = read(seed / 'config_profile.json')
    for rel, expected in profile['files'].items():
        source = safe_child(root, rel)
        if config_digest(source) != expected:
            raise ValueError(Message('转换配置与规则版本不匹配：{0}', rel))
        target = safe_child(out, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for rel, content in profile['overrides'].items():
        write(safe_child(out, rel), content)
    rule_manifest = {key: manifest[key] for key in ('source_map_sha256', 'target_map_sha256', 'terrain_override_provinces')}
    rule_manifest.update(schema=1, kind='player_generated_converter_rules', baseline='private/vic3-start.txt',
                         baseline_sha256=digest(private), recipe_sha256=digest(seed / 'manifest.json'),
                         files={p.relative_to(out).as_posix(): digest(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out / 'private')})
    write(out / 'manifest.json', rule_manifest)
    notify(Message('检查规则引用与本地化'))
    try:
        from verify_converter_identity import verify
        validation = verify(out, paths['v3'], paths['eu5'])
    except Exception:
        (out / 'manifest.json').rename(out / 'failed-manifest.json')
        raise
    write(out / 'initialization-report.json', {'validation': validation, 'baseline': baseline_report,
                                              'source_baseline_sha256': digest(baseline), 'recipe_sha256': digest(seed / 'manifest.json')})
    return {'rules': str(out / 'manifest.json'), 'baseline': baseline_report, 'validation': validation,
            'eu5': str(paths['eu5']), 'game': str(paths['v3'])}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    for name in ('workspace', 'eu5', 'game', 'baseline'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(initialize(**vars(args)), ensure_ascii=False, indent=2))
