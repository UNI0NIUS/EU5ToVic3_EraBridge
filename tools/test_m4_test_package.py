from pathlib import Path
import tempfile
import unittest
from package_m4_population_test import parse_pops

class TestPackagePops(unittest.TestCase):
    def read(self,text):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pops.txt';path.write_text(text,encoding='utf-8')
            return parse_pops(path)
    def test_culture_religion_and_owner_remain_separate(self):
        text='POPS = { s:STATE_A = { region_state:AAA = { create_pop = { culture = c religion = r size = 3 } create_pop = { culture = c religion = s size = 2 } } region_state:BBB = { create_pop = { culture = c religion = r size = 1 } } } }'
        self.assertEqual(self.read(text),{('STATE_A','AAA','c','r'):3,('STATE_A','AAA','c','s'):2,('STATE_A','BBB','c','r'):1})
    def test_duplicate_groups_rejected(self):
        pop='create_pop = { culture = c religion = r size = 3 } '
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.read('POPS = { s:A = { region_state:T = { '+pop+pop+'} } }')
    def test_zero_and_unscoped_population_rejected(self):
        with self.assertRaisesRegex(ValueError,'Non-positive'):self.read('POPS = { s:A = { region_state:T = { create_pop = { culture = c religion = r size = 0 } } } }')
        with self.assertRaisesRegex(ValueError,'one POPS'):self.read('POPS = {} POPS = {}')

if __name__=='__main__':unittest.main()
