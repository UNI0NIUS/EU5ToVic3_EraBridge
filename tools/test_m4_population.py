"""Population-unit and fractional-allocation invariants for the demographic stage."""
import unittest
from extract_m4_population import centipersons
from build_m2_prototype import allocate


class PopulationTests(unittest.TestCase):
    def test_thousands_to_centipersons_exactly(self):
        self.assertEqual(centipersons('1.23456'),123456)
        self.assertEqual(centipersons('0.00001'),1)
        self.assertEqual(centipersons('0'),0)

    def test_invalid_precision_and_negative_population_fail(self):
        for value in ('-1','0.000001'):
            with self.assertRaises(ValueError):centipersons(value)

    def test_many_to_many_split_retains_every_fraction(self):
        parts=allocate(centipersons('0.00007'),{'x003':1,'x001':1,'x002':1})
        self.assertEqual(parts,{'x001':3,'x002':2,'x003':2})
        self.assertEqual(sum(parts.values()),7)


if __name__=='__main__':unittest.main()
