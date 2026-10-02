"""Structural regressions that could silently corrupt baseline statistics."""
import unittest

from pdx_text import root


class SaveScannerTests(unittest.TestCase):
    def test_braces_and_comments_inside_strings_do_not_close_objects(self):
        data = root('SAV123\na={ name="} # not a comment \\" {" # }\n nested={ x=2 } } b=3').fields()
        self.assertEqual(data['b'], '3')
        self.assertEqual(data['a'].fields()['nested'].fields()['x'], '2')

    def test_sparse_header_is_not_a_population_value(self):
        sparse = root('values={ 3 0=100 2=200 }').fields()['values']
        self.assertEqual(list(sparse.entries()), [(None, '3'), ('0', '100'), ('2', '200')])

    def test_duplicate_fields_require_explicit_handling(self):
        data = root('law=a law=b')
        self.assertEqual(list(data.entries()), [('law', 'a'), ('law', 'b')])
        with self.assertRaises(ValueError):
            data.fields()

    def test_anonymous_objects_and_empty_containers(self):
        data = root('rows={ { id=1 } { id=2 } } empty={ }').fields()
        self.assertEqual([obj.fields()['id'] for _, obj in data['rows'].entries()], ['1', '2'])
        self.assertEqual(list(data['empty'].entries()), [])

    def test_truncated_input_fails(self):
        for text in ['a={ b={ c=1 }', 'a=', 'a=}', 'a="unterminated']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                root(text).fields()

    def test_optional_scope_operator_keeps_source_span(self):
        source = 'COUNTRIES={ c:ITA ?= { name="?=" nested={ value=1 } } }'
        country = root(source).fields()['COUNTRIES'].fields()['c:ITA']
        self.assertEqual('?=', country.fields()['name'])
        self.assertEqual('1', country.fields()['nested'].fields()['value'])
        self.assertEqual(' name="?=" nested={ value=1 } ', country.text())


if __name__ == '__main__':
    unittest.main()
