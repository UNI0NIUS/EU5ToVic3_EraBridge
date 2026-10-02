"""Independent read-back of a generated M3 mod and the installed regional templates."""
import argparse
from collections import Counter
from datetime import date
import json
import re
from pathlib import Path

from pdx_text import Object, root
from build_m2_prototype import objects, strings, scalars, walk
from m3_world import digest, fields, load_json, province


def doc(path):
    return root(path.read_text(encoding='utf-8-sig'))


def gather_pops(paths):
    counts = Counter()
    for path in paths:
        for _, container in objects(doc(path)):
            for state, obj in objects(container):
                for tag, sub in objects(obj):
                    for key, pop in objects(sub):
                        if key == 'create_pop':
                            p = scalars(pop)
                            counts[state, p.get('culture'), p.get('religion')] += int(p['size'])
    return counts


def gather_buildings(paths):
    counts = Counter()
    def recurse(obj, state=None):
        for key, o in objects(obj):
            if key.startswith('s:'): yield from recurse(o, key)
            elif key == 'create_building': yield state, o
            else: yield from recurse(o, state)
    for path in paths:
        for s, o in recurse(doc(path)):
            f = fields(o)
            counts[s, f['building']] += int(f.get('level', 0))
            counts[s, f['building']] += sum(int(scalars(v)['levels']) for k, v in walk(o) if 'levels' in scalars(v))
    return counts


