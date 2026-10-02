import unittest
from m4_migrant_cultures import cohort_states
from pdx_text import root


class MigrantScopeTests(unittest.TestCase):
    def test_overlapping_regions_rejected(self):
        regions={'a':root('states = { S }').fields(),'b':root('states = { S }').fields()}
        with self.assertRaises(ValueError):cohort_states({'regions':{'test':['a','b']}},regions)

    def test_native_african_scope_is_not_diaspora_scope(self):
        regions={'america':root('states = { US }').fields(),'africa':root('states = { AF }').fields()}
        config={'regions':{'european_settler':['america','africa'],'african_diaspora':['america']}}
        scope=cohort_states(config,regions)
        self.assertNotIn('AF',scope['african_diaspora'])
        self.assertEqual(scope['european_settler']['AF'],'africa')

if __name__=='__main__':unittest.main()
