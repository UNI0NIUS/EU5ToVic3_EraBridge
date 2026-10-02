"""Source-derived HRE roles and documentary journals; no simulated election effects."""
import re


POLICIES = {
    'perpetual_diet_policy': ('Perpetual Diet', '永久议会'),
    'hre_bi_camerial_imperial_diet_policy': ('Bicameral Imperial Diet', '两院帝国议会'),
    'imperial_circles_established': ('Imperial circles established', '已建立帝国行政圈'),
    'no_landfriede_policy': ('No general imperial peace law', '没有全面帝国禁战法'),
    'no_military_contribution': ('No mandatory military contribution', '不要求军事贡献'),
    'only_treasury_payment': ('Monetary contributions', '金钱贡献'),
    'hre_religion_catholic': ('Catholic imperial religion', '帝国宗教为天主教'),
    'only_imperial_religion_policy': ('Electors restricted to imperial religion', '选帝侯宗教限定为帝国宗教'),
    'emperor_dynastic_preference_policy': ('Dynastic preference in imperial elections', '帝位选举偏好现任皇帝王朝'),
    'free_cities_policy': ('Free cities recognized', '承认自由市制度'),
    'german_free_cities_only_policy': ('German free-city eligibility', '自由市资格限定德意志范围'),
    'golden_bull_policy': ('Golden Bull', '金玺诏书'),
    'hre_agnatic_succession_policy': ('Agnatic imperial succession', '帝位男性继承资格'),
    'electorate_policy': ('Electoral college', '选帝侯团'),
    'princely_bishopric_electorate_policy': ('Ecclesiastical electorates retained', '保留教会选帝侯'),
}


def plan_constitution(org, bloc, tags, market_mode):
    if market_mode not in ('source_only', 'personal_balance'):
        raise ValueError('Unknown HRE market mode')
    if not re.fullmatch(r'\d+', org['id']): raise ValueError('Unsafe organization identifier')
    members = set(bloc['members'])
    source_members = set(org['members'])
    estates = {tags[s] for s in source_members if s in tags} & members
    statuses = org.get('special_statuses', {})
    roles = {}
    for role in ('elector', 'archbishop_elector', 'free_city'):
        source = set(statuses.get(role, [])) & source_members
        roles[role] = {
            'members': sorted({tags[s] for s in source if s in tags and tags[s] in estates}),
            'without_target': sorted(s for s in source if s not in tags),
            'outside_bloc': sorted(s for s in source if s in tags and tags[s] not in estates)}
    source = org.get('constitution')
    laws = source.get('laws', {}) if source else {}
    return {
        'source_id': org['id'], 'source_constitution_present': source is not None,
        'source_constitution': source, 'estate_members': sorted(estates),
        'associated_members': sorted(members - estates),
        'missing_source_members': sorted(source_members - tags.keys()),
        'roles': roles,
        'electors': sorted(set(roles['elector']['members']) | set(roles['archbishop_elector']['members'])),
        'unreviewed_policies': {law: policy for law, policy in laws.items() if policy not in POLICIES},
        'market_mode': market_mode,
        'additional_principles': ['principle_market_unification_2'] if market_mode == 'personal_balance' else [],
        'elections_implemented': False, 'reforms_implemented': False,
        'role_effects': 'documentary_source_snapshot_only',
        'runtime_test': 'pending',
    }


def journal_ids(c):
    return {role: f'je_eu5_hre_{c["source_id"]}_{role}'
            for role in ('charter', 'elector', 'free_city', 'associated')}


def country_record_condition(tags):
    """Auto-activate only for the mapped source identities, including existing saves."""
    from build_m3_world import block
    if not tags: return 'always = no\n'
    return block('OR', ''.join(block('AND', f'exists = c:{tag}\nc:{tag} = THIS')
                              for tag in sorted(set(tags))))


