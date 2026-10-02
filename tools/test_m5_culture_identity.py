"""Regression cases for partial source splits, merges and exact integer conservation."""
import unittest
from collections import Counter
from package_m5_culture_identity import split_identities
from verify_m5_culture_identity import expected_split


class IdentitySplitTests(unittest.TestCase):
    def test_split_keeps_unaffected_members_and_merges_existing_target(self):
        old = {('S', 'A', 'yi', 'r'): 101, ('S', 'A', 'filipino', 'r'): 13,
               ('S', 'A', 'ilocano', 'r'): 9, ('S', 'B', 'yi', 'r'): 20,
               ('S', 'A', 'yi', 'other_faith'): 7}
        weights = {('S', 'A', 'yi', 'r'): Counter(yi=50, hani=25, lisu=25),
                   ('S', 'A', 'ilocano', 'r'): Counter(ilocano=2, filipino=1)}
        actual = split_identities(old, weights)
        self.assertEqual(actual[('S', 'A', 'yi', 'r')], 51)
        self.assertEqual(actual[('S', 'A', 'filipino', 'r')], 16)
        self.assertEqual(actual[('S', 'B', 'yi', 'r')], 20)
        self.assertEqual(actual[('S', 'A', 'yi', 'other_faith')], 7)
        self.assertEqual(actual, expected_split(old, weights))
        self.assertEqual(sum(actual.values()), sum(old.values()))

    def test_ties_and_large_products_use_integer_arithmetic(self):
        key = ('S', 'A', 'old', 'r')
        weights = {key: Counter(a=10**15 + 1, b=10**15, c=10**15)}
        for n in (1, 2, 3, 1077545489):
            self.assertEqual(split_identities({key: n}, weights), expected_split({key: n}, weights))
        self.assertEqual(split_identities({key: 2}, {key: Counter(a=1, b=1, c=1)}),
                         {('S', 'A', 'a', 'r'): 1, ('S', 'A', 'b', 'r'): 1})


if __name__ == '__main__':
    unittest.main()
