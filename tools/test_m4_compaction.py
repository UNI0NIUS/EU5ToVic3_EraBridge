from pathlib import Path
import unittest

from m3_world import load_json
from m4_demographics import culture_resolution
from pdx_text import root

PROFILE=load_json(Path(__file__).resolve().parents[1]/'config/personal/m4_demographics.json')


class CompactionTests(unittest.TestCase):
    def test_explicit_member_resolves_to_native_category(self):
        d=root('language = malagasy_language culture_groups = { malagasy_group }').fields()
        self.assertEqual(culture_resolution('merina_culture',d,None,PROFILE,{'malagasy'})[:2],('malagasy','explicit_v3_granularity_compaction'))
        self.assertEqual(culture_resolution('unlisted_malagasy_speaker',d,None,PROFILE,{'malagasy'})[0],'')

    def test_source_group_drift_and_missing_target_are_rejected(self):
        d=root('language = malagasy_language culture_groups = { other_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('merina_culture',d,None,PROFILE,{'malagasy'})
        d=root('language = malagasy_language culture_groups = { malagasy_group }').fields()
        with self.assertRaises(ValueError):culture_resolution('merina_culture',d,None,PROFILE,set())

    def test_historical_borderline_identities_are_outside_sweep(self):
        for source,language,group,native in [('beothuk_culture','cree_language','cree_group','cree'),('eyak_culture','nadene_language','nadene_group','athabaskan'),('tlingit_culture','nadene_language','nadene_group','athabaskan'),('hadza_culture','khoe_language','khoisan_group','khoisan')]:
            with self.subTest(source=source):
                definition=root('language = '+language+' culture_groups = { '+group+' }').fields()
                with self.assertRaises(ValueError):culture_resolution(source,definition,None,PROFILE,{native})
                target='eu5_resident_'+('tlingit_culture' if source=='eyak_culture' else source)
                self.assertEqual(culture_resolution(source,definition,None,PROFILE,{target})[0],target)


if __name__=='__main__':unittest.main()
