import unittest
from package_m5_uncolonized import split_groups, terrain_assignments


class IntegrationRules(unittest.TestCase):
    def test_population_rounding_preserves_identity_and_templates(self):
        a=('S','OLD','c','r');b=('S','TEMPLATE','b','r')
        self.assertEqual(split_groups({a:5,b:7},{a:{'U01':2,'U02':1}}),
                         {('S','U01','c','r'):3,('S','U02','c','r'):2,b:7})

    def test_source_groups_converge_without_population_loss(self):
        a=('S','A','c','r');b=('S','B','c','r')
        self.assertEqual(split_groups({a:11,b:3},{a:{'U':10},b:{'U':10}}),{('S','U','c','r'):14})

    def terrain(self,owner='0',mapping=None,empty=None,edges=None):
        return terrain_assignments({'OLD'} if empty is None else empty,{'U1','U2'},
             {'S':{'a':'OLD','b':'U1','c':'U2'}},{'a':['mountain']} if mapping is None else mapping,
             {'mountain':{'owner':owner}},{'mountain'},[('a','b')] if edges is None else edges)

    def test_empty_terrain_attaches_to_unique_adjacent_tribe(self):
        self.assertEqual(self.terrain()[0]['to'],'U1')

    def test_owned_terrain_is_never_absorbed(self):
        with self.assertRaises(ValueError):self.terrain(owner='17')

    def test_unmapped_terrain_is_never_absorbed(self):
        with self.assertRaises(ValueError):self.terrain(mapping={})

    def test_two_neighbor_tribes_are_ambiguous(self):
        with self.assertRaises(ValueError):self.terrain(edges=[('a','b'),('a','c')])

    def test_isolated_terrain_is_not_joined_across_sea(self):
        with self.assertRaises(ValueError):self.terrain(edges=[])

    def test_inhabited_country_is_not_retired(self):
        self.assertEqual(self.terrain(empty=set()),[])


if __name__=='__main__':unittest.main()
