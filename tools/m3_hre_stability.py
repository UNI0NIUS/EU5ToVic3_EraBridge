"""HRE variant: war exit, except a source player's one-time country permit.

V3 1.13.11 power bloc scopes do NOT support variables. Do not store flags there.
"""
import re
from pdx_text import root
from build_m2_prototype import patch, replace_body

IDENTITY = 'identity_eu5_hre_empire'
PRINCIPLE = 'principle_eu5_hre_vassalization_1'
IDENTITIES = 'common/power_bloc_identities/00_power_bloc_identities.txt'
RULES = 'common/scripted_rules/00_scripted_rules.txt'
GROUPS = 'common/power_bloc_principle_groups/00_power_bloc_principle_groups.txt'
PRINCIPLES = 'common/power_bloc_principles/00_power_bloc_principles.txt'


def empire_body(text):
    source = root(text).fields()['identity_sovereign_empire'].text()
    parts = root(source).fields()
    modifiers, count = re.subn(r'power_bloc_cohesion_per_member_add\s*=\s*-3\b',
        'power_bloc_cohesion_add = 15 # Charter +25, fixed size penalty -10',
        parts['power_bloc_modifier'].text())
    if count != 1: raise ValueError('Unsupported Sovereign Empire member penalty')
    return patch(source, [
        replace_body(parts['power_bloc_modifier'], modifiers),
        replace_body(parts['can_leave'], '''
        custom_tooltip = {
            text = eu5_hre_war_exit_tt
            is_subject = no
            is_power_bloc_leader = no
            has_variable = eu5_hre_exit_permit
        }
'''),
        # The inherited institution is created by history, not freely formable.
        replace_body(parts['visible'], '\nalways = no\n')])


def patch_identities(text):
    return text + '\n' + IDENTITY + ' = {\n' + empire_body(text) + '\n}\n'


def patch_rules(text):
    rules = root(text).fields()
    lead = rules['can_lead_power_bloc']; weak = rules['is_weak_power_bloc']
    return patch(text, [
        replace_body(lead, '\nOR = {\n' + lead.text() + '\neu5_is_chartered_hre_leader = yes\n}\n'),
        replace_body(weak, weak.text() + '\nNOT = { has_identity = identity:' + IDENTITY + ' }\n')])


def export_hre_stability(exporter, blocs):
    from build_m3_world import block
    affected = [b for b in blocs if b['source_type'] == 'hre']
    if not affected: return
    exporter.write(IDENTITIES, patch_identities(exporter.w.read(IDENTITIES)))
    exporter.write(RULES, patch_rules(exporter.w.read(RULES)))
    exporter.write('common/scripted_triggers/zz_eu5_hre_charter.txt', '''
eu5_is_chartered_hre_leader = {
    is_power_bloc_leader = yes
    is_subject = no
    NOT = { is_country_type = decentralized }
    power_bloc = { has_identity = identity:identity_eu5_hre_empire }
}
''')
    # Own primary principle group avoids changing primary status for ordinary
    # Sovereign Empires; clone all three levels so upgrades remain available.
    group_text = exporter.w.read(GROUPS)
    original = root(group_text).fields()['principle_group_vassalization']
    group_text = patch(group_text, [replace_body(original,
        original.text() + '\nblocking_identity = ' + IDENTITY + '\n')])
    group_text += block('principle_group_eu5_hre_vassalization',
        f'primary_for_identity = {IDENTITY}\nunlocking_identity = {IDENTITY}\n' +
        block('levels', '\n'.join(f'principle_eu5_hre_vassalization_{i}' for i in range(1, 4))))
    exporter.write(GROUPS, group_text)
    principles = root(exporter.w.read(PRINCIPLES)).fields()
    exporter.write('common/power_bloc_principles/zz_eu5_hre_vassalization.txt', ''.join(
        block(f'principle_eu5_hre_vassalization_{i}', principles[f'principle_vassalization_{i}'].text()
            .replace('identity:identity_sovereign_empire', 'identity:' + IDENTITY)) for i in range(1, 4)))
    labels = {
        'eu5_hre_war_exit_tt': (
            'Peaceful withdrawal requires the EU5 player country\'s one-time exit permit. Otherwise demand Leave Power Bloc against the Emperor and enforce the goal or obtain a backdown.',
            '和平退出须持有原 EU5 玩家国的一次性退出许可；否则须对皇帝发起退出集团外交博弈，迫使其退让或通过战争落实退出目标。'),
        IDENTITY: ('$identity_sovereign_empire$', '$identity_sovereign_empire$'),
        IDENTITY + '_desc': (
            '$identity_sovereign_empire_desc$ Imperial charter: withdrawal requires a diplomatic play, except the EU5 player country\'s one-time peaceful exit permit.',
            '$identity_sovereign_empire_desc$ 帝国宪制：通常退出须通过针对皇帝的外交博弈；原 EU5 玩家国可通过开局事件获得一次和平退出许可。'),
        'eu5_is_chartered_hre_leader': ('Independent Emperor of the converted Holy Roman Empire', '转换后神圣罗马帝国的独立皇帝')}
    for suffix in ('', '_desc'):
        labels['principle_group_eu5_hre_vassalization' + suffix] = ('$principle_group_vassalization' + suffix + '$',) * 2
    for i in range(1, 4):
        labels[f'principle_eu5_hre_vassalization_{i}_desc'] = ('$principle_group_vassalization_desc$',) * 2
    for key, values in labels.items():
        for lang, value in zip(('english', 'simp_chinese'), values):
            exporter.localization[lang][key] = value
    for b in affected:
        b['stability'] = {'identification': 'native_has_identity', 'identity': IDENTITY,
            'fixed_size_penalty': 10, 'charter_cohesion_add': 25, 'initial_cohesion_add': 50,
            'peaceful_exit': 'source_player_one_time_permit_only', 'leader_voluntary_dissolution': False,
            'exit_war_goal': 'leave_power_bloc', 'diplomatic_play': 'dp_leave_power_bloc',
            'leader_backdown_can_avoid_actual_combat': True,
            'weak_bloc_rank_penalty_exempt': True,
            'independent_emperor_leadership_rank_exempt': True, 'runtime_test': 'pending'}
