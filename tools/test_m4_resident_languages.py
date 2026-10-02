import unittest

from m4_cultures import checked_source_language, resident_language
from pdx_text import root
from verify_m4_culture_assets import validate_source_language


class ResidentLanguageTests(unittest.TestCase):
    def test_top_level_scope_is_an_explicit_disambiguation(self):
        languages={'greek_language':root('dialects = { greek_language = { default = yes } }').fields()}
        config={'source_language':'greek_language','source_language_family':None}
        with self.assertRaises(ValueError):checked_source_language(languages,config)
        with self.assertRaises(AssertionError):validate_source_language(config,languages)
        explicit=dict(config,source_language_scope='top_level')
        checked_source_language(languages,explicit)
        validate_source_language(explicit,languages)

    def test_nested_dialect_requires_exact_parent_and_family(self):
        languages = {'parent':root('family = family_a dialects = { child = {} }').fields()}
        config = {'source_language':'child','source_language_parent':'parent','source_language_family':'family_a'}
        checked_source_language(languages,config)
        validate_source_language(config,languages)
        for change in ({'source_language_parent':None},{'source_language_parent':'other'}, {'source_language_family':'wrong'}, {'source_language':'missing'}):
            with self.subTest(change=change):
                altered = dict(config,**change)
                with self.assertRaises(ValueError):checked_source_language(languages,altered)
                with self.assertRaises(AssertionError):validate_source_language(altered,languages)

    def test_duplicate_dialects_and_top_level_collisions_rejected(self):
        definition = root('family = family_a dialects = { child = {} }').fields()
        config = {'source_language':'child','source_language_parent':'parent','source_language_family':'family_a'}
        for languages in ({'parent':definition,'other':definition}, {'parent':definition,'child':{'family':'family_a'}}, {'parent':root('family = family_a dialects = { child = {} child = {} }').fields()}):
            with self.assertRaises(ValueError):checked_source_language(languages,config)
            with self.assertRaises(AssertionError):validate_source_language(config,languages)

    def test_missing_family_keeps_distinct_language_and_group(self):
        traits,groups = {},{}
        language,group = resident_language({'source_language':'hlai_language','language_trait':None}, {},{},traits,groups)
        self.assertEqual(language,'eu5_resident_language_hlai_language')
        self.assertEqual(group,'eu5_resident_language_group_hlai_language')
        self.assertEqual(groups[group],'type = language')
        self.assertIn('trait_group = '+group,traits[language])

    def test_explicit_family_keeps_language_separate(self):
        traits,groups = {},{}
        language,group = resident_language({'source_language':'example','language_trait':None,'language_group':'family'}, {},{'family':{'type':'language'}},traits,groups)
        self.assertEqual(language,'eu5_resident_language_example')
        self.assertEqual(group,'family');self.assertFalse(groups)

    def test_conflicting_family_is_rejected(self):
        traits={};config={'source_language':'example','language_trait':None,'language_group':'a'}
        groups={'a':{'type':'language'},'b':{'type':'language'}}
        resident_language(config,{},groups,traits,{})
        with self.assertRaises(ValueError):resident_language(dict(config,language_group='b'),{},groups,traits,{})

    def test_wrong_group_type_and_key_collision_rejected(self):
        config={'source_language':'example','language_trait':None,'language_group':'heritage'}
        with self.assertRaises(ValueError):resident_language(config,{}, {'heritage':{'type':'heritage'}},{},{})
        with self.assertRaises(ValueError):resident_language(config,{'eu5_resident_language_example':{}},{},{},{})

    def test_reviewed_languages_can_separate_a_shared_source_field(self):
        traits={};groups={}
        config={'source_language':'khoe_language','language_trait':None}
        for key in ('hadza','sandawe'):
            review={'trait':'eu5_reviewed_language_'+key,'group':'eu5_reviewed_language_group_'+key,
                'labels':{'english':key,'simp_chinese':key},'group_labels':{'english':key,'simp_chinese':key},
                'sources':['https://glottolog.org/'],'basis':'Explicit classification evidence'}
            language,group=resident_language(dict(config,reviewed_language=review),{},{},traits,groups)
            self.assertEqual(language,review['trait']);self.assertEqual(group,review['group'])
        self.assertEqual(len(traits),2);self.assertEqual(len(groups),2)
        self.assertEqual(config['source_language'],'khoe_language')

    def test_reviewed_language_needs_evidence_and_rejects_collisions(self):
        review={'trait':'eu5_reviewed_language_talysh','group':'iranic','labels':{},
                'sources':['https://glottolog.org/'],'basis':'Language evidence'}
        config={'language_trait':None,'reviewed_language':review}
        for altered in (dict(review,sources=[]),dict(review,basis=''),dict(review,trait='language_persian')):
            with self.assertRaises(ValueError):resident_language(dict(config,reviewed_language=altered),{}, {'iranic':{'type':'language'}},{},{})
        with self.assertRaises(ValueError):resident_language(config,{}, {'iranic':{'type':'heritage'}},{},{})
        with self.assertRaises(ValueError):resident_language(dict(config,aggregate_language=True),{},{},{},{})


if __name__ == '__main__':unittest.main()
