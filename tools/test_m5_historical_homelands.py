"""Adversarial checks: matching file hashes must not bypass semantic guards."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from verify_m5_historical_homelands import verify, read, inventory, validate_survey, STATE, POPS
from prepare_m5_historical_homelands import demographic_provenance

ROOT = Path(__file__).resolve().parents[1]
LATEST = ROOT / '.local/m5/historical-homelands-latest.json'


@unittest.skipUnless(LATEST.exists(), 'Needs a local historical homeland candidate')
class HomelandGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidate = Path(read(LATEST)['candidate'])
        cls.scratch = tempfile.TemporaryDirectory(prefix='homeland-guards-', dir=ROOT / '.local/m5')
        cls.out = Path(cls.scratch.name).resolve()
        assert cls.out.is_relative_to((ROOT / '.local/m5').resolve())
        cls.manifest = read(candidate / 'manifest.json')
        cls.mod = cls.out / 'candidate_mod'
        shutil.copytree(cls.manifest['candidate_mod'], cls.mod)
        shutil.copy2(candidate / 'policy.snapshot.json', cls.out / 'policy.snapshot.json')
        cls.manifest['candidate_mod'] = str(cls.mod)
        cls.original = {p: (cls.mod / p).read_bytes() for p in (STATE, POPS)}

    @classmethod
    def tearDownClass(cls):
        assert cls.out.is_relative_to((ROOT / '.local/m5').resolve())
        cls.scratch.cleanup()

    def setUp(self):
        for p, contents in self.original.items(): (self.mod / p).write_bytes(contents)

    def save_manifest(self):
        self.manifest['output_sha256'] = inventory(self.mod)
        (self.out / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def edit_state(self, before, after):
        p = self.mod / STATE
        text = p.read_text(encoding='utf-8-sig')
        self.assertIn(before, text)
        p.write_text(text.replace(before, after, 1), encoding='utf-8-sig')
        self.save_manifest()

    def test_valid_candidate(self):
        self.save_manifest()
        self.assertEqual(verify(self.out)['status'], 'passed')

    def test_owner_change_rejected_even_with_updated_digest(self):
        self.edit_state('country = c:ITA', 'country = c:E0F')
        with self.assertRaisesRegex(AssertionError, 'Political borders'): verify(self.out)

    def test_extra_homeland_rejected_even_with_updated_digest(self):
        self.edit_state('add_homeland = cu:south_italian', 'add_homeland = cu:south_italian\nadd_homeland = cu:eu5_resident_chimu_culture')
        with self.assertRaisesRegex(AssertionError, 'Missing or unexpected homeland'): verify(self.out)

    def test_duplicate_homeland_rejected(self):
        self.edit_state('add_homeland = cu:south_italian', 'add_homeland = cu:south_italian\nadd_homeland = cu:south_italian')
        with self.assertRaisesRegex(AssertionError, 'Duplicate add_homeland'): verify(self.out)

    def test_population_file_change_rejected(self):
        with (self.mod / POPS).open('ab') as f: f.write(b'\n# unauthorized population edit\n')
        self.save_manifest()
        with self.assertRaisesRegex(AssertionError, 'Non-homeland file changed'): verify(self.out)


class FullSurveyGuards(unittest.TestCase):
    def setUp(self):
        self.policy = read(ROOT / 'config/personal/m5_historical_homelands.json')
        if not self.policy.get('full_survey'): self.skipTest('No full survey yet')
        self.expected = set(self.policy['full_survey']['expected_cultures'])

    def test_omitted_culture_cannot_count_as_complete(self):
        self.policy['entries'].pop()
        with self.assertRaisesRegex(AssertionError, 'Incomplete full survey'):
            validate_survey(self.policy, self.expected)

    def test_withheld_culture_cannot_silently_get_land(self):
        next(e for e in self.policy['entries'] if e['status'].startswith('withheld_'))['states']=['STATE_MALAYA']
        with self.assertRaisesRegex(AssertionError, 'Withheld decision grants'):
            validate_survey(self.policy, self.expected)

    def test_uncited_withheld_decision_rejected(self):
        next(e for e in self.policy['entries'] if e['status'].startswith('withheld_'))['sources']=[]
        with self.assertRaisesRegex(AssertionError, 'Unexplained survey decision'):
            validate_survey(self.policy, self.expected)


class ProvenanceGuards(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='homeland-provenance-', dir=ROOT / '.local/m5')
        self.out = Path(self.scratch.name).resolve()
        assert self.out.is_relative_to((ROOT / '.local/m5').resolve())
        self.a, self.b = self.out / 'a', self.out / 'b'
        self.a.mkdir(); self.b.mkdir()

    def tearDown(self):
        assert self.out.is_relative_to((ROOT / '.local/m5').resolve())
        self.scratch.cleanup()

    def put(self, p, sha='same', **extra):
        (p / 'package_report.json').write_text(json.dumps({'output_sha256': {POPS: sha}, **extra}), encoding='utf-8')

    def test_inherits_matching_population_provenance(self):
        self.put(self.a, prior_package=str(self.b))
        self.put(self.b, demographic_run=str(self.out / 'run'))
        run, reports = demographic_provenance(self.a)
        self.assertEqual(run, self.out / 'run')
        self.assertEqual(len(reports), 2)

    def test_rejects_changed_population(self):
        self.put(self.a, prior_package=str(self.b))
        self.put(self.b, sha='different', demographic_run=str(self.out / 'run'))
        with self.assertRaisesRegex(ValueError, 'Population changed'): demographic_provenance(self.a)

    def test_rejects_ancestry_cycle(self):
        self.put(self.a, prior_package=str(self.b))
        self.put(self.b, prior_package=str(self.a))
        with self.assertRaisesRegex(ValueError, 'Cycle'): demographic_provenance(self.a)


if __name__ == '__main__': unittest.main()
