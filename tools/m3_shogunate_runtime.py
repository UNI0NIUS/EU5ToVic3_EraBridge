"""Original source-driven scripts informed by MTGA and China Power Bloc.
No Workshop scripts or assets are redistributed. See the research provenance.
"""
from build_m3_world import block
GLOBAL='common/history/global/02_eu5_shogunate.txt'
JOURNAL='common/journal_entries/zz_eu5_shogunate.txt'
EFFECTS='common/scripted_effects/zz_eu5_shogunate.txt'
DECISIONS='common/decisions/zz_eu5_shogunate.txt'
EVENTS='events/eu5_shogunate.txt'
PATHS={GLOBAL,JOURNAL,EFFECTS,DECISIONS,EVENTS}

def charter_authority(laws):
    score=50;changes=[]
    adjustments={'established_domains_policy':-10,'jap_buke_shohatto_guidelines':5}
    for policy in laws.values():
        if policy in adjustments:
            score+=adjustments[policy];changes.append({'policy':policy,'authority':adjustments[policy]})
    return score,changes

MEMBER='is_in_power_bloc = yes\npower_bloc = { has_identity = identity:identity_eu5_shogunate }'
ELIGIBLE='''eu5_shogunate_member = yes
is_power_bloc_leader = no
is_at_war = no
has_technology_researched = nationalism
NOT = { has_variable = eu5_shogunate_court }
NOT = { has_variable = eu5_shogunate_seat }
NOT = { has_variable = eu5_shogunate_petition_cooldown }
power_bloc.power_bloc_leader = {
    is_at_war = no
    country_has_monarchy_law = yes
    has_technology_researched = nationalism
    relations:root >= relations_threshold:amicable
    var:eu5_shogunate_authority >= 60
}
OR = { is_subject = no is_subject_of = power_bloc.power_bloc_leader }
'''

