"""Independent readback of an additive historical homeland candidate.

No imports from the candidate builder, no use of its declared expected pairs as
the authority. Recompute additions from the frozen policy and compare all files.
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pdx_text import root, Object
from build_m2_prototype import objects
from m3_world import digest
from package_m4_population_test import effective, parse_pops

STATE = 'common/history/states/00_eu5_world.txt'
POPS = 'common/history/pops/00_eu5_world.txt'


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def inventory(mod):
    return {p.relative_to(mod).as_posix(): digest(p) for p in mod.rglob('*') if p.is_file()}


def validate_survey(policy, baseline_pending):
    """A completed design pass must name every item, including withheld claims."""
    survey = policy.get('full_survey')
    if not survey:
        return
    expected = survey['expected_cultures']
    entries = policy['entries']
    assert len(expected) == len(set(expected)) == survey['expected_count'], 'Duplicate or inconsistent survey scope'
    assert set(expected) == baseline_pending, 'Survey scope differs from baseline missing homelands'
    assert len(entries) == len(expected) and {e['culture'] for e in entries} == set(expected), 'Incomplete full survey'
    for e in entries:
        assert e['period'] and e['core'] and e['limitation'] and e['sources'], 'Unexplained survey decision'
        assert e['status'] in {'candidate_core', 'withheld_label_scope', 'withheld_mobile_identity', 'withheld_map_resolution'}, 'Undecided full-survey entry'
        if e['status'].startswith('withheld_'):
            assert not e['states'], 'Withheld decision grants a homeland'
        else:
            assert e['states'] and e['anchors'], 'Core decision has no geographic witness'
        for s in e['sources']:
            assert s in policy['sources'] and policy['sources'][s]['url'].startswith('https://'), 'Missing survey reference'
    assert survey['unprocessed_items'] == 0 and not survey['all_historical_assets_reviewed'], 'Misleading completion claim'


def state_structure(path):
    pairs, remainder, states = Counter(), {}, set()
    for scope, obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['STATES']):
        s = scope.removeprefix('s:')
        assert s not in states, ('Duplicate state', s)
        states.add(s)
        other = []
        for key, value in obj.entries():
            if key == 'add_homeland':
                assert isinstance(value, str) and value.startswith('cu:'), (key, value)
                pairs[s, value.removeprefix('cu:')] += 1
            else:
                other.append((key, value.text().strip() if isinstance(value, Object) else value))
        remainder[s] = other
    assert all(n == 1 for n in pairs.values()), 'Duplicate add_homeland entry'
    return set(pairs), remainder, states


def verify(output):
    output = Path(output)
    manifest = read(output / 'manifest.json')
    policy = read(output / 'policy.snapshot.json')
    base, mod = Path(manifest['baseline_mod']), Path(manifest['candidate_mod'])
    demographic = Path(manifest['demographic_run'])
    for p, sha in manifest['input_sha256'].items():
        assert digest(Path(p)) == sha, ('Changed input', p)
    policy_path = next(p for p in manifest['input_sha256'] if p.endswith('m5_historical_homelands.json'))
    assert policy == read(policy_path), 'Policy snapshot differs from researched configuration'
    before_files, after_files = inventory(base), inventory(mod)
    assert before_files == manifest['baseline_sha256']
    assert after_files == manifest['output_sha256']
    if manifest.get('demographic_provenance_reports'):
        cursor = Path(manifest['baseline_package']).resolve()
        for path in manifest['demographic_provenance_reports']:
            assert Path(path).resolve() == cursor / 'package_report.json', 'Broken demographic ancestry'
            assert path in manifest['input_sha256'], 'Unhashed ancestry report'
            ancestor = read(path)
            assert ancestor['output_sha256'][POPS] == before_files[POPS], 'Unexplained inherited population change'
            cursor = Path(ancestor.get('prior_package', cursor)).resolve()
        assert Path(ancestor['demographic_run']).resolve() == demographic.resolve()
    assert before_files.keys() == after_files.keys(), 'Files added or removed'
    changed = [p for p in before_files if before_files[p] != after_files[p]]
    assert set(changed) <= {STATE}, ('Non-homeland file changed', changed)
    before, structural_before, states = state_structure(base / STATE)
    after, structural_after, after_states = state_structure(mod / STATE)
    assert structural_before == structural_after and states == after_states, 'Political borders/ownership/state properties changed'
    cultures = effective(mod, 'common/cultures')
    links = defaultdict(set)
    with (demographic / 'staging/province_population_draft.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f): links[row['source_location']].add(row['target_state'])
    expected, entries = set(), {}
    for e in policy['entries']:
        c = e['culture']
        assert c not in entries, ('Duplicate design', c)
        entries[c] = e
        assert c in cultures and c.startswith('eu5_resident_'), ('Invalid resident culture', c)
        for s in e.get('sources', []):
            assert s in policy['sources'] and policy['sources'][s]['finding'], ('Missing research source', c, s)
        for definition in e.get('source_identity_definitions', {}).values():
            assert digest(Path(definition['file'])) == definition['sha256'], ('Fixed EU5 identity definition changed', c)
        if e['status'] != 'candidate_core':
            assert not e['states'], 'Pending research must not grant homelands'
            continue
        assert e['period'] and e['core'] and e['sources'] and e['limitation']
        assert e['translation'] in {'direct_core','regional_witness','direct_core_with_split_link_restriction'}
        for source in e['sources']:
            assert policy['sources'][source]['url'].startswith('https://')
            assert policy['sources'][source]['finding']
        witnessed = set()
        for loc, mapped in e['anchors'].items():
            assert links[loc] == set(mapped), ('Anchor mismatch', loc)
            witnessed.update(mapped)
        assert set(e['states']) <= witnessed, ('Unwitnessed game state', c)
        for s in e['states']:
            assert s in states, ('Invalid state', s)
            expected.add((s, c))
    assert after == before | expected, 'Missing or unexpected homeland; existing claims must be retained'
    assert not (before - after)
    assert sorted(after - before) == [tuple(p) for p in manifest['added_pairs']]
    assert not manifest['removed_pairs']
    assert {(s,c) for s,c in after if c.startswith('eu5_migrant_')} == {(s,c) for s,c in before if c.startswith('eu5_migrant_')}
    oldpops, newpops = parse_pops(base / POPS), parse_pops(mod / POPS)
    assert oldpops == newpops, 'Population/state/owner/culture/religion differs'
    partitions = read(demographic / 'refinement_policy.snapshot.json')['partitions']
    affected = {g['target'] for g in partitions if g['target'].startswith('eu5_resident_')}
    baseline_pending = affected - {c for s,c in before}
    candidate_pending = affected - {c for s,c in after}
    with (demographic / 'template_fallback/candidate_culture_catalog.csv').open(encoding='utf-8-sig', newline='') as f:
        catalog = {r['culture']: r for r in csv.DictReader(f)}
    covered = baseline_pending - candidate_pending
    assert set(entries) <= affected, 'Research batch outside affected resident scope'
    validate_survey(policy, baseline_pending)
    withheld = {c:e['status'] for c,e in entries.items() if e['status'].startswith('withheld_')}
    if policy.get('full_survey'):
        assert set(withheld) == candidate_pending, 'Unexplained cultures without homelands'
        table_path = next(p for p in manifest['input_sha256'] if p.endswith('m5_homeland_research_full.tsv'))
        with Path(table_path).open(encoding='utf-8', newline='') as f:
            table_rows = list(csv.DictReader(f, delimiter='\t'))
        assert len({r['key'] for r in table_rows}) == len(table_rows), 'Duplicate research table row'
        for r in table_rows:
            c = 'eu5_resident_' + r['key']
            e = entries[c]
            assert e['core'] == r['core'] and e['evidence_grade'] == r['grade'], ('Research table/config disagreement', c)
            assert set(e['anchors']) == (set() if r['anchors'] == '-' else set(r['anchors'].split(','))), ('Research anchors/config disagreement', c)
            assert set(e['source_identity_definitions']) == set(catalog[c]['source_identities'].split('|')), ('Incomplete member identity evidence', c)
    return {
        'status': 'passed', 'installed': False, 'all_historical_assets_reviewed': False,
        'baseline_pending_count': len(baseline_pending), 'candidate_pending_count': len(candidate_pending),
        'newly_covered_cultures': len(covered),
        'design_decisions': len(entries), 'unprocessed_designs': len(baseline_pending - set(entries)),
        'withheld_decisions': withheld, 'withheld_count': len(withheld),
        'evidence_grade_counts': dict(Counter(e.get('evidence_grade', 'earlier_batch_documented_core') for e in entries.values())),
        'newly_covered_centipersons': sum(int(catalog[c]['centipersons']) for c in covered),
        'added_homeland_pairs': len(after - before), 'removed_homeland_pairs': 0,
        'unchanged_files': len(before_files) - len(changed), 'changed_files': changed,
        'global_integer_population': sum(newpops.values()), 'integer_population_groups': len(newpops),
        'political_state_structure_unchanged': True, 'all_existing_homelands_preserved': True,
        'migrant_homelands_unchanged': True, 'population_religion_literacy_assets_economy_navy_bytes_unchanged': True,
        'geographic_review_scope': 'Mechanical link validation; direct_core/regional_witness confidence and historical inference remain separately disclosed in each design.',
        'baseline_pending_cultures': sorted(baseline_pending), 'candidate_pending_cultures': sorted(candidate_pending),
        'newly_covered_culture_keys': sorted(covered)
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('candidate', type=Path)
    args = parser.parse_args()
    result = verify(args.candidate)
    (args.candidate / 'independent_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not isinstance(v,list) or k=='changed_files'}, ensure_ascii=True, indent=2))
