import unittest
from m4_location_overrides import apply_overrides


class ExplicitLocationTests(unittest.TestCase):
    def test_add_preserves_weights_replace_removes_old_target(self):
        inverse={'a':{'p'},'b':{'p'}};weights={'a':{'p':3}}
        entries={'a':{'operation':'add','expected_weights':{'p':3},'targets':{'q':1},'reason':'test'},'b':{'operation':'replace','expected_weights':{'p':1},'targets':{'q':2},'reason':'test'}}
        apply_overrides(inverse,weights,entries,{'a','b'},{'p','q'})
        self.assertEqual(weights,{'a':{'p':3,'q':1},'b':{'q':2}})
        self.assertEqual(inverse,{'a':{'p','q'},'b':{'q'}})

    def test_changed_baseline_and_invalid_target_rejected(self):
        entry={'operation':'add','expected_weights':{'p':1},'targets':{'q':1},'reason':'test'}
        for inverse,weights,valid in [({'a':{'r'}},{},{'p','q','r'}),({'a':{'p'}},{'a':{'p':2}},{'p','q'}),({'a':{'p'}},{},{'p'})]:
            with self.assertRaises(ValueError):apply_overrides(inverse,weights,{'a':entry},{'a'},valid)

    def test_add_existing_target_rejected(self):
        entry={'operation':'add','expected_weights':{'p':1},'targets':{'p':1},'reason':'test'}
        with self.assertRaises(ValueError):apply_overrides({'a':{'p'}},{},{'a':entry},{'a'},{'p'})


if __name__=='__main__':unittest.main()
