from collections import Counter
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from m3_uncolonized import plan, apply, choose_tag, connected_groups, province_land_edges
from pdx_text import root

POLICY={'schema':1,'enabled':True,'country_type':'decentralized','unowned_source_owners':['0'],
        'grouping':'connected_land_component_of_mapped_primary_culture',
        'primary_culture':'largest_source_population_before_culture_mapping',
        'tie_break':'source_culture_key','missing_evidence':'retain_and_report'}


class TribesTests(unittest.TestCase):
    def world(self):
        return SimpleNamespace(mapping={'p1':['l1'],'p2':['l2'],'p3':['l3']},
            province_state={'p1':'A','p2':'B','p3':'B'},
            owners={'A':{'p1':'OLD'},'B':{'p2':'OLD','p3':'OLD'}},
            original={'A':{'p1':'OLD'},'B':{'p2':'OLD','p3':'OLD'}},
            locations={n:{'owner':0} for n in ('l1','l2','l3')},uninhabitable=set(),
            countries={'OLD':{'source_id':None,'capital':'A'}},fallbacks=[],
            country_defs={'OLD':root('country_type=decentralized cultures={mapped} capital=A')})

    def run_plan(self,w=None,pops=None,edges=None):
        return plan(w or self.world(),pops or {n:Counter({('native','faith'):100}) for n in ('l1','l2','l3')},
                    {'native':'mapped','other':'other_mapped','related':'mapped'}, {'faith':'animist'},POLICY,
                    [('p1','p2'),('p2','p3')] if edges is None else edges)

    def test_same_culture_continues_across_state_borders(self):
        r=self.run_plan();self.assertEqual(len(r['countries']),1)
        c=next(iter(r['countries'].values()))
        self.assertEqual(c['states'],['A','B']);self.assertEqual(c['provinces'],3)
        self.assertEqual(c['country_type'],'decentralized')

    def test_disconnected_same_culture_is_separate(self):
        r=self.run_plan(edges=[('p1','p2')]);self.assertEqual(len(r['countries']),2)
        self.assertEqual(sorted(c['provinces'] for c in r['countries'].values()),[1,2])

    def test_other_culture_does_not_bridge_components(self):
        pops={n:Counter({('native','faith'):100}) for n in ('l1','l2','l3')}
        pops['l2']=Counter({('other','faith'):100})
        self.assertEqual(len(self.run_plan(pops=pops)['countries']),3)

    def test_source_owned_land_never_transfers_or_bridges(self):
        w=self.world();w.locations['l2']['owner']=17
        r=self.run_plan(w);self.assertEqual(len(r['countries']),2)
        self.assertEqual({x['province'] for x in r['transfers']},{'p1','p3'})

    def test_mixed_ownership_anchors_are_excluded(self):
        w=self.world();w.mapping['p1']=['l1','l2'];w.locations['l2']['owner']=17
        r=self.run_plan(w);self.assertNotIn('p1',{x['province'] for x in r['transfers']})
        self.assertEqual(r['excluded'][0]['reason'],'mixed_owned_and_unowned_anchors')

    def test_missing_population_or_identity_is_reported(self):
        pops={'l1':Counter(), 'l2':Counter({('unknown','faith'):100}), 'l3':Counter({('native','faith'):100})}
        r=self.run_plan(pops=pops)
        self.assertEqual(len(r['transfers']),1);self.assertEqual(len(r['unresolved']),2)

    def test_province_plurality_not_statewide_population_vote(self):
        pops={'l1':Counter({('other','faith'):10000}), 'l2':Counter({('native','faith'):10}), 'l3':Counter({('native','faith'):10})}
        r=self.run_plan(pops=pops)
        groups={c['culture']:c['provinces'] for c in r['countries'].values()}
        self.assertEqual(groups,{'other_mapped':1,'mapped':2})

    def test_split_source_location_weight_is_not_duplicated(self):
        w=self.world();w.mapping={p:['l1','l1'] for p in w.province_state}
        r=self.run_plan(w,pops={'l1':Counter({('native','faith'):100})})
        c=next(iter(r['countries'].values()))
        self.assertEqual(Fraction(c['source_culture_centipersons']['native']),100)

    def test_mapped_related_cultures_can_form_one_component(self):
        pops={'l1':Counter({('native','faith'):100}), 'l2':Counter({('related','faith'):100}), 'l3':Counter({('native','faith'):100})}
        self.assertEqual(len(self.run_plan(pops=pops)['countries']),1)

    def test_deterministic_tie_and_tag_collision_resolution(self):
        pops={n:Counter({('native','faith'):50,('other','faith'):50}) for n in ('l1','l2','l3')}
        a=self.run_plan(pops=pops);b=self.run_plan(pops=dict(reversed(list(pops.items()))))
        self.assertEqual(a,b);self.assertEqual(next(iter(a['countries'].values()))['culture'],'mapped')
        used=set();first=choose_tag('identity',used);second=choose_tag('identity',used)
        self.assertNotEqual(first,second);self.assertEqual(len(first),3)

    def test_apply_rebuilds_transfers_and_removes_empty_fallback(self):
        w=self.world();r=self.run_plan(w);apply(w,r)
        self.assertNotIn('OLD',w.countries)
        self.assertEqual(len(w.countries),1)
        tag=next(iter(w.countries));self.assertEqual(w.transfers['B','OLD'],{tag:2})
        self.assertEqual(w.countries[tag]['template'],'OLD')

    def test_apply_rejects_changed_ownership_evidence(self):
        w=self.world();r=self.run_plan(w);w.locations['l1']['owner']=42
        before=deepcopy(w.owners)
        with self.assertRaisesRegex(ValueError,'source-unowned'):apply(w,r)
        self.assertEqual(w.owners,before)

    def test_reviewed_population_geography_controls_local_plurality(self):
        w=self.world();raw={n:Counter({('native','faith'):100}) for n in w.locations}
        reviewed={p:Counter({('other','faith'):200}) for p in w.province_state}
        r=plan(w,raw,{'native':'mapped','other':'other_mapped'},{'faith':'animist'},POLICY,[('p1','p2'),('p2','p3')],reviewed,{p:{'0'} for p in reviewed})
        self.assertEqual(next(iter(r['countries'].values()))['culture'],'other_mapped')

    def test_reviewed_owned_location_prevents_uncolonized_transfer(self):
        w=self.world();raw={n:Counter({('native','faith'):100}) for n in w.locations}
        reviewed={p:Counter({('native','faith'):100}) for p in w.province_state}
        r=plan(w,raw,{'native':'mapped'},{'faith':'animist'},POLICY,[('p1','p2'),('p2','p3')],reviewed,{'p1':{'0'},'p2':{'7'},'p3':{'0'}})
        self.assertEqual(len(r['countries']),2)
        self.assertNotIn('p2',{x['province'] for x in r['transfers']})
        self.assertEqual(r['excluded'][0]['reason'],'reviewed_population_includes_source_owned_locations')

    def test_land_continuity_keeps_terrain_but_removes_sea_links(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'map_data').mkdir();cache=p/'edges.json'
            cache.write_text(json.dumps({'edges':[['x000001','x000002'],['x000002','x000003']]}))
            (p/'map_data/adjacencies.csv').write_text('From;To;Type\nx000002;x000003;sea\n')
            w=SimpleNamespace(game=p,owners={},province_state={'x000001':'A','x000002':'A','x000003':'B'})
            # The transport helper returns an empty graph for impassable terrain;
            # territorial grouping must still use its validated raster borders.
            with patch('economy_market.land_edges',return_value=([],set())):
                self.assertEqual(province_land_edges(w,cache),[('x000001','x000002')])


if __name__=='__main__':unittest.main()
