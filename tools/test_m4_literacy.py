from pathlib import Path
import tempfile
import unittest
from extract_m4_literacy import rate_units
from m4_literacy import decimal_rate
from verify_m4_literacy import parse_effects

class LiteracyTests(unittest.TestCase):
    def test_population_weighted_rate_and_percent_conversion(self):
        numerator=100*rate_units('20')+300*rate_units('80')
        self.assertEqual(decimal_rate(numerator,400),'0.65000')
        self.assertEqual(decimal_rate(10*rate_units('100'),10),'1.00000')
        self.assertEqual(decimal_rate(0,10),'0.00000')
        self.assertEqual(rate_units('86.8373'),86837300)
    def test_invalid_and_unrepresentable_source_values_rejected(self):
        for value in ('-1','101','NaN','Infinity','0.00000001'):
            with self.subTest(value=value),self.assertRaises(ValueError):rate_units(value)
        with self.assertRaises(ValueError):decimal_rate(0,0)
    def parse(self,body):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'effects.txt';p.write_text(body,encoding='utf-8');return parse_effects(p)
    def test_identity_selectors_and_rate_readback(self):
        script='eu5_m4_literacy_ITA = { every_scope_state = { limit = { state_region = s:STATE_A } every_scope_pop = { limit = { culture = cu:c religion = rel:r } set_pop_literacy = { literacy_rate = { value = 0.65 } } } } }'
        self.assertEqual(str(self.parse(script)[('STATE_A','ITA','c','r')]),'0.65')
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.parse(script.replace('religion = rel:r',''))
        with self.assertRaisesRegex(ValueError,'outside'):self.parse(script.replace('0.65','65'))
        with self.assertRaisesRegex(ValueError,'five places'):self.parse(script.replace('0.65','0.650000000'))
        with self.assertRaisesRegex(ValueError,'script value block'):self.parse(script.replace('{ value = 0.65 }','0.650000000'))
    def test_duplicate_selector_rejected(self):
        pop='every_scope_pop = { limit = { culture = cu:c religion = rel:r } set_pop_literacy = { literacy_rate = { value = 0.2 } } }'
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            self.parse('eu5_m4_literacy_ITA = { every_scope_state = { limit = { state_region = s:STATE_A } '+pop+pop+' } }')

if __name__=='__main__':unittest.main()
