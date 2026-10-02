import copy
import json
from pathlib import Path
import tempfile
import unittest

from m3_world import digest
from pdx_text import root
from verify_m4_culture_assets import effective_definitions, validate_culture


class CultureAssetTests(unittest.TestCase):
    def setUp(self):
        self.culture = root('heritage = h language = l religion = r male_common_first_names = { A } female_common_first_names = { B } common_last_names = { C }').fields()
        self.traits = {'h':{'type':'heritage','trait_group':'hg'},'l':{'type':'language','trait_group':'lg'}}
        self.groups = {'hg':{'type':'heritage'},'lg':{'type':'language'}}
        self.locs = {lang:{'test':'Test','h':'Heritage','l':'Language'} for lang in ('english','simp_chinese')}

    def verify(self):
        validate_culture('test',self.culture,self.traits,self.groups,{'r'},self.locs)

    def test_valid_graph(self):
        self.verify()

    def test_dangling_or_wrong_type_trait_rejected(self):
        for replacement in ('missing','l'):
            with self.subTest(replacement=replacement):
                self.culture['heritage'] = replacement
                with self.assertRaises(AssertionError): self.verify()

    def test_wrong_group_type_rejected(self):
        self.groups['lg']['type'] = 'heritage'
        with self.assertRaises(AssertionError): self.verify()

    def test_missing_default_religion_rejected(self):
        self.culture['religion'] = 'unknown'
        with self.assertRaises(AssertionError): self.verify()

    def test_empty_name_list_and_missing_translation_rejected(self):
        original = copy.copy(self.culture)
        self.culture['common_last_names'] = root('')
        with self.assertRaises(AssertionError): self.verify()
        self.culture = original
        del self.locs['simp_chinese']['test']
        with self.assertRaises(AssertionError): self.verify()

    def test_changed_political_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            game,mod = Path(temp)/'game',Path(temp)/'mod'
            (mod/'.metadata').mkdir(parents=True)
            (mod/'.metadata/metadata.json').write_text(json.dumps({'game_custom_data':{'replace_paths':[]}}),encoding='utf-8')
            p = mod/'common/cultures/custom.txt';p.parent.mkdir(parents=True)
            p.write_text('custom = { heritage = h }',encoding='utf-8')
            report = {'output_sha256':{str(p.relative_to(mod)):digest(p)}}
            self.assertIn('custom',effective_definitions(game,mod,'common/cultures',{},report))
            p.write_text('custom = { heritage = missing }',encoding='utf-8')
            with self.assertRaises(AssertionError):effective_definitions(game,mod,'common/cultures',{},report)


if __name__ == '__main__': unittest.main()
