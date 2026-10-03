import tempfile
import unittest
from pathlib import Path
from converter_identity_assets import sync, verify, labels
from converter_identity_repair import verify_event_labels
from religion_palette import color, apply


class IdentityAssetTests(unittest.TestCase):
    def test_old_replace_file_cannot_override_current_names_or_erase_event_text(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);assets=base/'assets';mod=base/'mod'
            for lang in ('english','simp_chinese'):
                p=assets/'localization/replace'/lang/('zz_current_l_'+lang+'.yml')
                p.parent.mkdir(parents=True)
                p.write_text('l_'+lang+':\n manchu:0 "满洲"\n',encoding='utf-8-sig')
                p=mod/'localization/replace'/lang/('zzz_old_l_'+lang+'.yml')
                p.parent.mkdir(parents=True)
                p.write_text('l_'+lang+':\n manchu:0 "女真—满洲"\n eu5_test.1.t:0 "帝国宪制"\n',encoding='utf-8-sig')
            with self.assertRaisesRegex(ValueError,'Duplicate|Outdated'):verify(mod,assets)
            result=sync(mod,assets)
            self.assertEqual(result['removed_duplicate_labels'],2)
            self.assertEqual(labels(mod,'simp_chinese')['manchu'],'满洲')
            self.assertEqual(labels(mod,'simp_chinese')['eu5_test.1.t'],'帝国宪制')
            self.assertEqual(sync(mod,assets)['removed_duplicate_labels'],0)
            (mod/'events').mkdir()
            (mod/'events/test.txt').write_text('eu5_test.1 = { title = eu5_test.1.t desc = eu5_test.1.d }')
            with self.assertRaisesRegex(ValueError,'eu5_test.1.d'):verify_event_labels(mod)

    def test_population_overlay_duplicate_is_removed_before_claim_reader(self):
        from economy_model import definitions
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);assets=base/'assets';mod=base/'mod'
            for folder in (assets/'common/religions',mod/'common/religions'):folder.mkdir(parents=True)
            (assets/'common/religions/zz_converter_identity.txt').write_text('faith={ heritage=new }')
            (mod/'common/religions/zz_converter_identity.txt').write_text('faith={ heritage=new }')
            (mod/'common/religions/zz_population_religions.txt').write_text('faith={ heritage=old } other={ heritage=keep }')
            with self.assertRaisesRegex(ValueError,'Duplicate definition'):definitions(mod/'common/religions')
            sync(mod,assets)
            result=definitions(mod/'common/religions')
            self.assertEqual(result['faith']['heritage'],'new')
            self.assertEqual(result['other']['heritage'],'keep')

    def test_religion_palette_keeps_script_and_uses_native_float_rgb(self):
        original='icon = "bon.dds"\nheritage = heritage_dharmic\ncolor = { 0 0 0 }\ntaboos = { wine }'
        updated=apply('bon',original)
        self.assertIn('icon = "bon.dds"',updated)
        self.assertIn('taboos = { wine }',updated)
        self.assertTrue(all(0 <= n <= 1 for n in color('bon')))
        self.assertTrue(all(len(str(n).partition('.')[2]) <= 5 for n in color('bon')))
        self.assertIsNone(color('unknown_faith'))
        self.assertEqual(apply('unknown_faith',original),original)


if __name__=='__main__':unittest.main()