def verify_organizations(mod, game, report, countries, parents):
    """Read emitted scripts, verify exclusive membership and exact treaty terms."""
    if 'organizations' not in report: return {}
    identities = {k for base in (game, mod) for p in (base/'common/power_bloc_identities').glob('*.txt') for k,o in objects(doc(p))}
    principles = {k for base in (game, mod) for p in (base/'common/power_bloc_principles').glob('*.txt') for k,o in objects(doc(p))}
    expected = {b['leader']:b for b in report['organizations']['power_blocs']}
    found, assigned = set(), {}
    for scope,country in objects(fields(doc(mod/'common/history/power_blocs/00_eu5_world.txt'))['POWER_BLOCS']):
        leader = scope[2:]; assert leader in expected and leader not in parents
        b = expected[leader]; f = fields(fields(country)['create_power_bloc'])
        if b.get('stability'):
            assert b['source_type'] == 'hre'
            charter = fields(fields(country)['power_bloc'])
            assert charter['add_cohesion_number'] == '50'
            extras = [v for k,v in fields(country)['power_bloc'].entries() if k == 'add_principle']
            assert extras == b.get('constitution', {}).get('additional_principles', [])
            assert set(charter) <= {'add_cohesion_number', 'add_principle'}
            assert all(p in principles for p in extras)
            assert len(extras) + 1 <= 4
        else:
            assert 'power_bloc' not in fields(country), 'Charter leaked into unrelated bloc'
        assert f['identity'] == b['identity'] and f['identity'] in identities
        assert f['principle'] == b['principle'] and f['principle'] in principles
        direct = {v[2:] for k,v in fields(country)['create_power_bloc'].entries() if k == 'member'}
        assert direct == set(b['direct_members']) and not (direct & parents.keys())
        members = direct | {leader}
        while True:
            expanded = members | {s for s,p in parents.items() if p in members}
            if expanded == members: break
            members = expanded
        assert members == set(b['members']) and not (members & assigned.keys())
        assert members <= countries.keys()
        assigned.update({t:leader for t in members}); found.add(leader)
    assert found == expected.keys()
    if any(b.get('stability') for b in expected.values()):
        identity_path = 'common/power_bloc_identities/00_power_bloc_identities.txt'
        vanilla = fields(doc(game/identity_path)); actual = fields(doc(mod/identity_path))
        identity = 'identity_eu5_hre_empire'
        assert set(actual) - set(vanilla) == {identity}
        for key in vanilla: assert vanilla[key].text() == actual[key].text()
        old, new = fields(vanilla['identity_sovereign_empire']), fields(actual[identity])
        value_text = lambda v: v.text() if isinstance(v, Object) else v
        for key in old:
            if key not in ('can_leave', 'power_bloc_modifier', 'visible'):
                assert value_text(old[key]) == value_text(new[key])
        gate = fields(fields(new['can_leave'])['custom_tooltip'])
        assert gate == {'text':'eu5_hre_war_exit_tt', 'is_subject':'no',
                        'is_power_bloc_leader':'no', 'has_variable':'eu5_hre_exit_permit'}
        # Variables are supported in this COUNTRY can_leave scope, never the bloc scope.
        assert 'has_variable' not in new['power_bloc_modifier'].text()
        assert fields(new['visible']) == {'always':'no'}
        old_mod, new_mod = fields(old['power_bloc_modifier']), fields(new['power_bloc_modifier'])
        assert old_mod.pop('power_bloc_cohesion_per_member_add') == '-3'
        assert new_mod.pop('power_bloc_cohesion_add') == '15'
        assert old_mod == new_mod
        groups_path = 'common/power_bloc_principle_groups/00_power_bloc_principle_groups.txt'
        vg, mg = fields(doc(game/groups_path)), fields(doc(mod/groups_path))
        for key in vg:
            if key != 'principle_group_vassalization': assert vg[key].text() == mg[key].text()
        group = fields(mg['principle_group_eu5_hre_vassalization'])
        assert group['primary_for_identity'] == identity and group['unlocking_identity'] == identity
        assert fields(mg['principle_group_vassalization'])['blocking_identity'] == identity
        vp = fields(doc(game/'common/power_bloc_principles/00_power_bloc_principles.txt'))
        mp = fields(doc(mod/'common/power_bloc_principles/zz_eu5_hre_vassalization.txt'))
        assert strings(group['levels']) == list(mp)
        for i in range(1,4):
            original = vp[f'principle_vassalization_{i}'].text().replace('identity:identity_sovereign_empire', 'identity:' + identity)
            # Whitespace from block formatting is irrelevant; all effects are unchanged.
            assert re.sub(r'\s+', '', original) == re.sub(r'\s+', '', mp[f'principle_eu5_hre_vassalization_{i}'].text())
        # War exit is a separate native goal, not dependent on our can_leave gate.
        war = fields(fields(doc(game/'common/war_goal_types/12_leave_power_bloc.txt'))['leave_power_bloc'])
        assert war['kind'] == 'leave_power_bloc'
        assert fields(war['valid'])['is_subject'] == 'no'
        assert 'can_leave_power_bloc' not in war['valid'].text()
        rules_path = 'common/scripted_rules/00_scripted_rules.txt'
        old, new = fields(doc(game/rules_path)), fields(doc(mod/rules_path))
        assert old.keys() == new.keys()
        for key in old:
            if key not in ('can_lead_power_bloc', 'is_weak_power_bloc'):
                assert old[key].text() == new[key].text()
        trigger = fields(doc(mod/'common/scripted_triggers/zz_eu5_hre_charter.txt'))['eu5_is_chartered_hre_leader']
        assert fields(trigger)['is_subject'] == 'no'
        assert fields(trigger)['is_power_bloc_leader'] == 'yes'
        assert fields(fields(trigger)['power_bloc']) == {'has_identity':'identity:identity_eu5_hre_empire'}
        assert 'has_variable' not in trigger.text()
    if any(b.get('constitution') for b in expected.values()):
        journals = fields(doc(mod/'common/journal_entries/zz_eu5_hre_constitution.txt'))
        initialization = fields(doc(mod/'common/history/global/01_eu5_hre_constitution.txt'))['GLOBAL']
        actual_entries = {tag[2:]: [fields(v)['type'] for k,v in obj.entries() if k == 'add_journal_entry']
                          for tag,obj in objects(initialization)}
        expected_entries, expected_journal_countries = {}, {}
        for b in expected.values():
            if not b.get('constitution'): continue
            c = b['constitution']; prefix = 'je_eu5_hre_' + b['source_id'] + '_'
            expected_journal_countries.update({prefix + 'charter': set(b['members']),
                prefix + 'elector': set(c['electors']), prefix + 'free_city': set(c['roles']['free_city']['members']),
                prefix + 'associated': set(c['associated_members'])})
            assert set(c['estate_members']) == set(b['source_members_surviving']) & set(b['members'])
            assert set(c['associated_members']) == set(b['members']) - set(c['estate_members'])
            assert not set(c['electors']) - set(c['estate_members'])
            assert set(c['electors']) == set(c['roles']['elector']['members']) | set(c['roles']['archbishop_elector']['members'])
            assert not c['elections_implemented'] and not c['reforms_implemented']
            assert len(c['electors']) == len(set(c['electors']))
            if c['market_mode'] == 'personal_balance':
                assert c['additional_principles'] == ['principle_market_unification_2']
                p = fields(doc(game/'common/power_bloc_principles/00_power_bloc_principles.txt'))['principle_market_unification_2']
                assert fields(fields(p)['power_bloc_modifier'])['power_bloc_customs_union_bool'] == 'yes'
            else:
                assert not c['additional_principles']
            for tag in b['members']:
                entries = [prefix + 'charter']
                if tag in c['electors']: entries.append(prefix + 'elector')
                if tag in c['roles']['free_city']['members']: entries.append(prefix + 'free_city')
                if tag in c['associated_members']: entries.append(prefix + 'associated')
                expected_entries[tag] = entries
        assert actual_entries == expected_entries
        assert {k for entries in actual_entries.values() for k in entries} <= journals.keys()
        for key,obj in journals.items():
            f = fields(obj)
            assert fields(f['complete']) == {'always':'no'}
            assert not any(k in f for k in ('on_monthly_pulse', 'on_yearly_pulse', 'immediate', 'on_complete', 'timeout'))
            assert 'power_bloc' not in f['invalid'].text(), 'Source record disappears after withdrawal'
            assert f['possible'].text() == f['is_shown_when_inactive'].text()
            gates = fields(f['possible'])
            if expected_journal_countries[key]:
                actual_countries = set()
                for name, gate in objects(gates['OR']):
                    gf = fields(gate); assert name == 'AND'
                    target = gf['exists']; assert gf[target] == 'THIS'
                    actual_countries.add(target[2:])
                assert actual_countries == expected_journal_countries[key]
            else: assert gates == {'always': 'no'}
            for lang in ('english', 'simp_chinese'):
                loc = (mod/f'localization/{lang}/eu5_world_l_{lang}.yml').read_text(encoding='utf-8-sig')
                for suffix in ('', '_reason', '_status'):
                    assert '\n ' + key + suffix + ':0 ' in loc
    player_exit = report['organizations'].get('source_player_exit', {})
    if player_exit.get('enabled'):
        from m3_hre_player_exit import patch_invite, patch_on_actions
        t = player_exit['target']
        assert t not in parents
        assert any(t in b['members'] and t != b['leader'] for b in expected.values())
        events = fields(doc(mod/'events/eu5_hre_player_exit.txt'))
        assert events['namespace'] == 'eu5_hre_exit'
        choice = fields(events['eu5_hre_exit.1'])
        assert ('c:' + t, 'THIS') in list(choice['trigger'].entries())
        options = [fields(v) for k,v in events['eu5_hre_exit.1'].entries() if k == 'option']
        assert len(options) == 2
        assert [int(fields(o['ai_chance'])['base']) for o in options] == [player_exit['ai_leave_percent'],100-player_exit['ai_leave_percent']]
        leave_vars = [fields(v) for k,v in next(v for k,v in events['eu5_hre_exit.1'].entries() if k == 'option').entries() if k == 'set_variable' and isinstance(v,Object)]
        assert leave_vars == [{'name':'eu5_hre_exit_permit','value':'yes','days':'365'}]
        for path,transform in [('common/diplomatic_actions/28_invite_to_power_bloc.txt',patch_invite),
                               ('common/on_actions/00_code_on_actions.txt',patch_on_actions)]:
            assert (mod/path).read_text(encoding='utf-8-sig') == transform((game/path).read_text(encoding='utf-8-sig'))
        all_exit_text = ''.join((mod/path).read_text(encoding='utf-8-sig') for path in (
            'events/eu5_hre_player_exit.txt','common/scripted_effects/zz_eu5_hre_player_exit.txt',
            'common/on_actions/zz_eu5_hre_player_exit.txt'))
        assert not any(token in all_exit_text for token in ('annex', 'remove_diplomatic_pact', 'create_diplomatic_play', 'join_power_bloc ='))
        assert 'remove_variable = eu5_hre_exit_permit' in all_exit_text
        assert 'has_variable = eu5_hre_exit_offered' in all_exit_text
        assert 'is_player = yes' in all_exit_text
        assert 'eu5_hre_exit_check = yes' in fields(events['eu5_hre_exit.6'])['immediate'].text()
        window = fields(fields(doc(mod/'common/journal_entries/zz_eu5_hre_exit_window.txt'))['je_eu5_hre_exit_window'])
        assert fields(window['possible']) == {'exists':f'c:{t}', f'c:{t}':'THIS', 'has_variable':'eu5_hre_exit_waiting'}
        assert fields(window['is_shown_when_inactive']) == fields(window['possible'])
        for lang in ('english','simp_chinese'):
            loc=(mod/f'localization/{lang}/eu5_world_l_{lang}.yml').read_text(encoding='utf-8-sig')
            for i in range(1,6):
                for suffix in ('t','d','f'): assert f' eu5_hre_exit.{i}.{suffix}:0 ' in loc
    expected_treaties = {t['name']:t for t in report['treaties']['created']}
    found_treaties, pairs = set(), set()
    for key,treaty in objects(fields(doc(mod/'common/history/treaties/00_eu5_world.txt'))['TREATIES']):
        assert key == 'create_treaty'
        f=fields(treaty); t=expected_treaties[f['name']]
        a,b = f['first_country'][2:],f['second_country'][2:]
        assert (a,b) == (t['target_first'],t['target_second'])
        assert a in countries and b in countries and a != b
        assert tuple(sorted((a,b))) not in pairs
        assert fields(f['binding_period']) == {'months':'1'}
        assert f['entered_into_force_on'] == report['start_date'] and f['is_draft'] == 'no'
        articles = [fields(v)['article'] for k,v in f['articles_to_create'].entries() if isinstance(v,Object)]
        assert articles == ['defensive_pact']
        assert not any(k in f for k in ('expiration_date','expiry_date','duration'))
        found_treaties.add(f['name']); pairs.add(tuple(sorted((a,b))))
    assert found_treaties == expected_treaties.keys()
    prerequisites = fields(doc(mod/'common/history/countries/01_eu5_diplomatic_prerequisites.txt'))['COUNTRIES']
    researched = {tag[2:] for tag,c in objects(prerequisites)
                  if ('add_technology_researched','international_relations') in list(c.entries())}
    assert {t for pair in pairs for t in pair} <= researched
    religion_defs = {k for p in (game/'common/religions').glob('*.txt') for k,o in objects(doc(p))}
    for tag,c in countries.items():
        if c['source_id']:
            assert c['religion'] in religion_defs
            assert c['religion_mapping'] in ('source_exact','explicit_alias')
            if c['source_religion']=='miaphysite': assert c['religion']=='oriental_orthodox'
    return {'power_blocs':len(found), 'bloc_members':len(assigned), 'defensive_treaties':len(pairs),
            'treaty_binding_months':1, 'treaty_automatic_expiry':False, 'state_religions':'explicitly_mapped'}


