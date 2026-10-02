"""One source-player opt-out, via native bloc exit permission and acceptance AI."""
from decimal import Decimal

from pdx_text import root
from build_m2_prototype import patch, replace_body

PERMIT = 'eu5_hre_exit_permit'
RESOLVED = 'eu5_hre_exit_resolved'
INVITE_PATH = 'common/diplomatic_actions/28_invite_to_power_bloc.txt'
ON_ACTIONS = 'common/on_actions/00_code_on_actions.txt'


def exit_probability(own, emperor, family, total, colonial, elector, republic_against_monarchy):
    """Use source demography, not unconverted target GDP or colony tag counts."""
    if own <= 0 or emperor <= 0 or total <= 0 or family <= 0:
        return 0, ['insufficient_source_population']
    ratio, share = own / emperor, family / total
    if ratio >= 2 and share >= Decimal('0.35'):
        return 100, ['dominant_source_player:own_population>=2x_emperor_and_family>=35pct_bloc']
    score, reasons = 20, ['base:20']
    changes = [(30 if ratio >= 2 else 15 if ratio >= 1 else -20 if ratio < Decimal('.25') else 0, 'relative_population'),
               (20 if share >= Decimal('.25') else -10 if share < Decimal('.05') else 0, 'family_population_share'),
               (10 if colonial / family >= Decimal('.25') else 0, 'overseas_colonial_population'),
               (-25 if elector else 0, 'electoral_stake'),
               (10 if republic_against_monarchy else 0, 'constitutional_distance')]
    for amount, reason in changes:
        score += amount
        if amount: reasons.append(f'{reason}:{amount:+d}')
    return min(95, max(5, score)), reasons


def plan_player_exit(w, blocs, edges):
    sid = str(w.audit.get('player', {}).get('id', ''))
    tag = w.tags.get(sid)
    result = {'source_player_id': sid or None, 'target': tag, 'enabled': False,
              'identification': 'EU5 played_country via audited player.id',
              'runtime_test': 'pending'}
    if not tag: return dict(result, reason='source_player_has_no_target')
    b = next((b for b in blocs if b['source_type'] == 'hre' and tag in b['members']), None)
    if not b: return dict(result, reason='source_player_not_in_hre')
    if b['leader'] == tag: return dict(result, reason='source_player_is_emperor')
    parents = {e['target_subject']:e['target_overlord'] for e in edges}
    if tag in parents: return dict(result, reason='source_player_is_subject')
    family = {tag}
    while True:
        expanded = family | {s for s,p in parents.items() if p in family}
        if expanded == family: break
        family = expanded
    populations = {t:Decimal(w.source[s]['population_persons']) for s,t in w.tags.items()}
    population = lambda members: sum((populations.get(t, Decimal(0)) for t in members), Decimal(0))
    colonies = {t for t in family if w.countries[t]['country_type'] == 'colonial'}
    own, emperor = populations[tag], populations[b['leader']]
    fp, total, cp = population(family), population(b['members']), population(colonies)
    elector = tag in b['constitution']['electors']
    different = w.countries[tag]['source_government'] == 'republic' and w.countries[b['leader']]['source_government'] == 'monarchy'
    probability, reasons = exit_probability(own, emperor, fp, total, cp, elector, different)
    return dict(result, enabled=True, reason='independent_source_player_hre_member',
                bloc=b['name'], initial_emperor=b['leader'], family=sorted(family),
                family_members=len(family), colonial_countries=len(colonies),
                own_population=str(own), emperor_population=str(emperor), family_population=str(fp),
                bloc_population=str(total), colonial_population=str(cp),
                family_population_share=float(fp/total) if total else 0,
                ai_leave_percent=probability, ai_reasons=reasons, permit_days=365,
                execution='native_peaceful_leave_action; human_click_required; AI_acceptance_drives_native_exit',
                notifications='decision_then_verified_exit_or_expiry',
                once='after_lobby_bootstrap_plus_country_offered/resolved_flags')


def patch_invite(text):
    obj = root(text).fields()['invite_to_power_bloc'].fields()['ai'].fields()['accept_score']
    # Native file documents that current-member invite acceptance is also used
    # to determine desire to LEAVE. Do not modify the leave WAR GOAL score.
    return patch(text, [replace_body(obj, obj.text() + '''
        if = {
            limit = {
                has_variable = eu5_hre_exit_permit
                is_in_same_power_bloc = scope:actor
                scope:actor.power_bloc ?= { has_identity = identity:identity_eu5_hre_empire }
            }
            add = -100000
        }
''')])


def patch_on_actions(text):
    entries = root(text).fields()
    edits = []
    for key, hook in [('on_game_started_after_lobby', 'eu5_hre_exit_bootstrap'),
                      ('on_diplomatic_action', 'eu5_hre_exit_action_cleanup')]:
        obj = entries[key]
        existing = obj.fields().get('on_actions')
        if existing:
            edits.append(replace_body(existing, existing.text() + '\n' + hook + '\n'))
        else:
            edits.append(replace_body(obj, obj.text() + '\non_actions = { ' + hook + ' }\n'))
    return patch(text, edits)


