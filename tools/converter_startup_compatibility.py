"""Adapt imported starting laws and known localization collisions for V3 1.13."""
import json
import re
from pathlib import Path
from pdx_text import root, Object
from build_m2_prototype import patch, replace_body

REVISION = 'native-startup-1'
LAW_FILES = {'law_chiefdom': '00_governance_principles.txt',
             'law_elder_council': '00_distribution_of_power.txt',
             'law_manorialism': '01_land_reform.txt',
             'law_hereditary_bureaucrats': '00_bureaucracy.txt',
             'law_peasant_levies': '00_army_model.txt'}
# Confirmed by V3 1.13.11: this generated key collides with sn_chong_chia.
KEY_ALIASES = {'EU5_DYNAMIC_NAME_EVU_dictatorship': 'EU5_DYNAMIC_NAME_EVU_dictatorship_imported'}


def retain_imported_law(text, law, tags):
    obj = root(text).fields()[law]
    visible = obj.fields().get('is_visible')
    if not isinstance(visible, Object):
        raise ValueError('Law lacks visibility predicate: ' + law)
    marker = '# EraBridge imported starting law retention'
    allowed = ' '.join('this = c:' + tag for tag in sorted(tags))
    edits = []
    for field in ('is_visible', 'can_enact'):
        predicate = obj.fields().get(field)
        if not isinstance(predicate, Object):
            continue
        original = predicate.text()
        if marker in original:
            original = next(value for key,value in predicate.fields()['OR'].entries() if key == 'AND').text()
        # The exception requires the law to be active already. It cannot be
        # used to adopt this law after changing away from it.
        body = '\n' + marker + '\nOR = {\nAND = {\n' + original.strip() + '\n}\n'
        body += 'AND = { has_law = law_type:' + law + ' OR = { ' + allowed + ' } }\n}\n'
        edits.append(replace_body(predicate, body))
    return patch(text, edits)


def apply(mod, game, run=None):
    mod, game = Path(mod), Path(game)
    tags = {law: set() for law in LAW_FILES}
    for path in (mod / 'common/history/countries').glob('*.txt'):
        countries = root(path.read_text(encoding='utf-8-sig')).fields().get('COUNTRIES')
        if not isinstance(countries, Object):
            continue
        for scope, obj in countries.entries():
            if not scope or not scope.startswith('c:') or not isinstance(obj, Object):
                continue
            active = set(re.findall(r'\bactivate_law\s*=\s*law_type:(\w+)', obj.text()))
            for law in tags:
                if law in active: tags[law].add(scope[2:])
    for law, filename in LAW_FILES.items():
        if not tags[law]: continue
        target = mod / 'common/laws' / filename
        source = target if target.exists() else game / 'common/laws' / filename
        updated = retain_imported_law(source.read_text(encoding='utf-8-sig'), law, tags[law])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding='utf-8-sig')
    renamed = []
    for folder, suffix in [('common/dynamic_country_names', '*.txt'), ('localization', '*.yml')]:
        for path in (mod / folder).rglob(suffix):
            original = path.read_text(encoding='utf-8-sig')
            updated = original
            for old, new in KEY_ALIASES.items():
                updated = re.sub(r'(?<![A-Za-z0-9_])' + re.escape(old) + r'(?![A-Za-z0-9_])', new, updated)
            if updated != original:
                path.write_text(updated, encoding='utf-8-sig'); renamed.append(path.relative_to(mod).as_posix())
    wars = None
    # Older local rule bundles used six-decimal religion colors, which the
    # native fixed-point parser rejects. Culture color parsing is different.
    colors = 0
    for path in (mod / 'common/religions').glob('*.txt'):
        original = path.read_text(encoding='utf-8-sig')
        def rounded(match):
            return re.sub(r'\d+\.\d{6,}', lambda n: str(round(float(n[0]),5)), match[0])
        updated = re.sub(r'\bcolor\s*=\s*\{[^{}]*\}', rounded, original)
        if updated != original:
            path.write_text(updated, encoding='utf-8-sig'); colors += 1
    # Journals also auto-activate through their possible predicates.
    journals = mod / 'common/history/global/01_eu5_hre_constitution.txt'
    if journals.exists():
        journals.write_text('# Entries activate through their possible predicates.\nGLOBAL = {}\n', encoding='utf-8-sig')
    if run is not None and (Path(run) / 'war_mapping.json').exists():
        from opening_wars import render
        rows = json.loads((Path(run) / 'war_mapping.json').read_text(encoding='utf-8-sig'))
        native = root((game / 'common/diplomatic_plays/00_diplomatic_plays.txt').read_text(encoding='utf-8-sig')).fields()
        recognition = root((game / 'common/war_goal_types/22_revoke_all_claims.txt').read_text(encoding='utf-8-sig')).fields()['revoke_all_claims']
        for rel, body in render(rows, native, recognition).items():
            target = mod / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding='utf-8-sig')
        wars = len(rows)
    return {'revision': REVISION, 'law_retention_tags': {k: sorted(v) for k, v in tags.items()},
            'original_enactment_conditions_preserved': True, 'localization_aliases': KEY_ALIASES,
            'renamed_files': renamed, 'opening_wars_regenerated': wars, 'religion_color_files_rounded': colors,
            'runtime_verified': False}