def export_constitutions(exporter, blocs):
    from build_m3_world import block
    journals, history = [], []
    for b in blocs:
        c = b.get('constitution')
        if not c: continue
        ids = journal_ids(c)
        # Seed after POWER_BLOCS initialization, using the native GLOBAL history stage.
        for tag in b['members']:
            entries = [ids['charter']]
            if tag in c['electors']: entries.append(ids['elector'])
            if tag in c['roles']['free_city']['members']: entries.append(ids['free_city'])
            if tag in c['associated_members']: entries.append(ids['associated'])
            history.append(block('c:' + tag + ' ?', ''.join(block('add_journal_entry', 'type = ' + entry) for entry in entries)))
        for role, key in ids.items():
            eligible = {'charter': b['members'], 'elector': c['electors'],
                        'free_city': c['roles']['free_city']['members'],
                        'associated': c['associated_members']}[role]
            condition = country_record_condition(eligible)
            # A hidden inactive entry with no possible block never activated in
            # the 0.3.10 runtime save. Use vanilla's visible+possible lifecycle.
            # These are source records, so withdrawal must not erase them.
            journals.append(block(key,
                'icon = "gfx/interface/icons/event_icons/event_portrait.dds"\n'
                'group = je_group_foreign_affairs\n'
                + block('is_shown_when_inactive', condition)
                + block('possible', condition)
                + block('complete', 'always = no')
                + block('invalid', block('NOT', condition))
                + 'weight = 100\nshould_be_pinned_by_default_uninvolved_or_context = yes\n'))
        titles = {
            'charter': ('Imperial Constitution — Source Record', '帝国宪制：转档制度记录'),
            'elector': ('Imperial Elector — Source Status', '帝国选帝侯：继承身份'),
            'free_city': ('Imperial Free City — Source Status', '帝国自由市：继承身份'),
            'associated': ('Associated Imperial Member', '帝国附随成员'),
        }
        for lang_index, lang in enumerate(('english', 'simp_chinese')):
            country_name = lambda tag: exporter.w.countries[tag]['name_' + lang]
            seats = ('、' if lang_index else ', ').join(country_name(t) for t in c['electors'])
            law_labels = [POLICIES[p][lang_index] for p in (c['source_constitution'] or {}).get('laws', {}).values() if p in POLICIES]
            source_laws = ('；' if lang_index else '; ').join(law_labels)
            n, a, m = len(c['estate_members']), len(c['associated_members']), len(c['missing_source_members'])
            date = exporter.w.politics['date']
            if lang_index:
                market = '本局开局采用个人平衡方案：附庸 I 与市场统一 II，集团加入共同市场。此项是平衡调整，不代表原档已有共同市场；退出后的当前市场请查看市场界面。' if c['additional_principles'] else '本局开局未额外启用共同市场。'
                desc = (f'以下为 {date} 原存档的制度记录，不随战局更新。开局皇帝：{country_name(b["leader"])}。'
                        f'落地帝国成员 {n} 国，附随成员 {a} 国，未落地原成员 {m} 国。'
                        f'\\n\\n选帝侯：{seats or "无有效席位"}。殖民政府及其他附随成员不自动取得选帝席位。'
                        f'\\n\\n原档制度：{source_laws or "尚无已核实记录"}。'
                        '\\n\\n普通成员须针对当前领袖提出退出集团外交博弈，通过战争目标或领袖退让退出；原 EU5 玩家国可通过开局事件获得一次和平退出许可。属国遵循原宗主关系。'
                        f'\\n\\n{market}\\n\\n本页记录历史身份和制度；实际帝位选举、议会改革、贡献征收与额外禁战机制尚未启用，国家政体保持原档转换结果。')
                if c['unreviewed_policies']: desc += '部分皇权条款尚待核实，不据此判定为世袭制。'
                texts = {'charter': desc,
                    'elector': '本国在原档拥有选帝侯身份；该身份来自实际源国家记录，不按 V3 原版国家标签猜测。席位不因属国身份自动移交宗主。本轮仅展示继承身份，实际投票和换帝机制尚未启用。',
                    'free_city': '本国在原档拥有帝国自由市身份。本轮保留身份说明，不额外改变政府、税收或给予禁止吞并的效果。',
                    'associated': '本国在转档开局时随宗主进入帝国集团，但不是原档神罗等级成员。此为开局身份记录，不代表当前仍在集团内；参与集团市场不会自动获得选帝侯或帝国议会席位。'}
            else:
                market = 'Initial personal balance: Vassalization I and Market Unification II establish a shared market. This is not an inherited source customs union. Consult the market interface for current membership after withdrawal.' if c['additional_principles'] else 'No additional common-market principle was enabled at start.'
                desc = (f'Source record at {date}; these figures do not update during play. Initial Emperor: {country_name(b["leader"])}. '
                        f'{n} represented imperial estates, {a} associated members, {m} unrepresented source members.'
                        f'\\n\\nElectors: {seats or "no surviving seats"}. Associated subjects gain no automatic electoral seats.'
                        f'\\n\\nRecorded institutions: {source_laws or "unverified"}.'
                        '\\n\\nOrdinary members must demand Leave Power Bloc and enforce the goal or obtain a backdown. The EU5 player country may obtain one peaceful exit permit at campaign start. Subjects follow their sovereign.'
                        f'\\n\\n{market}\\n\\nElections, parliamentary reforms, contribution collection and additional internal-war restrictions are not implemented. Source governments remain intact.')
                if c['unreviewed_policies']: desc += ' Some imperial-power clauses remain unverified; hereditary succession is not inferred.'
                texts = {'charter': desc,
                    'elector': 'This country held an electoral seat in the source save. Subject status does not automatically transfer its seat to its overlord. This entry records the inherited status; voting and imperial succession mechanics are not implemented.',
                    'free_city': 'This country was a free city in the source save. This documentary status does not change its government or taxes and does not prevent annexation.',
                    'associated': 'At conversion start this country accompanied its sovereign in the bloc but was not a source imperial estate. This historical record does not assert current bloc membership. Market membership grants no automatic electoral or parliamentary seat.'}
            for role, key in ids.items():
                exporter.localization[lang][key] = titles[role][lang_index]
                exporter.localization[lang][key + '_reason'] = texts[role].replace('\\n', '\n')
                exporter.localization[lang][key + '_status'] = ('Source constitution record' if not lang_index else '原档宪制记录')
    if journals:
        exporter.write('common/journal_entries/zz_eu5_hre_constitution.txt', ''.join(journals))
        exporter.write('common/history/global/01_eu5_hre_constitution.txt', block('GLOBAL', ''.join(history)))