def export_player_exit(exporter, blocs, edges):
    from build_m3_world import block
    w = exporter.w
    p = plan_player_exit(w, blocs, edges)
    if not p['enabled']: return p
    tag, chance = p['target'], p['ai_leave_percent']
    eligibility = '''is_subject = no
is_power_bloc_leader = no
is_in_power_bloc = yes
power_bloc ?= { has_identity = identity:identity_eu5_hre_empire }
'''
    exporter.write(INVITE_PATH, patch_invite(w.read(INVITE_PATH)))
    exporter.write(ON_ACTIONS, patch_on_actions(w.read(ON_ACTIONS)))
    # Country-scoped variables only. Global hooks explicitly scope the source player.
    exporter.write('common/on_actions/zz_eu5_hre_player_exit.txt',
        block('eu5_hre_exit_bootstrap', block('effect', block('c:' + tag + ' ?', block('if',
            block('limit', eligibility + 'NOT = { has_variable = eu5_hre_exit_offered }') +
            'set_variable = eu5_hre_exit_offered\ntrigger_event = { id = eu5_hre_exit.1 days = 0 popup = yes }')))) +
        block('eu5_hre_exit_action_cleanup', block('effect', block('c:' + tag + ' ?',
            'eu5_hre_exit_check = yes'))))
    notify = lambda event: block('every_country', block('limit', f'is_player = yes\nNOT = {{ c:{tag} = THIS }}') +
                                f'trigger_event = {{ id = eu5_hre_exit.{event} days = 0 popup = yes }}')
    not_hre = '''trigger_if = {
    limit = { is_in_power_bloc = yes }
    power_bloc = { NOT = { has_identity = identity:identity_eu5_hre_empire } }
}
trigger_else = { always = yes }
'''
    check = block('if', block('limit', 'has_variable = eu5_hre_exit_waiting') +
        block('if', block('limit', not_hre) +
              'remove_variable = eu5_hre_exit_permit\nremove_variable = eu5_hre_exit_waiting\n'
              'set_variable = eu5_hre_exit_completed\n' + notify(3)) +
        block('else_if', block('limit', 'NOT = { has_variable = eu5_hre_exit_permit }') +
              'remove_variable = eu5_hre_exit_waiting\nset_variable = eu5_hre_exit_expired\n' +
              'trigger_event = { id = eu5_hre_exit.5 days = 0 popup = yes }\n' + notify(5)))
    exporter.write('common/scripted_effects/zz_eu5_hre_player_exit.txt', block('eu5_hre_exit_check', check))
    def header(i):
        return (f'type = country_event\nplacement = ROOT\ntitle = eu5_hre_exit.{i}.t\n'
                f'desc = eu5_hre_exit.{i}.d\nflavor = eu5_hre_exit.{i}.f\nduration = 3\n'
                'event_image = { video = "unspecific_signed_contract" }\n'
                'icon = "gfx/interface/icons/event_icons/waving_flag.dds"\n')
    permission = ('set_variable = eu5_hre_exit_resolved\nset_variable = eu5_hre_exit_waiting\n'
                  'set_variable = { name = eu5_hre_exit_permit value = yes days = 365 }\n'
                  'add_journal_entry = { type = je_eu5_hre_exit_window }\n'
                  'trigger_event = { id = eu5_hre_exit.6 days = 1 }\n' + notify(2))
    events = 'namespace = eu5_hre_exit\n' + block('eu5_hre_exit.1', header(1) +
        block('trigger', eligibility + f'c:{tag} = THIS\nNOT = {{ has_variable = eu5_hre_exit_resolved }}') +
        block('option', 'name = eu5_hre_exit.1.leave\n' + block('ai_chance', f'base = {chance}') + permission) +
        block('option', 'name = eu5_hre_exit.1.stay\ndefault_option = yes\n' +
              block('ai_chance', f'base = {100-chance}') + 'set_variable = eu5_hre_exit_resolved\n' + notify(4)))
    for i in (2,3,4,5):
        events += block(f'eu5_hre_exit.{i}', header(i) +
                        block('option', 'name = eu5_hre_exit.ack\ndefault_option = yes'))
    # Finite polling only while the one-time permit is pending; no global pulses.
    events += block('eu5_hre_exit.6', 'type = country_event\nhidden = yes\n' +
        block('trigger', f'c:{tag} = THIS\nhas_variable = eu5_hre_exit_waiting') +
        block('immediate', 'eu5_hre_exit_check = yes\n' + block('if',
              block('limit', 'has_variable = eu5_hre_exit_waiting') +
              'trigger_event = { id = eu5_hre_exit.6 days = 1 }')))
    exporter.write('events/eu5_hre_player_exit.txt', events)
    exporter.write('common/journal_entries/zz_eu5_hre_exit_window.txt', block('je_eu5_hre_exit_window',
        'icon = "gfx/interface/icons/event_icons/waving_flag.dds"\ngroup = je_group_foreign_affairs\n' +
        block('is_shown_when_inactive', f'exists = c:{tag}\nc:{tag} = THIS\nhas_variable = eu5_hre_exit_waiting') +
        block('possible', f'exists = c:{tag}\nc:{tag} = THIS\nhas_variable = eu5_hre_exit_waiting') +
        block('complete', 'has_variable = eu5_hre_exit_completed') +
        block('invalid', 'NOT = { has_variable = eu5_hre_exit_waiting }\nNOT = { has_variable = eu5_hre_exit_completed }') +
        'weight = 1000\nshould_be_pinned_by_default_uninvolved_or_context = yes\n'))
    for lang in exporter.localization:
        name = w.countries[tag]['name_' + lang]
        if lang == 'simp_chinese':
            entries = {
                'eu5_hre_exit.1.t': '帝国宪制的重新选择',
                'eu5_hre_exit.1.d': f'{name}是原 EU5 战役的玩家国家。新时期开始，帝国允许我们一次性重新决定成员资格。选择离开后，请在一年内打开集团界面，使用原生“退出集团”按钮完成和平退出；属国随宗主处理，既有同盟和宗主关系不因本事件解除。选择留下或许可到期后，不再补发机会。',
                'eu5_hre_exit.1.f': f'按原档人口与属国规模，AI 选择退出的概率为 {chance}%。这项判断不使用当前 V3 经济模板。',
                'eu5_hre_exit.1.leave': '申请一次和平退出许可（须在集团界面完成）',
                'eu5_hre_exit.1.stay': '继续留在帝国，放弃本次机会',
                'eu5_hre_exit.2.t': f'{name}决定申请退出帝国',
                'eu5_hre_exit.2.d': f'原 EU5 玩家国{name}已取得一次性和平退出许可。AI 将倾向通过原生外交流程离开；这还不是退出完成通知。实际集团与市场变化将在退出后发生。',
                'eu5_hre_exit.3.t': f'{name}已离开帝国集团',
                'eu5_hre_exit.3.d': f'已确认{name}不再属于神罗集团，一次性许可现已收回。其属国仍遵循原宗主关系，原有同盟条约不由本事件删除。',
                'eu5_hre_exit.4.t': f'{name}选择留在帝国',
                'eu5_hre_exit.4.d': f'原 EU5 玩家国{name}放弃本次和平退出机会。此后按普通成员规则处理退出。',
                'eu5_hre_exit.5.t': '帝国退出许可已到期',
                'eu5_hre_exit.5.d': f'{name}未在一年内完成退团，一次性许可现已到期。后续退出恢复普通成员规则。',
                'eu5_hre_exit.ack': '知悉',
                'je_eu5_hre_exit_window': '一次性帝国退出许可',
                'je_eu5_hre_exit_window_reason': '你已选择申请和平退出。请在许可发放后一年内，进入神罗集团界面并点击“退出集团”。这是成员资格调整，不是解除你的殖民地与属国。成功退出即收回许可；保存重载不会再发一次事件。',
                'je_eu5_hre_exit_window_status': '在集团界面完成和平退出',
            }
        else:
            entries = {
                'eu5_hre_exit.1.t': 'An Imperial Choice',
                'eu5_hre_exit.1.d': f'{name} was the EU5 player country. Accept a single one-year permission to leave peacefully, then use Leave Power Bloc in the bloc interface. Subjects follow their sovereign; this event deletes no subject or alliance treaties. Staying or allowing the permit to expire forfeits the opportunity.',
                'eu5_hre_exit.1.f': f'Source population and subject structure give the AI a {chance}% leave preference. Target economic templates are not used.',
                'eu5_hre_exit.1.leave': 'Request peaceful exit permission (complete in bloc interface)',
                'eu5_hre_exit.1.stay': 'Remain and forfeit this opportunity',
                'eu5_hre_exit.2.t': f'{name} intends to leave the Empire',
                'eu5_hre_exit.2.d': f'{name} has requested its one-time permit. Native AI diplomacy must still execute the departure; this notice does not claim it has left.',
                'eu5_hre_exit.3.t': f'{name} has left the imperial bloc',
                'eu5_hre_exit.3.d': f'{name} is no longer in the HRE bloc. The permit has been consumed. Subject and alliance treaties are not deleted by this event.',
                'eu5_hre_exit.4.t': f'{name} remains in the Empire',
                'eu5_hre_exit.4.d': f'{name} has forfeited its one-time exit opportunity. Ordinary exit rules now apply.',
                'eu5_hre_exit.5.t': 'Imperial exit permission expired',
                'eu5_hre_exit.5.d': f'{name} did not complete its departure within a year. The one-time permission has expired and ordinary exit rules resume.',
                'eu5_hre_exit.ack': 'Understood',
                'je_eu5_hre_exit_window': 'One-time Imperial Exit Permission',
                'je_eu5_hre_exit_window_reason': 'Use Leave Power Bloc in the imperial bloc interface within one year. Subject relations remain intact. The permit is consumed upon departure and is not reissued on reload.',
                'je_eu5_hre_exit_window_status': 'Complete the peaceful exit in the bloc interface',
            }
        for i in (2,3,4,5): entries[f'eu5_hre_exit.{i}.f'] = ''
        exporter.localization[lang].update(entries)
    return p
