"""Install one authoritative set of identity assets and localization keys."""
from pathlib import Path
import re
import shutil
from build_m2_prototype import objects
from build_m3_world import block, load_localization
from pdx_text import root

KINDS = ('cultures', 'religions', 'discrimination_traits', 'discrimination_trait_groups')
LABEL = re.compile(r'^\s*([\w.-]+):\d*\s+"')


def bodies(directory):
    return {k: o.text() for p in sorted(directory.glob('*.txt'))
            for k, o in objects(root(p.read_text(encoding='utf-8-sig')))}


def labels(mod, lang):
    result = load_localization(mod/'localization'/lang)
    result.update(load_localization(mod/'localization/replace'/lang))
    return result


def sync(mod, assets):
    mod, assets = Path(mod), Path(assets)
    for folder in (*('common/'+k for k in KINDS), 'gfx/interface/icons/religion_icons', 'localization'):
        if (assets/folder).exists():
            shutil.copytree(assets/folder, mod/folder, dirs_exist_ok=True)
    for kind in KINDS:
        keys = set(bodies(assets/'common'/kind))
        for p in (mod/'common'/kind).glob('*.txt'):
            if (assets/'common'/kind/p.name).exists():
                continue
            text = p.read_text(encoding='utf-8-sig')
            entries = list(objects(root(text)))
            if any(k in keys for k, _ in entries):
                p.write_text(''.join(block(k, o.text()) for k, o in entries if k not in keys), encoding='utf-8-sig')
    # Old replace files can sort after the new bundle. Remove conflicting keys
    # from BOTH localization trees; file naming alone cannot guarantee precedence.
    removed = 0
    for lang in ('english', 'simp_chinese'):
        keys = set(labels(assets, lang))
        for directory in (mod/'localization'/lang, mod/'localization/replace'/lang):
            for p in directory.rglob('*.yml'):
                if (assets/p.relative_to(mod)).exists():
                    continue
                lines = p.read_text(encoding='utf-8-sig').splitlines(keepends=True)
                kept = [line for line in lines if not ((m := LABEL.match(line)) and m[1] in keys)]
                if kept != lines:
                    removed += len(lines)-len(kept)
                    p.write_text(''.join(kept), encoding='utf-8-sig')
    return dict(removed_duplicate_labels=removed, **verify(mod, assets))


def verify(mod, assets):
    mod, assets = Path(mod), Path(assets)
    count = 0
    for kind in KINDS:
        expected, actual = bodies(assets/'common'/kind), bodies(mod/'common'/kind)
        for key, value in expected.items():
            if ' '.join(value.split()) != ' '.join(actual.get(key, '').split()):
                raise ValueError('Identity asset differs from current rules: '+key)
        count += len(expected)
    for lang in ('english', 'simp_chinese'):
        expected, actual = labels(assets, lang), labels(mod, lang)
        seen = set()
        for directory in (mod/'localization'/lang, mod/'localization/replace'/lang):
            for p in directory.rglob('*.yml'):
                for line in p.read_text(encoding='utf-8-sig').splitlines():
                    m = LABEL.match(line)
                    if m and m[1] in expected:
                        if m[1] in seen:
                            raise ValueError('Duplicate identity localization: '+lang+'/'+m[1])
                        seen.add(m[1])
        for key, value in expected.items():
            if actual.get(key) != value:
                raise ValueError('Outdated identity localization: '+lang+'/'+key)
    return dict(identity_assets=count, identity_labels='current_and_unique')