def verify_cultures(mod, game, report):
    if 'custom_cultures' not in report:return {}
    def effective(directory):
        paths={p.relative_to(base).as_posix():p for base in (game,mod) for p in (base/directory).glob('*.txt')}
        return {k:o for p in paths.values() for k,o in objects(doc(p))}
    definitions=effective('common/country_definitions')
    cultures=effective('common/cultures'); traits=effective('common/discrimination_traits');groups=effective('common/discrimination_trait_groups')
    for tag,c in report['countries'].items():
        actual=strings(fields(definitions[tag])['cultures'])
        assert actual==c['cultures'],('Primary cultures differ in effective game files',tag,actual,c['cultures'])
        assert all(t in cultures for t in actual)
        if c['source_id']:
            assert c['culture_mapping'] in ('same_key','same_key_without_suffix','reviewed_alias','preserved_custom_identity')
    for c in report['custom_cultures']:
        f=fields(cultures[c['target']])
        assert f['heritage']==c['heritage'] and f['language']==c['language']
        for key,typ in [('heritage','heritage'),('language','language')]:
            t=fields(traits[f[key]])
            assert t['type']==typ and t['trait_group'] in groups
    names=effective('common/dynamic_country_names')
    for tag in report['source_name_overrides']:
        entries=[fields(o) for k,o in objects(names[tag]) if k=='dynamic_country_name']
        overrides=[f for f in entries if f.get('name')=='EU5_SOURCE_NAME_'+tag]
        assert len(overrides)==1 and overrides[0]['priority']=='10000'
        assert overrides[0]['is_main_tag_only']=='yes'
        assert list(overrides[0]['trigger'].entries())==[]
    if report['countries'].get('CHI',{}).get('source_tag')=='MNG':
        assert strings(fields(definitions['CHI'])['cultures'])==['han']
        flag=next(f for f in report['flags'] if f['tag']=='CHI')
        assert flag['source_flag_key']=='CHI_Ming' and flag['mode']=='imported_eu5_definition'
    for p,sha in report['source_culture_inputs_sha256'].items():assert digest(Path(p))==sha
    return {'primary_cultures':'all_effective_definitions_match','regional_culture_fallbacks':0,
            'custom_source_cultures':len(report['custom_cultures']),'source_name_overrides':len(report['source_name_overrides'])}


