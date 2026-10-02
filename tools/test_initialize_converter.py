from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from initialize_converter import InstalledResources, safe_child, materialize_assets, semantic_hash, validate_baseline
from pdx_text import root


class InitializationTests(unittest.TestCase):
    def test_configuration_digest_ignores_checkout_line_endings(self):
        from initialize_converter import config_digest
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_bytes(b'{\n  "rule": 1\n}\n')
            expected = config_digest(path)
            path.write_bytes(b'{\r\n  "rule": 1\r\n}\r\n')
            self.assertEqual(expected, config_digest(path))
            path.write_bytes(b'{\n  "rule": 2\n}\n')
            self.assertNotEqual(expected, config_digest(path))

    def test_external_resource_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)/'rules'
            with self.assertRaises(ValueError):safe_child(base,'../private.txt')
            with self.assertRaises(ValueError):safe_child(base,Path(td)/'outside.txt')

    def test_installed_name_pool_is_required_and_hash_checked(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);folder=base/'common/cultures';folder.mkdir(parents=True)
            source=folder/'test.txt';source.write_text('sample={ names={ NameA NameB } }',encoding='utf-8')
            value=root(source.read_text()).fields()['sample'].fields()['names']
            ref=dict(game='v3',kind='cultures',key='sample',field='names',sha256=semantic_hash(value))
            installed=InstalledResources({'v3':base})
            recipe={'definitions':{'cultures':{'output':{'male_common_first_names':{'reference':ref}}}},'labels':{},'icons':{}}
            materialize_assets(recipe,installed,base/'output')
            text=(base/'output/common/cultures/zz_converter_identity.txt').read_text(encoding='utf-8-sig')
            self.assertIn('NameA NameB',text)
            source.write_text('sample={ names={ Changed } }',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'版本不符'):InstalledResources({'v3':base}).field(ref)

    def test_localization_mismatch_does_not_silently_use_changed_text(self):
        import hashlib
        installed=InstalledResources({})
        installed.labels['v3','english']={'sample':'Changed'}
        ref=dict(game='v3',language='english',key='sample',sha256=hashlib.sha256(b'Original').hexdigest())
        with self.assertRaisesRegex(ValueError,'版本不符'):installed.label(ref)

    def test_baseline_rejects_advanced_date_or_mod_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'vic3-start.txt'
            for body in ['meta_data={version="1.13.11"} date=1836.1.2',
                         'meta_data={version="1.13.11" mods={ SomeMod }} date=1836.1.1',
                         'meta_data={version="1.12.0"} date=1836.1.1']:
                p.write_text(body,encoding='utf-8')
                with self.assertRaises(ValueError):validate_baseline(p,Path(td))

    def test_baseline_uses_validated_contents_not_one_fixed_file_hash(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'vic3-start.txt'
            p.write_text('meta_data={version="1.13.11"} date=1836.1.1 seed=999',encoding='utf-8')
            with patch('economy_model.Target'),patch('economy_model.british_baseline',return_value={'population':25951649}) as check:
                report=validate_baseline(p,Path(td))
                check.assert_called_once();self.assertEqual(report['date'],'1836.1.1')


if __name__=='__main__':unittest.main()
