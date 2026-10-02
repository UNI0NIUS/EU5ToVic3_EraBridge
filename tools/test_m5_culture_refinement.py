import unittest
from prepare_m5_culture_refinement import candidate


class RefinementPartitionTests(unittest.TestCase):
    def test_missing_duplicate_and_unknown_members_fail_before_asset_build(self):
        original={'global_culture_policy':{'aggregates':[{'members':['a','b']}]}}
        for members in (['a'],['a','a','b'],['a','b','c']):
            with self.subTest(members=members),self.assertRaisesRegex(ValueError,'exactly once'):
                candidate(original,{'partitions':[{'members':members}]},{})


if __name__=='__main__':unittest.main()
