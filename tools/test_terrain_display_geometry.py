import unittest
from terrain_display_geometry import footprint


class DisplayGeometryTest(unittest.TestCase):
    def test_seam_islands_focus_short_interval_and_mark_actual_pixels(self):
        xs=[98,99,0,1,5,6];ys=[10,10,10,10,20,20]
        result=footprint(xs,ys,100)
        self.assertEqual([[98,10],[6,20]],result['view_points'])
        self.assertEqual(2,len(result['markers']))
        pixels=set(zip(xs,ys))
        self.assertIn(tuple(result['xy']),pixels)
        for marker in result['markers']:self.assertIn(tuple(marker),pixels)

    def test_concave_polygon_marker_is_not_in_empty_center(self):
        xs=[10,10,10,11,12,12,12];ys=[10,11,12,12,12,11,10]
        r=footprint(xs,ys,100)
        self.assertIn(tuple(r['markers'][0]),set(zip(xs,ys)))
        self.assertEqual([[10,10],[12,12]],r['view_points'])

if __name__=='__main__':unittest.main()
