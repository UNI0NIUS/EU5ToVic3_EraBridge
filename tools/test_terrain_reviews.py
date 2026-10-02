import copy
import json
import tempfile
import unittest
from pathlib import Path
from terrain_reviews import SCHEMA,TerrainReviewStore,validate_document,apply_references
from terrain_connectivity import complete


class TerrainReviewsTest(unittest.TestCase):
    def setUp(self):
        self.dataset=dict(source_map_sha256='s',target_map_sha256='t',components=[dict(provinces=['x000001','x000002'])],sources={'coast':{},'barren':{},'native':{}})
        self.entries={'x000001':dict(status='mapped',source_location='barren',reference_location='coast',note='island review')}
        self.states={'x000001':'A','x000002':'A'}
        self.locations={'coast':dict(owner=4,population_persons='1'),'barren':dict(owner=0,population_persons='0'),'native':dict(owner=0,population_persons='2')}
        self.pops={'native':{'culture_a':200}}

    def test_campaign_owner_rederived_and_land_filled_without_population_change(self):
        original=copy.deepcopy(self.pops)
        for owner in (4,8):
            self.locations['coast']['owner']=owner;seeds={};natives={}
            self.assertEqual([],apply_references(self.entries,self.states,self.locations,{'barren'},self.pops,seeds,natives))
            plan=complete(self.states,[('x000001','x000002')],seeds,natives)
            self.assertTrue(plan['export_ready']);self.assertEqual('source:'+str(owner),plan['provinces']['x000002']['owner'])
        self.assertEqual(original,self.pops)

    def test_native_identity_rederived(self):
        self.entries['x000001']['reference_location']='native'
        for culture in ('culture_a','culture_b'):
            seeds={};natives={};apply_references(self.entries,self.states,self.locations,{'barren'},{'native':{culture:200}},seeds,natives)
            self.assertEqual('native:'+culture,seeds['x000001']['owner'])

    def test_barren_mapping_alone_does_not_invent_owner(self):
        self.entries['x000001']['reference_location']='';seeds={}
        missing=apply_references(self.entries,self.states,self.locations,{'barren'},self.pops,seeds,{})
        self.assertEqual(1,len(missing));self.assertEqual({},seeds)
        self.assertFalse(complete(self.states,[],seeds)['export_ready'])

    def test_existing_evidence_never_overridden(self):
        with self.assertRaises(ValueError):apply_references(self.entries,self.states,self.locations,{'barren'},self.pops,{'x000001':{'owner':'source:9'}},{})

    def test_explicit_review_scope_can_override_only_selected_evidence(self):
        seeds={'x000001':{'owner':'source:9'},'x000002':{'owner':'source:7'}}
        original=copy.deepcopy(self.pops)
        apply_references(self.entries,self.states,self.locations,{'barren'},self.pops,seeds,{},allowed_overrides={'x000001'})
        self.assertEqual('source:4',seeds['x000001']['owner'])
        self.assertEqual('source:7',seeds['x000002']['owner'])
        self.assertEqual(original,self.pops)

    def test_review_round_survives_atomic_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=TerrainReviewStore(tmp,self.dataset)
            row={**self.entries['x000001'],'review_round':'empty-parts-review'}
            saved=store.save(0,{'x000001':row})
            self.assertEqual(row,TerrainReviewStore(tmp,self.dataset).doc['entries']['x000001'])
            self.assertEqual(saved['revision'],1)

    def test_validation_revision_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=TerrainReviewStore(tmp,self.dataset)
            first=store.save(0,self.entries)
            self.assertEqual(first,TerrainReviewStore(tmp,self.dataset).doc)
            self.assertTrue((Path(tmp)/'review-history/000000.json').exists())
            with self.assertRaises(RuntimeError):store.save(0,self.entries)
            other=copy.deepcopy(first);other['target_map_sha256']='wrong'
            with self.assertRaises(ValueError):store.validate(other)
            bad=copy.deepcopy(self.entries);bad['x000001']['reference_location']='missing'
            with self.assertRaises(ValueError):store.save(1,bad)
            bad=copy.deepcopy(self.entries);bad['sea']=bad.pop('x000001')
            with self.assertRaises(ValueError):store.save(1,bad)
            # Reset is an explicit pending record, preserving the audit trail.
            reset=store.save(1,{'x000001':dict(status='pending',source_location='',reference_location='',note='')})
            self.assertEqual('pending',reset['entries']['x000001']['status'])
            self.assertEqual(first,json.loads((Path(tmp)/'review-history/000001.json').read_text(encoding='utf-8')))

if __name__=='__main__':unittest.main()
