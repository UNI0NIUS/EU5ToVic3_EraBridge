"""Protect demographic decisions against stale maps, data loss and invalid targets."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from location_reviews import ReviewStore, validate_document, validate_entries
from build_m2_prototype import allocate


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.dataset={'source_sha256':'source','political_map_sha256':'map',
                      'locations':[{'id':'sarzana'},{'id':'nanhui'}],'targets':{'x123456':{},'xABCDEF':{}}}
        self.entry={'sarzana':{'status':'mapped','targets':[{'province':'x123456','weight':2},{'province':'xABCDEF','weight':1}],'note':'test'}}

    def test_invalid_or_duplicate_provinces_and_non_integer_weights(self):
        for parts in ([],[{'province':'x000000'}],[{'province':'x123456'},{'province':'x123456'}],
                      [{'province':'x123456','weight':0}],[{'province':'x123456','weight':1.5}],
                      [{'province':'x123456','weight':True}]):
            with self.assertRaises(ValueError):
                validate_entries({'sarzana':{'status':'mapped','targets':parts}}, {'sarzana'},set(self.dataset['targets']))

    def test_wrong_campaign_map_and_nonpending_source_are_rejected(self):
        doc={'schema':1,'source_sha256':'source','political_map_sha256':'map','entries':self.entry}
        for source,politics,missing in [('other','map',{'sarzana'}),('source','other',{'sarzana'}),('source','map',{'nanhui'})]:
            with self.assertRaises(ValueError):
                validate_document(doc,source,politics,missing,set(self.dataset['targets']))

    def test_save_reload_history_and_conflicting_browser(self):
        with TemporaryDirectory() as d:
            store=ReviewStore(d,self.dataset);store.save(0,self.entry)
            self.assertEqual(ReviewStore(d,self.dataset).doc['entries'],self.entry)
            before=Path(d,'location_reviews.json').read_bytes()
            with self.assertRaises(RuntimeError):store.save(0,{'nanhui':{'status':'deferred'}})
            self.assertEqual(before,Path(d,'location_reviews.json').read_bytes())
            store.save(1,{'nanhui':{'status':'deferred','note':'later'}})
            self.assertEqual(len(store.doc['entries']),2)
            self.assertEqual(json.loads(Path(d,'review-history/000001.json').read_text())['entries'],self.entry)

    def test_fractional_people_remain_conserved_with_reviewed_weights(self):
        weights={p['province']:p['weight'] for p in self.entry['sarzana']['targets']}
        result=allocate(66390746,weights)
        self.assertEqual(sum(result.values()),66390746)
        self.assertLessEqual(abs(result['x123456']-2*result['xABCDEF']),1)


if __name__=='__main__':unittest.main()
