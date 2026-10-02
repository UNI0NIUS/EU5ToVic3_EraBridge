"""Independent raw-ledger/PDX readback for the bounded M5 identity repair."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import re

import numpy as np
from build_m2_prototype import objects, strings
from build_m3_world import load_localization
from m3_world import digest
from m5_culture_geography import read_color, lab, COLOR
from package_m4_population_test import effective, parse_pops, rows, GAME
from package_m5_culture_refinement import read, write, files, homeland_pairs, non_homeland_states
from package_m5_uncolonized import inherited_report
from pdx_text import root, Object
from verify_m4_culture_assets import validate_culture
from verify_m4_literacy import verify as verify_literacy, parse_effects

ROOT = Path(__file__).resolve().parents[1]
POPS = 'common/history/pops/00_eu5_world.txt'
STATE = 'common/history/states/00_eu5_world.txt'
DEFS = 'common/country_definitions/zz_eu5_world.txt'
CHARS = 'common/history/characters/00_eu5_world.txt'


def txt(p):
    return p.read_text(encoding='utf-8-sig')


def expected_split(before, fractions):
    result = Counter()
    for (s, t, c, r), n in before.items():
        weights = fractions.get((s, t, c, r))
        if weights is None:
            result[s, t, c, r] += n
            continue
        exact = {culture: Fraction(n * weight, sum(weights.values())) for culture, weight in weights.items()}
        rounded = {culture: v.numerator // v.denominator for culture, v in exact.items()}
        ranking = sorted(exact, key=lambda c: (-(exact[c] - rounded[c]), c))
        for culture in ranking[:n - sum(rounded.values())]:
            rounded[culture] += 1
        for culture, amount in rounded.items():
            if amount:
                result[s, t, culture, r] += amount
    return dict(result)


def canonical(obj):
    return [(k, canonical(v) if isinstance(v, Object) else v) for k, v in obj.entries()]


def margins(pops):
    result = Counter()
    for (s, t, c, r), n in pops.items():
        result[s, t, r] += n
    return result


def verify(package):
    report = read(package / 'package_report.json')
    policy = read(package / 'policy.snapshot.json')
    evidence = read(package / 'identity_correction.json')
    prior = inherited_report(Path(report['prior_package']))
    base, mod = Path(prior['mod_directory']), Path(report['mod_directory'])
    demo, old_demo = Path(report['demographic_run']), Path(prior['demographic_run'])
    assert files(mod) == report['output_sha256']
    assert files(base) == prior['output_sha256']
    for p, h in report['input_sha256'].items():
        assert digest(Path(p)) == h, ('Changed input', p)
    assert policy == read(ROOT / 'config/personal/m5_culture_identity_corrections.json')
    allowed = {POPS, STATE, DEFS, CHARS, '.metadata/metadata.json',
               'common/scripted_effects/zz_eu5_m4_literacy.txt', 'common/on_actions/zz_eu5_m4_literacy.txt',
               'common/on_actions/00_code_on_actions.txt', 'common/history/population/00_eu5_world.txt'}
    added = {'common/cultures/zz_eu5_identity_corrections.txt',
             'common/discrimination_traits/zz_eu5_identity_corrections.txt',
             'common/discrimination_trait_groups/zz_eu5_identity_corrections.txt',
             'localization/english/eu5_identity_corrections_l_english.yml',
             'localization/simp_chinese/eu5_identity_corrections_l_simp_chinese.yml'}
    before_hash, after_hash = files(base), files(mod)
    assert set(after_hash) - set(before_hash) == added and not set(before_hash) - set(after_hash)
    changed = {p for p, h in after_hash.items() if before_hash.get(p) != h}
    assert changed <= allowed | added and changed == set(report['changed_files'])
    # The source geography ledger is immutable in this operation.
    assert files(demo / 'staging') == files(old_demo / 'staging')
    old_rows = list(rows(old_demo / 'demographics/resident_culture_crosswalk.csv'))
    new_rows = list(rows(demo / 'demographics/resident_culture_crosswalk.csv'))
    oldmap = {r['source_culture']: r['target_culture'] for r in old_rows}
    newmap = {r['source_culture']: r['target_culture'] for r in new_rows}
    assert len(oldmap) == len(old_rows) == len(newmap) == len(new_rows) == 1540
    assert newmap == {**oldmap, **policy['mappings']}
    assert {s for s in oldmap if oldmap[s] != newmap[s]} == set(policy['mappings'])
    assert {r['source_culture']: r['centipersons'] for r in old_rows} == {r['source_culture']: r['centipersons'] for r in new_rows}
    religions = {r['source_religion']: r['target_religion'] for r in rows(old_demo / 'demographics/resident_religion_crosswalk.csv')}
    assert digest(demo / 'demographics/resident_religion_crosswalk.csv') == digest(old_demo / 'demographics/resident_religion_crosswalk.csv')
    old_dr, dr = read(old_demo / 'demographics/demographics_report.json'), read(demo / 'demographics/demographics_report.json')
    assert old_dr['migrant_cultures'] == dr['migrant_cultures']
    migrants = {(m['source'], s): m['target'] for m in dr['migrant_cultures']['cultures'] for s in m['states']}
    weights, cents, source_totals = defaultdict(Counter), Counter(), Counter()
    for x in rows(demo / 'staging/province_population_draft.csv'):
        n = int(x['centipersons']); source_totals[x['source_culture']] += n
        s, t, source = x['target_state'], x['target_owner'], x['source_culture']
        old, new = migrants.get((source, s), oldmap[source]), migrants.get((source, s), newmap[source])
        r = religions[x['source_religion']]
        weights[s, t, old, r][new] += n; cents[s, t, new, r] += n
    assert dict(source_totals) == {r['source_culture']: int(r['centipersons']) for r in old_rows}
    actual = parse_pops(mod / POPS); before = parse_pops(base / POPS)
    original = parse_pops(package / 'original_population.txt')
    old_original = parse_pops(Path(evidence['old_original_population']))
    assert actual == expected_split(before, weights), 'Incorrect current POP split/merge'
    assert original == expected_split(old_original, weights), 'Incorrect original POP split/merge'
    assert margins(before) == margins(actual) and margins(old_original) == margins(original)
    group_rows = list(rows(demo / 'demographics/resident_population_groups.csv'))
    assert {tuple(r[k] for k in ('state', 'owner', 'culture', 'religion')): int(r['centipersons']) for r in group_rows} == cents
    for r in group_rows:
        k = tuple(r[x] for x in ('state', 'owner', 'culture', 'religion'))
        assert int(r['preview_integer_persons']) == actual.get(k, 0)
    assert digest(demo / 'template_fallback/template_population_groups.csv') == digest(old_demo / 'template_fallback/template_population_groups.csv'), 'Template population changed'
    template_cents = Counter()
    for r in rows(demo / 'template_fallback/template_population_groups.csv'):
        template_cents[r['culture']] += int(r['persons']) * 100
    source_cents = Counter()
    for (_, _, c, _), n in cents.items():
        source_cents[c] += n
    catalog = list(rows(demo / 'template_fallback/candidate_culture_catalog.csv'))
    assert {r['culture']: int(r['centipersons']) for r in catalog} == dict(source_cents + template_cents)
    assert {r['culture']: int(r['template_centipersons']) for r in catalog} == {r['culture']: template_cents[r['culture']] for r in catalog}
    for rel, h in dr['files_sha256'].items():
        assert digest(demo / 'demographics' / rel) == h, ('Demographic artifact drift', rel)
    # Political source identities, including source rulers, are separate from POP cultures.
    old_politics = read(Path(prior['political_run']) / 'conversion_report.json')
    politics = read(Path(report['political_run']) / 'conversion_report.json')
    country_defs = effective(mod, 'common/country_definitions')
    base_defs = effective(base, 'common/country_definitions')
    assert set(country_defs) == set(base_defs)
    changed_countries = {}
    for tag, old in old_politics['countries'].items():
        new = politics['countries'][tag]
        source = old.get('source_culture')
        want = policy['mappings'].get(source, old['culture'])
        assert new['culture'] == want
        expected_cultures = [want if c == old['culture'] else c for c in old.get('cultures', [old['culture']])]
        assert strings(country_defs[tag]['cultures']) == expected_cultures == new.get('cultures', [want])
        assert {k: v for k, v in old.items() if k not in ('culture', 'cultures', 'culture_mapping')} == {k: v for k, v in new.items() if k not in ('culture', 'cultures', 'culture_mapping')}
        if want != old['culture']:
            changed_countries[tag] = {'source': source, 'old': old['culture'], 'new': want}
    assert changed_countries == evidence['country_changes']
    for tag in country_defs:
        for key, v in base_defs[tag].items():
            if key == 'cultures' and tag in changed_countries:
                continue
            actual_value = country_defs[tag][key]
            assert (canonical(v) if isinstance(v, Object) else v) == (canonical(actual_value) if isinstance(actual_value, Object) else actual_value)
    old_chars = dict(objects(root(txt(base / CHARS)).fields()['CHARACTERS']))
    new_chars = dict(objects(root(txt(mod / CHARS)).fields()['CHARACTERS']))
    assert old_chars.keys() == new_chars.keys()
    ruler_map = {(r['tag'], r['source_id']): r for r in old_politics['rulers']}
    actual_ruler_changes = []
    for scope, body in old_chars.items():
        left, right = list(objects(body)), list(objects(new_chars[scope]))
        assert len(left) == len(right)
        for (op, old), (new_op, new) in zip(left, right):
            assert op == new_op
            f = old.fields(); tag = scope.removeprefix('c:'); pid = f.get('first_name', '').removeprefix('EU5_FIRST_')
            ruler = ruler_map.get((tag, pid), {})
            target = policy['mappings'].get(ruler.get('source_culture'), f.get('culture'))
            if target != f.get('culture'):
                assert new.fields()['culture'] == target
                assert re.sub(r'\bculture\s*=\s*\w+', 'culture = CHECKED', old.text()) == re.sub(r'\bculture\s*=\s*\w+', 'culture = CHECKED', new.text())
                actual_ruler_changes.append({'tag': tag, 'source_id': pid, 'source': ruler['source_culture'], 'old': f['culture'], 'new': target})
            else:
                assert old.text() == new.text()
    assert actual_ruler_changes == evidence['ruler_changes']
    assert digest(Path(prior['political_run']) / 'province_owners.json') == digest(Path(report['political_run']) / 'province_owners.json')
    assert non_homeland_states(txt(base / STATE)) == non_homeland_states(txt(mod / STATE))
    additions = {(s, c) for c, spec in policy['assets'].items() for s in spec['homelands']}
    assert homeland_pairs(txt(mod / STATE)) == homeland_pairs(txt(base / STATE)) | additions
    # Graph, colors and actual template limitations.
    cultures, prior_cultures = effective(mod, 'common/cultures'), effective(base, 'common/cultures')
    traits, prior_traits = effective(mod, 'common/discrimination_traits'), effective(base, 'common/discrimination_traits')
    groups = effective(mod, 'common/discrimination_trait_groups')
    faiths = effective(mod, 'common/religions')
    assert set(cultures) - set(prior_cultures) == set(policy['assets'])
    assert all(traits[t]['type'] == 'language' for t in set(traits) - set(prior_traits)), 'New heritage forbidden'
    loc = {}
    for lang in ('english', 'simp_chinese'):
        loc[lang] = {}
        for directory in (GAME / 'localization' / lang, mod / 'localization' / lang, mod / 'localization/replace' / lang):
            loc[lang].update(load_localization(directory))
    rgb, bodies = {}, {}
    for folder in (GAME, mod):
        for p in (folder / 'common/cultures').glob('*.txt'):
            for c, body in objects(root(txt(p))):
                rgb[c] = read_color(body.text()); bodies[c] = body.text()
    minimum = float('inf')
    for c, spec in policy['assets'].items():
        validate_culture(c, cultures[c], traits, groups, faiths, loc)
        assert cultures[c]['heritage'] == spec['heritage']
        want_language = spec.get('language') or 'eu5_identity_language_' + spec['new_language'][0]
        assert cultures[c]['language'] == want_language
        assert [loc[l][c] for l in ('english', 'simp_chinese')] == spec['labels']
        strip = lambda s: re.sub(r'\b(?:heritage|language)\s*=\s*\w+', '', COLOR.sub('', s)).strip()
        assert strip(bodies[c]) == strip(bodies[spec['template']]), 'Unexpected template alteration'
        delta = float(np.linalg.norm(lab([v for k, v in rgb.items() if k != c]) - lab(rgb[c]), axis=1).min())
        assert delta >= 8, (c, delta)
        minimum = min(minimum, delta)
    used = {k[2] for k in actual}
    assert all(c in cultures for c in used)
    assert len(used) <= policy['budget']['max_used_cultures']
    assert len(cultures) <= policy['budget']['max_effective_cultures']
    assert len(actual) <= policy['budget']['max_population_groups']
    assert len(policy['assets']) <= policy['budget']['max_new_cultures']
    assert dr['culture_budget']['counts']['used_cultures'] == len(used)
    assert dr['culture_budget']['counts']['population_groups'] == len(actual)
    assert dr['culture_budget']['counts']['resident_assets'] == len(dr['custom_resident_cultures']['cultures']) <= dr['culture_budget']['limits']['max_resident_assets']
    assert read(demo / 'template_fallback/template_report.json')['candidate_culture_budget']['counts'] == dr['culture_budget']['counts']
    rates = parse_effects(mod / 'common/scripted_effects/zz_eu5_m4_literacy.txt')
    assert set(rates) == {k for k in actual if k in cents}, 'Missing or extra source literacy selector'
    literacy = verify_literacy(package, mod, package / 'literacy_base')
    old_meta, meta = read(base / '.metadata/metadata.json'), read(mod / '.metadata/metadata.json')
    assert {k: v for k, v in old_meta.items() if k != 'version'} == {k: v for k, v in meta.items() if k != 'version'}
    check = {'status': 'passed', 'corrected_source_mappings': len(policy['mappings']), 'new_culture_assets': len(policy['assets']),
             'new_heritages': 0, 'source_centipersons': sum(source_totals.values()),
             'population': sum(actual.values()), 'original_population': sum(original.values()),
             'population_groups': len(actual), 'used_cultures': len(used), 'effective_definitions': len(cultures),
             'changed_primary_countries': sorted(changed_countries), 'changed_rulers': actual_ruler_changes,
             'added_homeland_pairs': len(additions), 'deferred_homelands': evidence['deferred_homelands'],
             'minimum_color_delta_e': minimum,
             'source_allocation_and_both_integer_ledgers_verified': True,
             'all_state_owner_religion_totals_preserved': True,
             'political_borders_economy_and_existing_homelands_preserved': True,
             'country_and_character_source_identity_verified': True,
             'all_assets_and_literacy_selectors_resolved': True,
             'unrelated_files_byte_identical': True, 'runtime_verified': False}
    result = {'status': 'passed_static_runtime_pending', 'culture_identity': check, 'literacy': literacy,
              'package_report_sha256': digest(package / 'package_report.json'),
              'audit_sha256': {p: digest(package / p) for p in ['policy.snapshot.json', 'identity_correction.json']}}
    write(package / 'verification.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('package', type=Path)
    args = parser.parse_args()
    print(__import__('json').dumps(verify(args.package), ensure_ascii=False, indent=2))