def export_runtime(out,blocs):
    if not blocs:return
    globals=[];journals=[]
    for b in blocs:
        base,changes=charter_authority(b['source_constitution'].get('laws',{}))
        b['authority']={'base':base,'source_adjustments':changes,'crisis_threshold':30,'crisis_months_for_exit':12}
        leader=b['leader'];key='je_eu5_shogunate_'+b['source_id']
        for tag in b['members']:
            seed='set_variable = eu5_shogunate_inherited_member\n'
            if tag==b['nominal_shogun']:seed+='set_variable = eu5_shogunate_seat\n'
            if tag in b['imperial_court']:seed+='set_variable = eu5_shogunate_court\n'
            seed+=f'set_variable = {{ name = eu5_shogunate_base_authority value = {base} }}\n'
            seed+=f'set_variable = {{ name = eu5_shogunate_authority value = {base} }}\nset_variable = {{ name = eu5_shogunate_crisis_months value = 0 }}\n'
            # The journal activates through possible; history insertion races
            # the engine's automatic activation and emits duplicate-entry errors.
            globals.append(block('c:'+tag+' ?',seed))
        journals.append(block(key,'''icon = "gfx/interface/icons/event_icons/event_portrait.dds"
group = je_group_foreign_affairs
is_shown_when_inactive = { has_variable = eu5_shogunate_inherited_member }
possible = { eu5_shogunate_member = yes }
complete = { always = no }
invalid = { NOT = { eu5_shogunate_member = yes } }
on_monthly_pulse = { effect = {
    if = { limit = { is_power_bloc_leader = yes } eu5_shogunate_update_authority = yes }
} }
current_value = { value = power_bloc.power_bloc_leader.var:eu5_shogunate_authority }
goal_add_value = { add = 100 }
progressbar = yes
weight = 100
should_be_pinned_by_default_uninvolved_or_context = yes
'''))
        for lang in out.localization:
            zh=lang=='simp_chinese';name=lambda t:out.w.countries[t].get('opening_name_'+lang,out.w.countries[t]['name_'+lang])
            out.localization[lang][key]='幕府秩序与诸藩' if zh else 'Shogunal Order and the Domains'
            out.localization[lang][key+'_reason']=(
                f'转档时幕府席位：{name(b["nominal_shogun"])}；集团领导国：{name(leader)}；天皇朝廷：'+ '、'.join(name(t) for t in b['imperial_court'])+
                f'。这是源存档角色记录，不把邦联宗主自动改称将军。\n\n权威基数 {base}；合法性至少 60：+15，低于 30：−15；地主强大：+10；地主执政：+5；处于战争：−10；废除君主制：−50。每月重算。权威连续 12 个月低于 30、影响力不高于 30 的独立成员可和平退出，其余成员须使用退出集团外交博弈。附庸仍须先解决宗属关系。\n\n民族主义、友好关系和权威至少 60 可解锁版籍奉还申请；双方确认才合并，幕府席位和朝廷不适用。'
                if zh else f'Inherited shogunal seat: {name(b["nominal_shogun"])}; bloc leader: {name(leader)}. Offices, union seniority and regents are separate. Base authority {base}; legitimacy at least 60: +15, below 30: -15; powerful landowners +10, governing landowners +5, war -10, no monarchy -50. After 12 consecutive months below 30, independent members may leave at leverage 30 or less. Otherwise use a diplomatic play. Nationalism, amicable relations and authority 60 unlock a consensual integration petition; court and shogunal seat are excluded.')
            out.localization[lang][key+'_status']='幕府权威（每月更新）' if zh else 'Shogunal authority (monthly)'
        # Preserve the actual shared royal person once, in the union senior.
        # V3 union juniors share their sovereign; duplicating him would invent people.
        person=b.get('shogun_person');sid=out.w.countries[leader]['source_id']
        src=out.w.politics['countries'][sid]
        if (person and person.get('alive') and b.get('shogun_character_basis')=='heir_during_regency'
                and src.get('heir')==b['shogun_character'] and src.get('regent')):
            from m3_world import shift_birth
            from m3_cultures import resolve_culture
            culture,mode=resolve_culture(person['culture'],out.w.profile,out.valid_cultures)
            birth=shift_birth(person['birth_date'],out.w.profile['source_date'],out.w.profile['start_date'])
            first='EU5_SHOGUN_FIRST_'+b['shogun_character'];last='EU5_SHOGUN_LAST_'+b['shogun_character']
            for lang in out.localization:
                out.localization[lang][first]=out.localize(person['first_name'],lang)
                out.localization[lang][last]=out.localize(person.get('last_name') or person.get('dynasty'),lang)
            body=f'first_name = {first}\nlast_name = {last}\nbirth_date = {birth}\nculture = {culture}\nhistorical = yes\nheir = yes\ninterest_group = ig_landowners\nideology = ideology_moderate\ntrait_generation = {{ }}\nsave_scope_as = monarch_scope\n'
            if person.get('female')=='yes':body+='female = yes\n'
            globals.append(block('c:'+leader+' ?',block('create_character',body)+
                'add_regency_modifier = yes\nruler ?= { designate_character_as_regent = { YEARS = 0 } }\n'))
            b['heir_conversion']={'source_character':b['shogun_character'],'target_country':leader,
                'target_birth':birth,'culture':culture,'mode':mode,'native_regency':True,
                'limitation':'V3 personal unions share the senior regent; separate junior regents remain source audit records.'}
    out.write(GLOBAL,block('GLOBAL',''.join(globals)))
    out.write(JOURNAL,''.join(journals))
    out.write(EFFECTS,'''eu5_shogunate_update_authority = {
set_variable = { name = eu5_shogunate_authority value = var:eu5_shogunate_base_authority }
if = { limit = { legitimacy >= 60 } change_variable = { name = eu5_shogunate_authority add = 15 } }
if = { limit = { legitimacy < 30 } change_variable = { name = eu5_shogunate_authority subtract = 15 } }
if = { limit = { ig:ig_landowners = { is_powerful = yes } } change_variable = { name = eu5_shogunate_authority add = 10 } }
if = { limit = { ig:ig_landowners = { is_in_government = yes } } change_variable = { name = eu5_shogunate_authority add = 5 } }
if = { limit = { is_at_war = yes } change_variable = { name = eu5_shogunate_authority subtract = 10 } }
if = { limit = { country_has_monarchy_law = no } change_variable = { name = eu5_shogunate_authority subtract = 50 } }
if = { limit = { var:eu5_shogunate_authority < 0 } set_variable = { name = eu5_shogunate_authority value = 0 } }
if = { limit = { var:eu5_shogunate_authority < 30 } change_variable = { name = eu5_shogunate_crisis_months add = 1 } }
else = { set_variable = { name = eu5_shogunate_crisis_months value = 0 } }
}

# CPB/CMF pattern: a country type transition re-evaluates leadership eligibility.
# The flag stays set until the engine actually processes dissolution.
eu5_shogunate_dissolve = {
set_variable = eu5_shogunate_dissolving
if = { limit = { is_country_type = recognized }
    set_country_type = unrecognized set_country_type = recognized
}
else_if = { limit = { is_country_type = unrecognized }
    set_country_type = recognized set_country_type = unrecognized
}
}
''')
    out.write(DECISIONS,block('eu5_shogunate_petition',
        block('is_shown','eu5_shogunate_member = yes\nis_power_bloc_leader = no\nNOT = { has_variable = eu5_shogunate_court }\nNOT = { has_variable = eu5_shogunate_seat }')+
        block('possible',ELIGIBLE)+block('when_taken','trigger_event = { id = eu5_shogunate.1 popup = yes }')+
        block('ai_chance','value = 0 # Explicit player choice; never silently annex an AI domain.'))+
        block('eu5_shogunate_end_order',block('is_shown','eu5_is_shogunate_leader = yes')+
        block('possible','country_has_monarchy_law = no\nis_at_war = no\nOR = { is_country_type = recognized is_country_type = unrecognized }')+
        block('when_taken','eu5_shogunate_dissolve = yes')+block('ai_chance','value = 100')))
    out.write(EVENTS,'''namespace = eu5_shogunate
eu5_shogunate.1 = {
type = country_event
placement = root
title = eu5_shogunate.1.t
desc = eu5_shogunate.1.d
event_image = { video = "unspecific_signed_contract" }
icon = "gfx/interface/icons/event_icons/waving_flag.dds"
duration = 3
trigger = { eu5_shogunate_can_petition = yes }
option = {
    name = eu5_shogunate.1.a
    save_scope_as = eu5_petitioning_domain
    set_variable = { name = eu5_shogunate_petition_cooldown months = 60 }
    power_bloc.power_bloc_leader = { trigger_event = { id = eu5_shogunate.2 popup = yes } }
}
option = { name = eu5_shogunate.1.b default_option = yes }
}
eu5_shogunate.2 = {
type = country_event
placement = root
title = eu5_shogunate.2.t
desc = eu5_shogunate.2.d
event_image = { video = "unspecific_signed_contract" }
icon = "gfx/interface/icons/event_icons/waving_flag.dds"
duration = 3
trigger = {
    eu5_is_shogunate_leader = yes
    exists = scope:eu5_petitioning_domain
    scope:eu5_petitioning_domain = { is_in_same_power_bloc = root }
}
option = {
    name = eu5_shogunate.2.a
    trigger = {
        is_at_war = no
        country_has_monarchy_law = yes
        var:eu5_shogunate_authority >= 60
        scope:eu5_petitioning_domain = {
            is_at_war = no
            is_in_same_power_bloc = root
            NOT = { has_variable = eu5_shogunate_court }
            NOT = { has_variable = eu5_shogunate_seat }
            OR = { is_subject = no is_subject_of = root }
        }
    }
    annex = scope:eu5_petitioning_domain
    ai_chance = { base = 75 }
}
option = { name = eu5_shogunate.2.b default_option = yes ai_chance = { base = 25 } }
}
''')
    labels={
        'eu5_shogunate_petition':('Petition to Return the Domain','申请版籍奉还'),
        'eu5_shogunate_petition_desc':('Offer full integration into the current bloc leader. Confirmation is required from both countries.','向当前集团领袖申请完全合并；需本国确认与领袖同意。'),
        'eu5_shogunate_end_order':('End the Shogunal Order','终结幕府集团'),
        'eu5_shogunate_end_order_desc':('After abandoning monarchy, dissolve the bloc without annexing or freeing subjects.','领袖废除君主制后解散集团；不吞并诸藩，不自动解除宗属关系。'),
        'eu5_shogunate.1.t':('Return of the Domain','版籍奉还'),
        'eu5_shogunate.1.d':('This petitions the bloc leader to annex our entire country. If accepted, our independent country ceases to exist.','本次申请将把本国全部领土交给集团领袖；一旦对方接受，本国将不再作为单独国家存在。'),
        'eu5_shogunate.1.a':('Confirm and send the petition','确认提交版籍奉还申请'),
        'eu5_shogunate.1.b':('Retain our domain','保留本藩'),
        'eu5_shogunate.2.t':('A Domain Offers Integration','藩国请求合并'),
        'eu5_shogunate.2.d':("[SCOPE.sCountry('eu5_petitioning_domain').GetName] has offered full integration.","[SCOPE.sCountry('eu5_petitioning_domain').GetName]申请将全境并入本国。"),
        'eu5_shogunate.2.a':('Accept integration','接受版籍奉还'),
        'eu5_shogunate.2.b':('Preserve the domain','维持藩国自治'),
        'eu5_shogunate_member':('Member of the inherited Shogunate','继承幕府的成员'),
        'eu5_shogunate_can_petition':('Eligible for consensual domain integration','满足版籍奉还申请条件')}
    for k,v in labels.items():
        for lang,value in zip(('english','simp_chinese'),v):out.localization[lang][k]=value
