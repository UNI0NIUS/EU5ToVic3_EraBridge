"""Focused regressions for geometry choices, dates, names and source relationships."""
import unittest
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from pdx_text import root
from m3_world import owner_vote, province, shift_birth, assign_country_tags
from build_country_tag_table import name_candidates, normalized
from m3_flags import generated_flag, FlagExporter
from m3_organizations import plan_blocs, plan_treaties
from m3_cultures import resolve_culture
from m3_hre_stability import patch_identities, patch_rules
from build_m3_world import block, entry, history_replace_paths, Exporter
from extract_m3_politics import international_organizations
from build_m2_prototype import allocate


class M3Tests(unittest.TestCase):
    def test_hre_variant_preserves_vanilla_and_only_allows_country_exit_permit(self):
        source = '''identity_sovereign_empire = {
          power_bloc_modifier = { power_bloc_cohesion_per_member_add = -3
            power_bloc_leader_can_make_subjects_bool = yes }
          can_leave = { OR = { is_power_bloc_leader = yes } }
          cohesion = { add = { add = 30 } }
          visible = { has_dlc_feature = power_bloc_features }
          possible = { country_has_monarchy_law = yes }
        }
        identity_trade_league = { can_leave = { always = yes } }'''
        original = root(source).fields(); result = root(patch_identities(source)).fields()
        for key in original:
            self.assertEqual(original[key].text(), result[key].text())
        old = original['identity_sovereign_empire'].fields()
        new = result['identity_eu5_hre_empire'].fields()
        for key in ('cohesion', 'possible'):
            self.assertEqual(old[key].text(), new[key].text())
        gate = new['can_leave'].fields()['custom_tooltip'].fields()
        self.assertEqual(gate, {'text':'eu5_hre_war_exit_tt','is_subject':'no',
                               'is_power_bloc_leader':'no','has_variable':'eu5_hre_exit_permit'})
        self.assertNotIn('has_variable', new['power_bloc_modifier'].text())
        modifiers = new['power_bloc_modifier'].fields()
        self.assertNotIn('power_bloc_cohesion_per_member_add', modifiers)
        self.assertEqual(modifiers['power_bloc_leader_can_make_subjects_bool'], 'yes')

    def test_hre_rank_exception_does_not_relax_bloc_formation(self):
        source = '''can_form_power_bloc = { country_can_form_power_bloc = yes }
        can_lead_power_bloc = { country_rank >= rank_value:major_power }
        is_weak_power_bloc = { power_bloc_is_weak = yes }
        unrelated_rule = { always = no }'''
        original = root(source).fields(); result = root(patch_rules(source)).fields()
        for key in ('can_form_power_bloc', 'unrelated_rule'):
            self.assertEqual(original[key].text(), result[key].text())
        self.assertIn('country_rank >= rank_value:major_power', result['can_lead_power_bloc'].text())
        self.assertIn('eu5_is_chartered_hre_leader = yes', result['can_lead_power_bloc'].text())
        self.assertIn('NOT = { has_identity = identity:identity_eu5_hre_empire }', result['is_weak_power_bloc'].text())

    def test_generated_flags_are_stable_distinct_and_have_emblems(self):
        a = generated_flag('country-one', ['100', '130', '160'])
        self.assertEqual(a, generated_flag('country-one', ['100', '130', '160']))
        self.assertNotEqual(a, generated_flag('country-two', ['100', '130', '160']))
        self.assertIn('colored_emblem', a)
        self.assertNotIn('ce_triangle', a)

    def test_blocs_preserve_subjects_and_reserve_church_leaders(self):
        countries = {t: {'country_type':'recognized'} for t in ('AAA','BBB','CCC','DDD','EEE')}
        tags = dict(zip(('1','2','3','4','5'), countries))
        edges = [{'target_subject':'CCC', 'target_overlord':'BBB', 'target_type':'puppet'},
                 {'target_subject':'EEE', 'target_overlord':'AAA', 'target_type':'colony'}]
        politics = {'date':'1780.7.4', 'international_organizations':[
            {'id':'1','type':'hre','leader':'1','members':['1','2','4']},
            {'id':'2','type':'autocephalous_patriarchate','leader':'2','members':['2','3','4']},
            {'id':'3','type':'autocephalous_patriarchate','leader':'3','members':['3']}]}
        r = plan_blocs(politics,tags,countries,edges)
        self.assertEqual(r['power_blocs'][0]['members'], ['AAA','DDD','EEE'])
        self.assertEqual(r['power_blocs'][1]['members'], ['BBB','CCC'])
        self.assertEqual(r['omitted_organizations'][0]['reason'], 'leader_is_subject')
        self.assertEqual(r['power_blocs'][1]['excluded_members'][0]['tag'], 'DDD')

    def test_ilkhanate_vacuum_does_not_elect_a_substitute(self):
        p={'date':'1780.7.4','international_organizations':[{'id':'9','type':'ilkhanate','leader':None,'members':['1','2']}]}
        cs={t:{'country_type':'recognized'} for t in ('AAA','BBB')}; tags={'1':'AAA','2':'BBB'}
        r=plan_blocs(p,tags,cs,[])
        self.assertFalse(r['power_blocs'])
        self.assertEqual(r['omitted_organizations'][0]['reason'],'source_leadership_vacuum')
        p['international_organizations'][0]['leader']='2'
        self.assertEqual(plan_blocs(p,tags,cs,[])['power_blocs'][0]['leader'],'BBB')

    def test_hre_sovereign_variant_has_primary_vassalization(self):
        p={'date':'1780.7.4','international_organizations':[{'id':'0','type':'hre','leader':'1','members':['1']}]}
        b=plan_blocs(p,{'1':'BOH'},{'BOH':{}},[])['power_blocs'][0]
        self.assertEqual((b['identity'],b['principle']),('identity_eu5_hre_empire','principle_eu5_hre_vassalization_1'))

    def test_culture_mapper_has_no_regional_template_fallback(self):
        import json
        profile=json.loads((Path(__file__).resolve().parents[1]/'config/personal/m3_world.json').read_text(encoding='utf-8'))
        self.assertEqual(resolve_culture('jianghuai_culture',profile,{'han','manchu'})[0],'han')
        self.assertEqual(resolve_culture('smolenskian_culture',profile,{'russian','byelorussian'})[0],'byelorussian')
        self.assertEqual(resolve_culture('tujia_culture',profile,{'eu5_tujia_culture','manchu'})[0],'eu5_tujia_culture')
        with self.assertRaisesRegex(ValueError,'Unreviewed source culture'):
            resolve_culture('unknown',profile,{'manchu'})

    def test_treaties_deduplicate_and_reject_invalid_participants(self):
        rels = [dict(first=a,second=b,type='alliance',mutual=True) for a,b in
                [('1','2'),('2','1'),('1','3'),('1','4')]]
        rels.append(dict(first='1',second='2',type='guarantee',mutual=False))
        countries = {t:{'country_type':'recognized'} for t in ('AAA','BBB','CCC')}
        edges = [{'target_subject':'CCC','target_overlord':'BBB','target_type':'puppet'}]
        r=plan_treaties(rels,dict(zip(('1','2','3'),countries)),countries,edges,{'puppet':False})
        self.assertEqual(len(r['created']),1)
        self.assertEqual(r['created'][0]['binding_months'],1)
        self.assertFalse(r['created'][0]['automatic_expiry'])
        self.assertEqual({x['reason'] for x in r['omitted']},
                         {'duplicate_pair','insufficient_subject_diplomatic_autonomy','country_has_no_target_territory'})

    def test_colonial_generated_charges_clear_canton(self):
        from m3_flags import flag_design
        for i in range(100):
            d=flag_design(str(i),['180','40','40'],'catholic',True)
            for x,y in d['positions']:
                self.assertTrue(x-d['scale'][0]/2 >= .4 or y-d['scale'][1]/2 >= .4)

    def test_explicit_religion_mappings_keep_eastern_traditions_distinct(self):
        import json
        p=Path(__file__).resolve().parents[1] / 'config/personal/m3_world.json'
        aliases=json.loads(p.read_text(encoding='utf-8'))['religion_aliases']
        self.assertEqual(aliases['miaphysite'],'oriental_orthodox')
        self.assertEqual(aliases['shinto'],'shinto')
        self.assertEqual(aliases['sanjiao'],'confucian')
        self.assertEqual(aliases['tibetan_buddhism'],'gelugpa')

    def test_imported_heraldry_namespaces_assets_colors_and_parents(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / 'main_menu'
            for folder in ('common/coat_of_arms/coat_of_arms', 'common/named_colors', 'gfx/coat_of_arms/patterns'):
                (base / folder).mkdir(parents=True)
            (base / 'common/coat_of_arms/coat_of_arms/test.txt').write_text(
                'A = { sub = { parent = B } } B = { pattern = "pattern_test.dds" color1 = red }')
            (base / 'common/named_colors/test.txt').write_text('colors = { red = rgb { 1 0 0 } }')
            (base / 'gfx/coat_of_arms/patterns/pattern_test.dds').write_bytes(b'test-fixture')
            flags = FlagExporter(Path(temp))
            name = flags.import_coa('A')
            self.assertIn('parent = "EU5SRC_', flags.imported[name])
            self.assertEqual(flags.used_colors, {'red'})
            self.assertEqual(len(flags.assets), 1)
            self.assertIn('eu5_m3_pattern_test.dds', next(iter(flags.assets)))

    def test_reviewed_identity_mapping_rejects_same_code_shortcut(self):
        sources = {'1': {'tag': 'BRA'}, '2': {'tag': 'BRU'}, '3': {'tag': 'ITA'}}
        matches = {'2': {'source_tag': 'BRU', 'target_tag': 'BRA'},
                   '3': {'source_tag': 'ITA', 'target_tag': 'ITA'}}
        self.assertEqual(assign_country_tags(sources, set(sources), {'BRA', 'ITA'}, matches, {}),
                         {'1': 'E00', '2': 'BRA', '3': 'ITA'})

    def test_reviewed_tags_must_be_unique_valid_and_same_source_identity(self):
        sources = {'1': {'tag': 'FRA'}, '2': {'tag': 'FRA'}}
        match = {'source_tag': 'FRA', 'target_tag': 'FRA'}
        with self.assertRaisesRegex(ValueError, 'collision'):
            assign_country_tags(sources, set(sources), {'FRA'}, {'1': match, '2': match}, {})
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            assign_country_tags({'1': {'tag': 'ENG'}}, {'1'}, {'FRA'}, {'1': match}, {})
        with self.assertRaisesRegex(ValueError, 'absent'):
            assign_country_tags(sources, {'1'}, set(), {'1': match}, {})

    def test_name_candidates_preserve_georgia_ambiguity(self):
        index = {normalized('Georgia'): {'GEO', 'GRG'}, normalized('格鲁吉亚'): {'GEO'}}
        self.assertEqual(name_candidates(['Georgia', '格鲁吉亚'], index), ['GEO', 'GRG'])

    def test_history_replacement_includes_each_database_and_empty_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            game = Path(temporary)
            for category in ('states', 'countries', 'diplomacy', 'global', 'power_blocs'):
                (game / 'common/history' / category).mkdir(parents=True)
            paths = history_replace_paths(game)
            self.assertEqual(paths, ['common/history/' + c for c in
                                     ('countries', 'diplomacy', 'global', 'power_blocs', 'states')])
            self.assertNotIn('common/history', paths)

    def test_engine_enum_and_effect_tokens_are_not_quoted(self):
        self.assertEqual(entry('set_tax_level', 'medium'), 'set_tax_level = medium\n')
        self.assertEqual(entry('effect_starting_politics_traditional', 'yes'),
                         'effect_starting_politics_traditional = yes\n')
        self.assertEqual(entry('activate_law', 'law_type:law_monarchy'),
                         'activate_law = law_type:law_monarchy\n')
        self.assertEqual(entry('first_name', 'Two Names'), 'first_name = "Two Names"\n')

    def test_shared_province_uses_population_not_anchor_count(self):
        locations = {'a': {'owner': 1, 'population_persons': '20.00'},
                     'b': {'owner': 2, 'population_persons': '11.00'},
                     'c': {'owner': 2, 'population_persons': '10.00'}}
        self.assertEqual(owner_vote(['a', 'b', 'c'], locations, {'1', '2'}), '2')

    def test_repeated_source_anchors_do_not_multiply_weight(self):
        locations = {'a': {'owner': 1, 'population_persons': '20'}, 'b': {'owner': 2, 'population_persons': '21'}}
        self.assertEqual(owner_vote(['a', 'a', 'b'], locations, {'1', '2'}), '2')

    def test_unowned_locations_do_not_create_source_country(self):
        self.assertIsNone(owner_vote(['a'], {'a': {'owner': -1, 'population_persons': '5'}}, {'1'}))

    def test_tied_owner_is_stable_numeric_id(self):
        locations = {n: {'owner': n, 'population_persons': '0'} for n in ('10', '2')}
        self.assertEqual(owner_vote(['10', '2'], locations, {'10', '2'}), '2')

    def test_province_hex_is_case_insensitive(self):
        self.assertEqual(province('xf0d080'), province('xF0D080'))

    def test_birth_shift_preserves_days_alive_across_leap_years(self):
        birth = shift_birth('1690.10.31', '1780.7.4', '1836.1.1')
        shifted = date(*map(int, birth.split('.')))
        self.assertEqual(date(1836, 1, 1)-shifted, date(1780, 7, 4)-date(1690, 10, 31))

    def test_optional_country_scope_round_trip(self):
        text = block('c:ITA ?', 'activate_law = law_type:law_presidential_republic')
        self.assertIn('c:ITA ?=', text)
        self.assertEqual(list(root(text).fields()), ['c:ITA'])

    def test_union_uses_explicit_senior_not_list_order(self):
        org = root('database = { 5 = { type = union all_members = { 10 20 } countries_with_special_status_v2 = { senior_partner = { 20 } junior_partner = { 10 } } } }')
        self.assertEqual(international_organizations(org)[0]['senior'], ['20'])

    def test_equal_union_does_not_invent_a_senior(self):
        org = root('database = { 5 = { type = union all_members = { 10 20 } } }')
        self.assertEqual(international_organizations(org)[0]['senior'], [])

    def test_template_pop_split_preserves_small_minorities(self):
        parts = allocate(3, {'ITA': 8, 'PAP': 1})
        self.assertEqual(sum(parts.values()), 3)
        self.assertEqual(parts, {'ITA': 3, 'PAP': 0})

    def test_localization_aliases_and_compound_names(self):
        obj = Exporter.__new__(Exporter)
        obj.source_loc = {'english': {'name_one': 'One', 'name_two': 'Two', 'alias': '$name_one$'}, 'simp_chinese': {}}
        self.assertEqual(obj.localize('alias', 'simp_chinese'), 'One')
        self.assertEqual(obj.localize('name_one.name_two', 'english'), 'One Two')


if __name__ == '__main__':
    unittest.main()
