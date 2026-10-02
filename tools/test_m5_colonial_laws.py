import unittest
from build_political_rules_report import territorial_colonial_participants


class ColonialEvidenceTest(unittest.TestCase):
    def test_building_company_and_unrepresented_country_do_not_grant_colonial_state(self):
        politics = {'countries': {'a': {'type': 'location'}, 'b': {'type': 'building'}, 'c': {'type': 'location'}},
                    'subjects': [{'overlord': 'a', 'subject': 'b', 'type': 'trade_company'},
                                 {'overlord': 'a', 'subject': 'c', 'type': 'colonial_nation'}]}
        mapping = {'countries': {'A': {'source_id': 'a', 'country_type': 'recognized'},
                                'B': {'source_id': 'b', 'country_type': 'company'}}}
        self.assertEqual(territorial_colonial_participants(politics, mapping), (set(), set()))

    def test_nested_territorial_colonial_governments_remain_eligible(self):
        politics = {'countries': {k: {'type': 'location'} for k in 'abc'},
                    'subjects': [{'overlord': 'a', 'subject': 'b', 'type': 'colonial_nation'},
                                 {'overlord': 'b', 'subject': 'c', 'type': 'trade_company'}]}
        mapping = {'countries': {k.upper(): {'source_id': k, 'country_type': t}
                                for k, t in zip('abc', ['recognized', 'colonial', 'company'])}}
        self.assertEqual(territorial_colonial_participants(politics, mapping), ({'b', 'c'}, {'a', 'b'}))


if __name__ == '__main__': unittest.main()
