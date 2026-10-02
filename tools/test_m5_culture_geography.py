import tempfile,unittest
from pathlib import Path
from m5_culture_geography import majority,historical_anchors,lab,read_color

class CultureGeographyTests(unittest.TestCase):
    def test_strict_majority_boundary(self):
        self.assertFalse(majority(50,100));self.assertTrue(majority(51,100));self.assertFalse(majority(0,0))
        # A majority in one owner's part cannot replace the full-state denominator.
        self.assertTrue(majority(60,80));self.assertFalse(majority(60,200))

    def test_historical_merging_split_mapping_and_missing_locations(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'pops.txt';p.write_text('locations = { a = { define_pop = { size = 1 culture = one } define_pop = { size = 1 culture = two } define_pop = { size = 8 culture = other } } b = { define_pop = { size = 4 culture = one } } }')
            records,best,unmapped=historical_anchors(p,{'one':'merged','two':'merged'},{'a':{'STATE_A','STATE_B'}},{'merged'})
            self.assertEqual(records['merged'][0]['centipersons'],200000)
            self.assertEqual(records['merged'][0]['states'],['STATE_A','STATE_B'])
            self.assertEqual(len(unmapped),1);self.assertEqual(unmapped[0]['location'],'b')
            self.assertEqual(best['merged']['location'],'a')

    def test_lab_reference_and_color_units(self):
        self.assertAlmostEqual(lab([1,1,1])[0],100,places=3)
        self.assertAlmostEqual(lab([1,0,0])[0],53.2408,places=3)
        self.assertEqual(read_color('color = rgb { 255 0 0 }'),[1,0,0])
        self.assertEqual(read_color('color = hsv360 { 120 100 100 }'),[0,1,0])

if __name__=='__main__':unittest.main()
