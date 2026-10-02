import json
from pathlib import Path
from unittest import TestCase, main
from economy_population_calibration import calibrate, majority_signature


class CalibrationTests(TestCase):
    def setUp(self):
        self.policy=json.loads((Path(__file__).resolve().parents[1]/'config/personal/economy_population_calibration.json').read_text())

    def row(self,s,n,capacity=0):
        return {'state':s,'country':'ITA','population':n,'formal_job_capacity':capacity,'new_subsistence_job_capacity':0}

    def test_country_limit_and_state_limit(self):
        groups={('A','ITA','a','r'):1000,('B','ITA','a','r'):1000}
        after,rows=calibrate(groups,set(groups),[self.row('A',1000),self.row('B',1000)],{}, {}, self.policy)
        self.assertEqual(sum(after.values()),1700)
        self.assertTrue(all(r['removed_persons']==150 for r in rows))

    def test_fifteen_percent_workforce_reserve(self):
        groups={('A','ITA','a','r'):1000}
        # 260 formal jobs * 75% = 195; required people ceil(195*1.15/0.25)=897.
        after,rows=calibrate(groups,set(groups),[self.row('A',1000,260)],{}, {}, self.policy)
        self.assertEqual(sum(after.values()),897)
        self.assertGreaterEqual(sum(after.values())*.25,195*1.15)

    def test_jobs_available_means_no_reduction(self):
        groups={('A','ITA','a','r'):1000}
        after,_=calibrate(groups,set(groups),[self.row('A',1000,400)],{}, {}, self.policy)
        self.assertEqual(after,groups)

    def test_template_and_tiny_identity_preserved(self):
        groups={('A','ITA','a','r'):999,('A','ITA','b','r'):1,('A','ITA','fallback','r'):100}
        eligible={k for k in groups if k[2]!='fallback'}
        after,_=calibrate(groups,eligible,[self.row('A',1100)],{}, {}, self.policy)
        self.assertEqual(after['A','ITA','b','r'],1)
        self.assertEqual(after['A','ITA','fallback','r'],100)
        self.assertEqual(set(after),set(groups))

    def test_elite_host_population_floor(self):
        groups={('A','ITA','a','r'):1000}
        after,_=calibrate(groups,set(groups),[self.row('A',1000)],{}, {('A','ITA'):.95}, self.policy)
        self.assertEqual(sum(after.values()),950)

    def test_whole_state_majority_not_flipped_by_split_ownership(self):
        groups={('A','ITA','a','r'):510,('A','BOH','b','r'):490}
        after,rows=calibrate(groups,{('A','ITA','a','r')},[self.row('A',510)],{}, {}, self.policy)
        self.assertEqual(after,groups)
        self.assertTrue(rows[0]['majority_guard_preserved_original'])
        self.assertEqual(majority_signature(groups,True),majority_signature(after,True))

    def test_mismatched_stale_employment_rejected(self):
        groups={('A','ITA','a','r'):900}
        with self.assertRaisesRegex(ValueError,'Employment/population mismatch'):
            calibrate(groups,set(groups),[self.row('A',1000)],{}, {}, self.policy)

    def test_owner_jobs_count_at_full_staffing(self):
        groups={('A','ITA','a','r'):1000}
        after,_=calibrate(groups,set(groups),[self.row('A',1000,260)],{('A','ITA'):40}, {}, self.policy)
        # 220*0.75 + 40 = 205, retained population ceil(205*1.15/0.25)=943.
        self.assertEqual(sum(after.values()),943)


if __name__=='__main__':main()
