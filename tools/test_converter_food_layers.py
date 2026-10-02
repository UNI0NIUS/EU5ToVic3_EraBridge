import io
from types import SimpleNamespace
import unittest
import numpy as np
from PIL import Image
from converter_controller import App
from converter_project import DEFAULTS


class FoodLayersTests(unittest.TestCase):
    def test_market_and_local_layers_use_distinct_fields(self):
        app=object.__new__(App);app.image_cache={}
        pixels=np.array([[1]*4+[2]*4+[3]*4]*4,dtype=np.uint32)
        app.world=SimpleNamespace(raster=lambda:pixels)
        app.preview=dict(settings=DEFAULTS,rows=[dict(state='S',country='AAA',market_owner='AAA',risks=[],provinces=['x000001'],market_food_shortfall=0,local_food_shortfall=.8),
            dict(state='T',country='BBB',market_owner='AAA',risks=[],provinces=['x000002'],market_food_shortfall=0,local_food_shortfall=0),
            dict(state='U',country='CCC',market_owner='CCC',risks=[],provinces=['x000003'],market_food_shortfall=None,local_food_shortfall=None)])
        market=Image.open(io.BytesIO(app.image('market_food')));local=Image.open(io.BytesIO(app.image('local_food')))
        self.assertEqual(market.getpixel((1,1)),market.getpixel((3,1)))
        self.assertNotEqual(local.getpixel((1,1)),local.getpixel((3,1)))
        self.assertEqual(local.getpixel((5,1)),(110,110,116))
        self.assertIs(app.image('market_food'),app.image_cache['market_food'])


if __name__=='__main__':unittest.main()
