"""Engine-facing checks missing from the original fresh-save static verifier."""
from pathlib import Path
import re
import shutil
from pdx_text import root, Object
from build_m2_prototype import objects, patch, replace_body
from build_m3_world import block, entry


def rewrite_homelands(content, homelands):
    """Replace complete parsed assignments, preserving all other state actions."""
    edits = []
    for state, obj in objects(root(content).fields()['STATES']):
        body = []
        for key, value in obj.entries():
            if key is None:
                raise ValueError(f'Bare token in state history {state}: {value}')
            if key != 'add_homeland':
                body.append(block(key, value.text().strip()) if isinstance(value, Object) else entry(key, value))
        body.extend(f'add_homeland = cu:{culture}\n'
                    for culture in sorted(homelands.get(state[2:], set())))
        edits.append(replace_body(obj, ''.join(body)))
    return patch(content, edits)


def validate_state_history(content, cultures):
    count = 0
    for state, obj in root(content).fields()['STATES'].entries():
        if not state or not state.startswith('s:') or not isinstance(obj, Object):
            raise ValueError(f'Invalid state history scope: {state}')
        for key, value in obj.entries():
            if key is None:
                raise ValueError(f'Bare token in state history {state}: {value}')
            if key == 'add_homeland':
                if not isinstance(value, str) or not value.startswith('cu:') or value[3:] not in cultures:
                    raise ValueError(f'Invalid homeland culture scope in {state}: {value}')
                count += 1
    return count


MODIFIER_KINDS = {
    'standard_of_living': 'state_{culture}_standard_of_living_add',
    'cultural_acceptance': 'country_{culture}_cultural_acceptance_add',
    'fervor_target': 'country_fervor_target_{culture}_add',
}
MODIFIER_FILE = 'common/static_modifiers/zz_eu5_culture_runtime.txt'
MODIFIER_TYPES_FILE = 'common/modifier_type_definitions/zz_eu5_identity_runtime.txt'


def effective_objects(game, mod, directory, exclude=None):
    paths = {p.name: p for base in (game, mod)
             for p in sorted((base / directory).glob('*.txt')) if p != exclude}
    return {key: obj for p in paths.values()
            for key, obj in objects(root(p.read_text(encoding='utf-8-sig')))}


def culture_modifiers(game, mod, write=False):
    """Generate required definitions using installed vanilla unit templates.

    These are definitions only, never starting bonuses applied to a country.
    """
    output = mod / MODIFIER_FILE
    types_output = mod / MODIFIER_TYPES_FILE
    types = effective_objects(game, mod, 'common/modifier_type_definitions', types_output if write else None)
    vanilla_types = effective_objects(game, game, 'common/modifier_type_definitions')
    existing = effective_objects(game, mod, 'common/static_modifiers', output if write else None)
    vanilla = effective_objects(game, game, 'common/static_modifiers')
    rendered = []
    rendered_types = []
    required = []
    for directory, template_identity, kinds in [('cultures', 'scottish', MODIFIER_KINDS),
                                               ('religions', 'catholic', {'standard_of_living': MODIFIER_KINDS['standard_of_living']})]:
      for culture in sorted(effective_objects(game, mod, 'common/' + directory)):
        for kind, effect in kinds.items():
            effect_key = effect.format(culture=culture)
            template_effect = effect.format(culture=template_identity)
            if effect_key not in types:
                if not write:
                    raise ValueError('Missing required identity modifier type: ' + effect_key)
                rendered_types.append(block(effect_key, vanilla_types[template_effect].text().strip()))
                types[effect_key] = vanilla_types[template_effect]
            for sign in ('positive', 'negative'):
                suffix = f'_{kind}_modifier_{sign}'
                key = culture + suffix
                required.append(key)
                if key in existing:
                    if effect_key not in existing[key].fields():
                        raise ValueError('Identity static modifier does not reference its type: ' + key)
                    continue
                if not write:
                    raise ValueError('Missing required culture static modifier: ' + key)
                template = vanilla[template_identity + suffix].text()
                old = template_effect
                if old not in template:
                    raise ValueError('Vanilla culture modifier schema changed: ' + old)
                rendered.append(block(key, template.replace(old, effect.format(culture=culture))))
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(''.join(rendered), encoding='utf-8-sig')
        types_output.parent.mkdir(parents=True, exist_ok=True)
        types_output.write_text(''.join(rendered_types), encoding='utf-8-sig')
    return len(rendered) if write else len(required)


def flag_assets(game, mod, eu5=None):
    """Check the texture folder required by each COA node, not just its filename."""
    repaired = []
    def visit(obj, folder=None):
        for key, value in obj.entries():
            if isinstance(value, Object):
                visit(value, {'colored_emblem': 'colored_emblems',
                              'textured_emblem': 'textured_emblems'}.get(key, folder))
            elif key == 'pattern' or (key == 'texture' and folder):
                destination = 'patterns' if key == 'pattern' else folder
                if not value.startswith('eu5_m3_'):
                    continue
                relative = Path('gfx/coat_of_arms') / destination / value
                if (mod / relative).is_file() or (game / relative).is_file():
                    continue
                source = None
                if eu5:
                    filename = value.removeprefix('eu5_m3_')
                    source = next((p for base in ('main_menu', 'in_game')
                                   for kind in (destination, 'colored_emblems', 'textured_emblems', 'patterns')
                                   if (p := eu5 / base / 'gfx/coat_of_arms' / kind / filename).is_file()), None)
                if not source:
                    raise ValueError('Missing flag texture: ' + relative.as_posix())
                (mod / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, mod / relative)
                repaired.append({'destination': relative.as_posix(), 'source': str(source)})
    for p in (mod / 'common/coat_of_arms/coat_of_arms').glob('*.txt'):
        visit(root(p.read_text(encoding='utf-8-sig')))
    return repaired


def validate_opening_war_removals(mod, rows):
    from opening_wars import HISTORY, PLAYS, validate_seed_removals
    plays = dict(objects(root((mod / PLAYS).read_text(encoding='utf-8-sig'))))
    histories = list(objects(root((mod / HISTORY).read_text(encoding='utf-8-sig')).fields()['DIPLOMATIC_PLAYS']))
    for row in rows:
        matches = [obj for key, obj in histories if key == 'c:' + row['attacker']
                   and any(k == 'create_diplomatic_play' and isinstance(v, Object)
                           and v.fields().get('type') == row['play_type'] for k, v in obj.entries())]
        if len(matches) != 1:
            raise ValueError('Ambiguous/missing opening war history: ' + row['id'])
        validate_seed_removals(row, matches[0].text(), plays[row['play_type']])
    return len(rows)
