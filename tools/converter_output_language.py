"""Validate game localization and write installation guidance for a chosen language."""
from pathlib import Path
import re

from build_m3_world import load_localization

OUTPUT_LANGUAGES = {'zh-CN': 'simp_chinese', 'en': 'english'}


def output_language(value):
    if value not in OUTPUT_LANGUAGES:
        raise ValueError('Unsupported output language: ' + str(value))
    return value


def verify(mod, game, language):
    """Require every mod-owned key in the chosen language (or the base game).

    Do not copy Chinese strings into English files to disguise missing translations.
    Do not remove other languages: V3 chooses localization using its own setting.
    """
    selected = OUTPUT_LANGUAGES[output_language(language)]
    mod, game = Path(mod), Path(game)
    if not mod.is_dir():
        raise ValueError('Mod directory does not exist: ' + str(mod))
    catalogs = {}; files = {}
    for folder in OUTPUT_LANGUAGES.values():
        values = {}; paths = []
        for base in (mod/'localization'/folder, mod/'localization/replace'/folder):
            for path in sorted(base.rglob('*.yml')):
                text = path.read_text(encoding='utf-8-sig')
                header = next((line.strip() for line in text.splitlines()
                               if line.strip() and not line.lstrip().startswith('#')), '')
                if header != 'l_' + folder + ':':
                    raise ValueError('Invalid localization header: ' + str(path))
                if not path.read_bytes().startswith(b'\xef\xbb\xbf'):
                    raise ValueError('Localization requires UTF-8 BOM: ' + str(path))
                paths.append(path.relative_to(mod).as_posix())
            values.update(load_localization(base))
        catalogs[folder] = values; files[folder] = paths
    required = set().union(*(set(v) for v in catalogs.values()))
    # Dynamic names may reference keys not present in either mod catalog.
    for path in (mod/'common/dynamic_country_names').glob('*.txt'):
        required.update(re.findall(r'\b(?:name|adjective)\s*=\s*(EU5_\w+)', path.read_text(encoding='utf-8-sig')))
    available = load_localization(game/'localization'/selected)
    available.update(catalogs[selected])
    # Empty surnames and event flavor paragraphs can be intentional.
    missing = sorted(key for key in required if key not in available)
    if missing:
        raise ValueError('Missing ' + selected + ' localization: ' + ', '.join(missing[:50]))
    return dict(status='passed', preferred_language=language, game_language=selected,
                checked_keys=len(required), mod_keys=len(catalogs[selected]), files=files,
                runtime_verified=False)


def write_guide(package, language):
    language = output_language(language)
    texts = {
        'en': 'Independent candidate mod; start a new campaign to validate it.\n'
              'Copy eu5_converted and eu5_converted.mod into your Victoria 3 user mod folder.\n'
              'Enable this candidate in the launcher; avoid enabling other world conversion mods together.\n'
              'Set Victoria 3 language to English before loading the campaign.\n'
              'This package retains its other localization files; changing the game language selects them.\n'
              'The converter produces a starting-world mod, not a .v3 save. Start a campaign and save in Victoria 3.\n'
              'See project.json and risk_report.json for edits and estimates, where present.\n'
              'Static localization checks are recorded in localization_verification.json; in-game validation is pending.\n',
        'zh-CN': '独立候选模组；需新开战役验证。\n'
                 '把 eu5_converted 目录及 eu5_converted.mod 文件放入 Victoria 3 用户 mod 目录。\n'
                 '在启动器启用本候选包，避免同时启用其他世界转换包。\n'
                 '请将 Victoria 3 的游戏语言设置为简体中文。\n'
                 '包内保留其他语言资源；切换游戏语言即可选用。\n'
                 '转换器生成开局世界模组，不直接生成 .v3 存档；请在游戏中新开战役后保存。\n'
                 '编辑与风险估算见 project.json、risk_report.json（若存在）。\n'
                 '本地化静态检查见 localization_verification.json；仍需游戏内验证。\n',
    }
    (Path(package)/'README.txt').write_text(texts[language], encoding='utf-8')
