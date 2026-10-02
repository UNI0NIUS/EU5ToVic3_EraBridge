import unittest
from pdx_text import root
from m4_demographics import culture_resolution,religion_resolution,round_groups
from m3_world import load_json
from pathlib import Path

PROFILE=load_json(Path(__file__).resolve().parents[1]/'config/personal/m4_demographics.json')


class DemographicTests(unittest.TestCase):
    def test_chinese_yue_wu_uses_language_and_protects_minorities(self):
        wu=root('language = wu_language culture_groups = { chinese_group confucian_group }').fields()
        self.assertEqual(culture_resolution('yue_wu_culture',wu,None,PROFILE,{'han','yue'})[0],'han')
        yue=root('language = yue_language culture_groups = { chinese_group }').fields()
        self.assertEqual(culture_resolution('yuehai_culture',yue,None,PROFILE,{'han','yue'})[0],'yue')
        chinese=root('language = northern_mandarin_dialect culture_groups = { chinese_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('hui_muslim_culture',chinese,None,PROFILE,{'han'})
        hui=root('language = northern_mandarin_dialect culture_groups = { chinese_group confucian_group }').fields()
        self.assertEqual(culture_resolution('hui_muslim_culture',hui,None,PROFILE,{'eu5_resident_hui_muslim_culture'})[0],'eu5_resident_hui_muslim_culture')
        self.assertEqual(culture_resolution('qayfengi',chinese,None,PROFILE,{'han'})[0],'')

    def test_no_language_only_or_owner_identity_fallback(self):
        nubian=root('language = nubian_language').fields()
        with self.assertRaises(ValueError):culture_resolution('nubian',nubian,None,PROFILE,{'nuba'})
        self.assertEqual(culture_resolution('nubian',nubian,None,PROFILE,{'eu5_resident_nubian'})[0],'eu5_resident_nubian')
        self.assertEqual(culture_resolution('unconfigured_nubian_speaker',nubian,None,PROFILE,{'nuba'})[0],'')
        wrong_group=root('language = wu_language culture_groups = { other_group }').fields()
        self.assertEqual(culture_resolution('test',wrong_group,None,PROFILE,{'han'})[0],'')

    def test_existing_custom_identity_is_preserved(self):
        self.assertEqual(culture_resolution('test',{},('eu5_test','custom'),PROFILE,{'eu5_test'})[:2],('eu5_test','custom'))

    def test_named_rakhine_compaction_does_not_spread_to_other_burmese_speakers(self):
        definition = root('language = burmese_language culture_groups = { tibeto_burman_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('rakhine_culture',definition,None,PROFILE,{'eu5_resident_rakhine_culture'})
        target = 'burmese'
        self.assertEqual(culture_resolution('rakhine_culture',definition,None,PROFILE,{target})[0],target)
        self.assertEqual(culture_resolution('another_culture',definition,None,PROFILE,{target})[0],'')

    def test_resident_custom_identity_rejects_source_drift(self):
        for text in ('language = burmese_language','language = other culture_groups = { tibeto_burman_group }'):
            with self.assertRaises(ValueError):
                culture_resolution('rakhine_culture',root(text).fields(),None,PROFILE,{'eu5_resident_rakhine_culture'})

    def test_reviewed_alias_does_not_spread_to_shared_language(self):
        definition=root('language = rwanda_language culture_groups = { bantu_group great_lakes_kingdoms_group }').fields()
        self.assertEqual(culture_resolution('rwanda_culture',definition,None,PROFILE,{'ruanda'})[0],'ruanda')
        with self.assertRaises(ValueError):
            culture_resolution('rutara_culture',definition,None,PROFILE,{'ruanda'})
        self.assertEqual(culture_resolution('rutara_culture',definition,None,PROFILE,{'lacustrine_bantu'})[0],'lacustrine_bantu')
        self.assertEqual(culture_resolution('unconfigured_rwanda_speaker',definition,None,PROFILE,{'ruanda'})[0],'')
        with self.assertRaises(ValueError):
            culture_resolution('rwanda_culture',{'language':'other_language'},None,PROFILE,{'ruanda'})

    def test_similar_names_are_not_alias_rules(self):
        with self.assertRaises(ValueError):culture_resolution('tigre',{},None,PROFILE,{'tigray'})

    def test_chinese_yao_is_neither_miao_nor_african_yao(self):
        definition=root('language = hmong_language culture_groups = { hmong_mien_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('yao_china_culture',definition,None,PROFILE,{'miao','yao'})
        target='eu5_resident_yao_china_culture'
        self.assertEqual(culture_resolution('yao_china_culture',definition,None,PROFILE,{target})[0],target)
        african=root('language = yao_language culture_groups = { bantu_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('yao_china_culture',african,None,PROFILE,{target})

    def test_buginese_identity_does_not_merge_with_its_template(self):
        definition=root('language = buginese_language culture_groups = { austronesian_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('buginese_culture',definition,None,PROFILE,{'moluccan','malay'})
        target='eu5_resident_buginese_culture'
        self.assertEqual(culture_resolution('buginese_culture',definition,None,PROFILE,{target})[0],target)
        self.assertEqual(culture_resolution('unconfigured_buginese_speaker',definition,None,PROFILE,{target})[0],'')

    def test_sibe_explicit_compaction_requires_exact_source_groups(self):
        definition=root('language = jurchen_language culture_groups = { mongolian_group tungusic_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('sibe_culture',definition,None,PROFILE,{'mongol'})
        target='manchu'
        self.assertEqual(culture_resolution('sibe_culture',definition,None,PROFILE,{target})[0],target)
        wrong=root('language = jurchen_language culture_groups = { mongolian_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('sibe_culture',wrong,None,PROFILE,{target})

    def test_island_compaction_is_enumerated_not_automatic_by_dialect(self):
        for source,language in [('acehnese_culture','achenese_dialect'),('minangkabau_culture','minangkabau_dialect'),('iban_culture','iban_dialect')]:
            with self.subTest(source=source):
                definition = root('language = '+language+' culture_groups = { austronesian_group }').fields()
                target = 'dayak' if source=='iban_culture' else 'sumatran'
                with self.assertRaises(ValueError):culture_resolution(source,definition,None,PROFILE,{'malay','bornean'})
                self.assertEqual(culture_resolution(source,definition,None,PROFILE,{target})[0],target)
                self.assertEqual(culture_resolution('unconfigured_'+source,definition,None,PROFILE,{target})[0],'')

    def test_folk_religion_rule_does_not_swallow_unrelated_religions(self):
        old={'religion_aliases':{}}
        self.assertEqual(religion_resolution('test',{'group':'folk_african_group'},old,PROFILE,{'animist'})[0],'animist')
        self.assertEqual(religion_resolution('unconfigured_religion',{'group':'zoroastrian_group'},old,PROFILE,{'animist'})[0],'')
        self.assertEqual(religion_resolution('sikhism',{'group':'dharmic'},old,PROFILE,{'sikh'})[0],'sikh')

    def test_custom_religion_requires_generated_definition(self):
        with self.assertRaises(ValueError):
            religion_resolution('zoroastrian',{}, {'religion_aliases':{}},PROFILE,{'animist'})
        resolved = religion_resolution('zoroastrian',{}, {'religion_aliases':{}},PROFILE,{'eu5_religion_zoroastrian'})
        self.assertEqual(resolved[:2],('eu5_religion_zoroastrian','preserved_custom_religion'))

    def test_source_color_normalization_is_explicit(self):
        from m4_religions import source_color
        color,notes = source_color('color_test = rgb { 288 108 180 }','color_test')
        self.assertEqual(color,[1.0,0.423529,0.705882]);self.assertTrue(notes)
        color,notes = source_color('test = hsv360 { 222 99 41 }','test')
        self.assertTrue(all(0 <= c <= 1 for c in color));self.assertFalse(notes)
        with self.assertRaises(ValueError):source_color('test = hsv360 { 222 101 41 }','test')
        color,notes=source_color('test = hsv { 0.5 1 1 }','test')
        self.assertEqual(color,[0,1,1]);self.assertFalse(notes)
        with self.assertRaises(ValueError):source_color('test = hsv { 1.2 1 1 }','test')

    def test_rounding_is_global_and_deterministic(self):
        self.assertEqual(round_groups({'b':150,'a':150,'c':49}),{'b':1,'a':2,'c':0})
        self.assertEqual(sum(round_groups({str(n):49 for n in range(1000)}).values()),490)
        self.assertEqual(round_groups({}),{})
        with self.assertRaises(ValueError):round_groups({'bad':-1})


if __name__=='__main__':unittest.main()
