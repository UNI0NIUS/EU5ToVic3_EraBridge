import unittest
from pdx_text import root
from converter_startup_compatibility import retain_imported_law

class StartingLawTests(unittest.TestCase):
    def test_retention_preserves_enactment_and_original_visibility(self):
        text='law_chiefdom = { can_enact = { is_country_type = decentralized } is_visible = { is_country_type = decentralized } modifier = { authority = 1 } }'
        updated=retain_imported_law(text,'law_chiefdom',{'ABC'})
        before=root(text).fields()['law_chiefdom'].fields()
        after=root(updated).fields()['law_chiefdom'].fields()
        self.assertEqual(before['modifier'].text(),after['modifier'].text())
        for field in ('is_visible','can_enact'):
            branches=after[field].fields()['OR'].entries()
            conditions=[obj.text() for key,obj in branches]
            self.assertEqual(2,len(conditions))
            self.assertIn('is_country_type = decentralized',conditions[0])
            self.assertIn('has_law = law_type:law_chiefdom',conditions[1])
            self.assertIn('this = c:ABC',conditions[1])
        self.assertEqual(updated,retain_imported_law(updated,'law_chiefdom',{'ABC'}))
        changed=retain_imported_law(updated,'law_chiefdom',{'XYZ'})
        self.assertIn('this = c:XYZ',changed)
        self.assertNotIn('this = c:ABC',changed)

if __name__=='__main__':unittest.main()