def verify(run, game):
    report = load_json(run / 'conversion_report.json')
    mod = Path(report['mod_directory'])
    replaced = set(load_json(mod / '.metadata/metadata.json')['game_custom_data']['replace_paths'])
    # Inspect the effective file set, not only the newly generated history scripts.
    # A parent-only replace path allowed vanilla state history to overwrite M3.
    vanilla_history = list((game / 'common/history').rglob('*.txt'))
    leaked_history = [p.relative_to(game).as_posix() for p in vanilla_history
                      if p.parent.relative_to(game).as_posix() not in replaced
                      and not (mod / p.relative_to(game)).exists()]
    assert not leaked_history, ('Vanilla history still loads', len(leaked_history), leaked_history[:10])
    for path, signature in report['output_sha256'].items():
        assert digest(mod / path) == signature, ('Output hash changed', path)
        if Path(path).suffix in ('.txt', '.yml'):
            assert (mod / path).read_bytes().startswith(b'\xef\xbb\xbf'), ('Missing UTF-8 BOM', path)
    country_text = (mod / 'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')
    tax_values = re.findall(r'^\s*set_tax_level\s*=\s*(\S+)', country_text, re.M)
    assert all(v in {'very_low', 'low', 'medium', 'high', 'very_high'} for v in tax_values), ('Invalid tax enum', tax_values)
    for path, signature in report['target_inputs_sha256'].items():
        assert digest(game / path) == signature, ('Target input changed', path)
    countries = report['countries']
    culture_checks = verify_cultures(mod,game,report)
    if 'flags' in report:
        coa_objects = dict(objects(doc(mod / 'common/coat_of_arms/coat_of_arms/zz_eu5_world.txt')))
        flag_defs = {k:o for p in (mod/'common/flag_definitions').glob('*.txt') for k,o in objects(doc(p))}
        flag_rows = {r['tag']: r for r in report['flags']}
        assert len(flag_rows) == sum(bool(c['source_id']) or bool(c.get('generated_uncolonized')) for c in countries.values())
        for tag, row in flag_rows.items():
            if row['mode'] == 'existing_v3_identity_flag': continue
            assert tag in flag_defs, ('Custom country lacks flag definition', tag)
            definition = fields(fields(flag_defs[tag])['flag_definition'])
            assert definition['coa'] in coa_objects
            if countries[tag]['country_type'] == 'colonial':
                assert definition.get('allow_overlord_canton') == 'yes'
        for name, coa in coa_objects.items():
            for _, node in [('', coa), *list(walk(coa))]:
                for key, value in node.entries():
                    if key == 'parent': assert value in coa_objects, ('Missing flag parent', name, value)
                    if key in ('texture', 'pattern') and isinstance(value, str):
                        folders = ('patterns',) if key == 'pattern' else ('colored_emblems', 'textured_emblems')
                        assert any((base / 'gfx/coat_of_arms' / folder / value).is_file()
                                   for base in (mod, game) for folder in folders), ('Missing flag texture', name, value)
        for path, source in report['flag_asset_sources'].items():
            assert digest(mod / path) == source['sha256'] == digest(Path(source['source']))
    ownership, substates = {}, set()
    for state, obj in objects(fields(doc(mod / 'common/history/states/00_eu5_world.txt'))['STATES']):
        for key, sub in objects(obj):
            if key != 'create_state': continue
            f = fields(sub); tag = f['country'][2:]
            assert tag in countries
            if countries[tag].get('generated_uncolonized'):
                assert f.get('state_type')=='unincorporated',('Tribal state must be unincorporated',tag)
            substates.add((state[2:], tag))
            for p in strings(f['owned_provinces']):
                assert p not in ownership, ('Duplicate province', p)
                ownership[p] = (state[2:], tag)
    expected = {province(p): s for path in (game / 'map_data/state_regions').glob('*.txt')
                for s, o in objects(doc(path)) if s in {state for state, tag in substates}
                for p in strings(fields(o)['provinces'])}
    assert set(expected) == set(ownership)
    assert all(ownership[p][0] == state for p, state in expected.items())
    assert all((c['capital'], tag) in substates for tag, c in countries.items())
    native=report.get('uncolonized_tribes')
    native_check={}
    if native:
        from types import SimpleNamespace
        from m3_uncolonized import connected_groups,province_land_edges
        for path,sha in native['input_sha256'].items():assert digest(Path(path))==sha,('Tribal input changed',path)
        paths={p.name:p for base in (game,mod) for p in sorted((base/'common/country_definitions').glob('*.txt'))}
        definitions={k:fields(o) for p in paths.values() for k,o in objects(doc(p))}
        finalized=report.get('terrain_finalization') or {};aliases=dict(finalized.get('country_aliases',{}))
        frontier=report.get('frontier_finalization') or {};frontier_aliases=frontier.get('country_aliases',{})
        aliases={k:frontier_aliases.get(v,v) for k,v in aliases.items()};aliases.update(frontier_aliases)
        reviewed_islands={r['province'] for r in frontier.get('reviewed_islands',[])}
        for r in frontier.get('changes',[]):assert ownership[r['province']]==(r['state'],r['to'])
        generated={t for t,c in countries.items() if c.get('generated_uncolonized')};seen=set();identity={};groups={}
        for t in generated:
            c=countries[t]
            assert definitions[t]['country_type']=='decentralized'
            assert strings(definitions[t]['cultures'])==[c['culture']]
            assert definitions[t]['capital']==c['capital']
            groups[t]=set()
        for r in native['transfers']:
            p=r['province'];t=aliases.get(r['to'],r['to']);assert p not in seen;seen.add(p)
            assert ownership[p]==(r['state'],t)
            assert r['target_primary_culture']==native['countries'][r['to']]['culture']
            if t in generated:identity[p]=r['target_primary_culture'];groups[t].add(p)
        if finalized:
            for p,(s,t) in ownership.items():
                if t in generated and p not in reviewed_islands:identity[p]=countries[t]['culture'];groups[t].add(p);seen.add(p)
        graph_world=SimpleNamespace(game=game,owners={s:{p:t for p,(ss,t) in ownership.items() if s==ss} for s in {ss for ss,t in ownership.values()}},province_state=expected)
        edges=province_land_edges(graph_world,run.parent/'tribal_verify_land_edges.json')
        components={frozenset(ps) for ps in connected_groups(identity,edges)}
        assert components=={frozenset(ps) for ps in groups.values()},'Tribal countries are not maximal same-culture land components'
        assert not generated & {e[k] for e in report['subjects']+report['vanilla_fallback_subjects'] for k in ('target_subject','target_overlord')}
        native_check={'uncolonized_tribal_countries':len(generated),'uncolonized_provinces':len(seen),
                      'uncolonized_connected_components_verified':True,'uncolonized_native_decentralized_type_verified':True}
    assert gather_pops((game / 'common/history/pops').glob('*.txt')) == gather_pops((mod / 'common/history/pops').glob('*.txt'))
    assert gather_buildings((game / 'common/history/buildings').glob('*.txt')) == gather_buildings((mod / 'common/history/buildings').glob('*.txt'))
    law_defs = {k for p in (game / 'common/laws').glob('*.txt') for k, o in objects(doc(p))}
    laws = {}
    for tag, country in objects(fields(doc(mod / 'common/history/countries/00_eu5_world.txt'))['COUNTRIES']):
        values = [v.removeprefix('law_type:') for k, v in country.entries() if k == 'activate_law']
        assert all(l in law_defs for l in values), ('Unknown law', tag)
        c = countries[tag[2:]]
        if c['source_id']:
            assert values[-2:] == [c['government_law'], c['power_law']]
            if c['source_government'] == 'republic' and c['country_type'] not in ('colonial', 'company'):
                assert c['government_law'] == 'law_presidential_republic'
        laws[tag[2:]] = values
    edges = []
    for tag, country in objects(fields(doc(mod / 'common/history/diplomacy/00_eu5_subjects.txt'))['DIPLOMACY']):
        for k, pact in objects(country):
            f = fields(pact); edges.append((tag[2:], f['country'][2:], f['type']))
    assert len({s for o, s, kind in edges}) == len(edges), 'Duplicate target overlords'
    expected_edges = {(e['target_overlord'], e['target_subject'], e['target_type']) for e in report['subjects'] + report['vanilla_fallback_subjects']}
    assert set(edges) == expected_edges
    parents = {s: o for o, s, kind in edges}
    for s in parents:
        seen = set(); cur = s
        while cur in parents:
            assert cur not in seen, 'Dependency cycle'
            seen.add(cur); cur = parents[cur]
    organization_checks = verify_organizations(mod, game, report, countries, parents)
    for tag, c in countries.items():
        if c['source_id'] and c['country_type'] == 'colonial':
            assert c['government_law'] == 'law_colonial_administration'
            assert any(s == tag and kind == 'colony' for o, s, kind in edges)
    units, ships = Counter(), Counter()
    for tag, country in objects(fields(doc(mod / 'common/history/military_formations/00_eu5_world.txt'))['MILITARY_FORMATIONS']):
        for key, obj in walk(country):
            f = scalars(obj)
            if key == 'combat_unit':
                assert (f['state_region'][2:], tag[2:]) in substates, ('Army in foreign substate', tag, f)
                units[f['type']] += int(f['count'])
            if key in ('ship', 'create_ship'):
                ships[f['type']] += int(f.get('count', 1))
    original_units, original_ships = Counter(), Counter()
    for p in (game / 'common/history/military_formations').glob('*.txt'):
        for key, obj in walk(doc(p)):
            f = scalars(obj)
            if key == 'combat_unit': original_units[f['type']] += int(f['count'])
            if key in ('ship', 'create_ship'): original_ships[f['type']] += int(f.get('count', 1))
    assert units == original_units
    assert ships == original_ships
    parse_date = lambda s: date(*map(int, s.split('.')[:3]))
    for person in report['rulers']:
        assert parse_date(report['source_date']) - parse_date(person['source_birth']) == parse_date(report['start_date']) - parse_date(person['target_birth'])
    # Sources not represented by a target province are explicitly accounted for.
    assert report['validation']['represented_source_countries'] + len(report['omitted_countries']) == report['validation']['source_countries_with_land']
    result = {'status': 'passed', 'land_provinces': len(ownership), 'countries': len(countries), 'subject_edges': len(edges),
              'population_by_state_culture_religion': 'exact', 'building_levels_by_state_type': 'exact',
              'land_units_by_type': 'exact', 'ships_by_type': 'exact', 'ruler_age': 'exact',
              'vanilla_history_files_excluded': len(vanilla_history), 'runtime_test': 'pending'}
    result.update(organization_checks)
    result.update(culture_checks)
    result.update(native_check)
    (run / 'independent_verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path)
    p.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    a = p.parse_args(); print(json.dumps(verify(a.run, a.game)))
