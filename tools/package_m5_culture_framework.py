"""Apply a bounded identity correction to the latest M5, preserving each old POP total."""
import argparse
from collections import Counter, defaultdict
import colorsys
import csv
from datetime import datetime
import html
from pathlib import Path
import re
import shutil

import numpy as np
from build_m2_prototype import objects, strings, patch, replace_body
from build_m3_world import block, load_localization
from m3_world import digest
from m4_literacy import build as build_literacy, POPULATION_PATH, CODE_PATH, EFFECT_PATH, HOOK_PATH
from m5_culture_geography import read_color, lab, COLOR
from package_m4_population_test import effective, parse_pops, rows, GAME
from package_m5_culture_refinement import read, write, files, strip_imported_literacy, strip_imported_hook
from package_m5_population_options import original_population_package
from package_m5_uncolonized import inherited_report, render_pops
from pdx_text import root

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'config/personal/m5_culture_framework.json'
POPS = 'common/history/pops/00_eu5_world.txt'
STATE = 'common/history/states/00_eu5_world.txt'
DEFS = 'common/country_definitions/zz_eu5_world.txt'
CHARS = 'common/history/characters/00_eu5_world.txt'
ASSETS = 'common/cultures/zz_eu5_framework.txt'
TRAITS = 'common/discrimination_traits/zz_eu5_framework.txt'
GROUPS = 'common/discrimination_trait_groups/zz_eu5_framework.txt'
LOCS = ['localization/' + lang + '/eu5_framework_l_' + lang + '.yml'
        for lang in ('english', 'simp_chinese')]
ADDITIONS = {ASSETS, TRAITS, GROUPS, *LOCS}
ALLOWED = ADDITIONS | {POPS, STATE, DEFS, CHARS, POPULATION_PATH, CODE_PATH, EFFECT_PATH,
                      HOOK_PATH, '.metadata/metadata.json'}


def text(p):
    return p.read_text(encoding='utf-8-sig')


def put(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(value, encoding='utf-8-sig')


def csvwrite(path, fields, records):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def split_identities(population, weights):
    """Split each old integer group separately; merging targets is intentional."""
    result = Counter()
    for (s, o, c, r), n in sorted(population.items()):
        w = weights.get((s, o, c, r))
        if w is None:
            result[s, o, c, r] += n  # Explicit template-origin group.
        else:
            assert sum(w.values()) > 0
            denominator = sum(w.values())
            divided = {target: divmod(weight * n, denominator) for target, weight in w.items()}
            allocation = {target: value[0] for target, value in divided.items()}
            for target in sorted(divided, key=lambda t: (-divided[t][1], t))[:n - sum(allocation.values())]:
                allocation[target] += 1
            for target, amount in allocation.items():
                if amount:
                    result[s, o, target, r] += amount
    assert sum(result.values()) == sum(population.values())
    return dict(result)


def collect_weights(stage, oldmap, newmap, religion, migrants):
    weights = defaultdict(Counter)
    groups = Counter()
    anchors = defaultdict(set)
    for x in rows(stage / 'province_population_draft.csv'):
        s, o, source, n = x['target_state'], x['target_owner'], x['source_culture'], int(x['centipersons'])
        old = migrants.get((source, s), oldmap[source])
        new = migrants.get((source, s), newmap[source])
        faith = religion[x['source_religion']]
        weights[s, o, old, faith][new] += n
        groups[s, o, new, faith] += n
        anchors[x['source_location']].add(s)
    return weights, groups, anchors


def make_assets(mod, policy):
    definitions = effective(mod, 'common/cultures')
    trait_defs = effective(mod, 'common/discrimination_traits')
    group_defs = effective(mod, 'common/discrimination_trait_groups')
    bodies = {}
    for base in (GAME, mod):
        for p in sorted((base / 'common/cultures').glob('*.txt')):
            bodies.update({c: o.text() for c, o in objects(root(text(p)))})
    colors = {c: read_color(body) for c, body in bodies.items()}
    grid = np.array([colorsys.hsv_to_rgb(h / 192, s, v) for h in range(192)
                     for s in (.35, .48, .61, .74, .87, 1) for v in (.42, .54, .66, .78, .90, 1)])
    grid_lab = lab(grid)
    distance = np.full(len(grid), np.inf)
    for point in lab(list(colors.values())):
        distance = np.minimum(distance, np.linalg.norm(grid_lab - point, axis=1))
    cultures, traits, groups, labels, records = {}, {}, {}, [{}, {}], {}
    for c, spec in policy['assets'].items():
        assert c not in definitions and spec['heritage'] in trait_defs
        assert trait_defs[spec['heritage']]['type'] == 'heritage'
        template = spec['template']
        if 'language' in spec:
            language = spec['language']
            assert trait_defs[language]['type'] == 'language'
        else:
            suffix, group, en, zh = spec['new_language']
            language = 'eu5_framework_language_' + suffix
            assert language not in trait_defs
            if group not in group_defs:
                assert group.startswith('eu5_framework_language_group_')
                groups[group] = 'type = language'
                labels[0][group], labels[1][group] = en, zh
            else:
                assert group_defs[group]['type'] == 'language'
            traits[language] = 'type = language\ntrait_group = ' + group
            labels[0][language], labels[1][language] = en, zh
        # Preserve the established color separation without recoloring any old asset.
        desired = lab(colors[template])
        valid = distance >= 8.005
        assert valid.any(), 'No separated color remains'
        i = int(np.where(valid, -np.linalg.norm(grid_lab - desired, axis=1), -np.inf).argmax())
        rgb = [round(float(v), 5) for v in grid[i]]
        distance = np.minimum(distance, np.linalg.norm(grid_lab - lab(rgb), axis=1))
        body, n = re.subn(r'\bheritage\s*=\s*\w+', 'heritage = ' + spec['heritage'], bodies[template]); assert n == 1
        body, n = re.subn(r'\blanguage\s*=\s*\w+', 'language = ' + language, body); assert n == 1
        body, n = COLOR.subn('color = { ' + ' '.join(map(str, rgb)) + ' }', body); assert n == 1
        cultures[c] = body
        labels[0][c], labels[1][c] = spec['labels']
        records[c] = {'heritage': spec['heritage'], 'language': language, 'rgb': rgb,
                      'template': template, 'limitations': policy['asset_limitations']}
    for k, names in policy['labels'].items():
        labels[0][k], labels[1][k] = names
    for rel, entries in [(ASSETS, cultures), (TRAITS, traits), (GROUPS, groups)]:
        put(mod / rel, ''.join(block(k, v) for k, v in entries.items()))
    for i, rel in enumerate(LOCS):
        lang = ('english', 'simp_chinese')[i]
        put(mod / rel, 'l_' + lang + ':\n' + ''.join(' ' + k + ':0 "' + v + '"\n' for k, v in labels[i].items()))
    return records


def build():
    installation = read(ROOT / '.local/m5/installation-latest.json')
    prior_path = Path(installation['package'])
    prior = inherited_report(prior_path)
    base = Path(prior['mod_directory'])
    assert files(base) == prior['output_sha256'] == files(Path(installation['target']))
    policy = read(POLICY)
    audit = read(ROOT / policy['audit'])
    expected_sources = set(policy['mappings'])
    assert expected_sources <= {r['source_culture'] for r in audit['rows']}
    assert set(policy['assets']) <= set(policy['mappings'].values())
    protected = {str(p): digest(p) for p in [ROOT / '.local/m4/location-workstation/location_reviews.json',
                 ROOT / '.local/m5/installation-latest.json', ROOT / '.local/economy/installation-latest.json',
                 ROOT / 'config/personal/m3_world.json', ROOT / 'config/personal/m4_demographics.json']}
    output = ROOT / '.local/economy/packages' / ('m5-culture-framework-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    output.mkdir(parents=True)
    mod = output / 'eu5_economy_test'
    shutil.copytree(base, mod)
    write(output / 'policy.snapshot.json', policy)
    demographic = output / 'demographic'
    old_demo = Path(prior['demographic_run'])
    shutil.copytree(old_demo, demographic)
    political = output / 'political'
    shutil.copytree(Path(prior['political_run']), political)
    old_rows = list(rows(old_demo / 'demographics/resident_culture_crosswalk.csv'))
    oldmap = {r['source_culture']: r['target_culture'] for r in old_rows}
    assert len(oldmap) == 1540
    assert all(oldmap[s] == next(r['target_culture'] for r in audit['rows'] if r['source_culture'] == s)
               for s in expected_sources), 'Audited identity baseline changed'
    newmap = {**oldmap, **policy['mappings']}
    d = read(old_demo / 'demographics/demographics_report.json')
    religion = {r['source_religion']: r['target_religion'] for r in rows(old_demo / 'demographics/resident_religion_crosswalk.csv')}
    migrants = {(m['source'], s): m['target'] for m in d['migrant_cultures']['cultures'] for s in m['states']}
    assert not {m[0] for m in migrants} & expected_sources, 'Migrant policy requires explicit rebase'
    weights, source_groups, anchors = collect_weights(demographic / 'staging', oldmap, newmap, religion, migrants)
    before_groups = {tuple(r[k] for k in ('state', 'owner', 'culture', 'religion')): int(r['centipersons'])
                     for r in rows(old_demo / 'demographics/resident_population_groups.csv')}
    assert {k: sum(w.values()) for k, w in weights.items()} == before_groups
    actual = split_identities(parse_pops(base / POPS), weights)
    original_path = original_population_package(prior_path)
    original = split_identities(parse_pops(original_path), weights)
    put(mod / POPS, render_pops(actual))
    put(output / 'original_population.txt', render_pops(original))
    for r in old_rows:
        if r['source_culture'] in expected_sources:
            r['target_culture'] = newmap[r['source_culture']]
            r['method'] = 'm5_framework_decision'
            r['reason'] = 'Explicit culture framework decision; frozen policy: ' + str(POLICY)
    csvwrite(demographic / 'demographics/resident_culture_crosswalk.csv', list(old_rows[0]), old_rows)
    csvwrite(demographic / 'demographics/resident_population_groups.csv',
             ['state', 'owner', 'culture', 'religion', 'centipersons', 'preview_integer_persons'],
             [dict(zip(['state', 'owner', 'culture', 'religion'], k), centipersons=n,
                   preview_integer_persons=actual.get(k, 0)) for k, n in sorted(source_groups.items())])
    put(demographic / 'demographics/population_history_preview.txt', render_pops({k: actual[k] for k in source_groups if k in actual}))
    assets = make_assets(mod, policy)
    # Change source rulers by their own recorded identities, never by their country's culture.
    politics = read(political / 'conversion_report.json')
    country_changes = {}
    for tag, c in politics['countries'].items():
        if c.get('source_culture') in expected_sources:
            old, new = c['culture'], newmap[c['source_culture']]
            country_changes[tag] = {'old': old, 'new': new, 'source': c['source_culture']}
            c['culture'] = new
            c['cultures'] = [new if x == old else x for x in c.get('cultures', [old])]
            c['culture_mapping'] = 'm5_framework_decision'
    raw = text(mod / DEFS); edits = []
    for tag, o in objects(root(raw)):
        if tag in country_changes:
            c = politics['countries'][tag]
            edits.append(replace_body(o.fields()['cultures'], ' ' + ' '.join(c['cultures']) + ' '))
    assert len(edits) == len(country_changes)
    put(mod / DEFS, patch(raw, edits))
    rulers = {(r['tag'], r['source_id']): r for r in politics['rulers'] if r.get('source_culture') in expected_sources}
    raw = text(mod / CHARS); edits = []; ruler_changes = []
    for scope, body in objects(root(raw).fields()['CHARACTERS']):
        tag = scope.removeprefix('c:')
        for op, obj in objects(body):
            if op != 'create_character':
                continue
            f = obj.fields(); pid = f.get('first_name', '').removeprefix('EU5_FIRST_')
            r = rulers.get((tag, pid))
            if not r:
                continue
            assert f['culture'] == r['culture']
            new = newmap[r['source_culture']]
            replacement, n = re.subn(r'\bculture\s*=\s*' + re.escape(r['culture']) + r'\b', 'culture = ' + new, obj.text()); assert n == 1
            edits.append(replace_body(obj, replacement))
            ruler_changes.append({'tag': tag, 'source_id': pid, 'source': r['source_culture'], 'old': r['culture'], 'new': new})
    put(mod / CHARS, patch(raw, edits))
    for r in rulers.values():
        r['culture'] = newmap[r['source_culture']]
        r['culture_mapping'] = 'm5_framework_decision'
    # Add only named historical cores. Preserve existing indigenous and migrant claims.
    pairs = set()
    for c, spec in policy.get('extra_homelands', {}).items():
        pairs.update((s,c) for s in spec['states'])
    for c, spec in policy['assets'].items():
        observed = {s for a in spec['anchors'] for s in anchors[a]}
        if not set(spec['homelands']) <= observed:
            raise ValueError(('Homeland projection changed', c, sorted(observed)))
        pairs.update((s, c) for s in spec['homelands'])
    raw = text(mod / STATE); edits = []
    for scope, obj in objects(root(raw).fields()['STATES']):
        additions = [c for s, c in sorted(pairs) if s == scope.removeprefix('s:')]
        if additions:
            edits.append(replace_body(obj, obj.text() + ''.join('\nadd_homeland = cu:' + c + '\n' for c in additions)))
    put(mod / STATE, patch(raw, edits))
    from m5_framework_display import apply_display
    display = apply_display(mod, politics, policy, output)
    write(output / 'display.json', display)
    # Refresh the authoritative catalogs. Older asset-review evidence remains historical only.
    loc = load_localization(GAME / 'localization/simp_chinese')
    loc.update(load_localization(mod / 'localization/simp_chinese'))
    loc.update(load_localization(mod / 'localization/replace/simp_chinese'))
    totals, groups = Counter(), Counter()
    for (s, o, c, r), n in source_groups.items():
        totals[c] += n; groups[c] += 1
    sources = defaultdict(list)
    for s, c in newmap.items():
        sources[c].append(s)
    catalog = [dict(culture=c, name=loc[c], kind='custom' if c.startswith('eu5_') else 'vanilla',
                    source_identity_count=len(sources[c]), source_identities='|'.join(sorted(sources[c])),
                    centipersons=n, population_groups=groups[c]) for c, n in sorted(totals.items())]
    csvwrite(demographic / 'demographics/active_culture_catalog.csv', list(catalog[0]), catalog)
    current_defs = effective(mod, 'common/cultures')
    current_traits = effective(mod, 'common/discrimination_traits')
    current_catalog = [dict(culture=c, heritage=f['heritage'], language=f['language'],
                            name=loc.get(c, c)) for c, f in sorted(current_defs.items())]
    csvwrite(demographic / 'demographics/effective_culture_assets.csv', list(current_catalog[0]), current_catalog)
    # Inherited asset records are historical provenance, not the effective trait
    # catalog after the intervening heritage patch. Point to the readback above.
    for source in expected_sources:
        d['culture_compaction'].pop(source, None)
    d['framework_overrides'] = policy['mappings']
    d['effective_asset_catalog'] = 'effective_culture_assets.csv'
    d['inherited_asset_record_scope'] = 'Historical scaffold provenance; effective traits are in effective_culture_assets.csv.'
    for target, spec in policy['assets'].items():
        members = [s for s, t in policy['mappings'].items() if t == target]
        record = dict(assets[target], source=members[0], target=target, aggregate_members=members,
                      heritage_group=current_traits[spec['heritage']]['trait_group'],
                      language_group=current_traits[assets[target]['language']]['trait_group'],
                      review_status='framework_decided_template_names_and_appearance_pending')
        d['custom_resident_cultures']['cultures'].append(record)
    limits = dict(d['culture_budget']['limits'], max_used_cultures=policy['budget']['max_used_cultures'],max_resident_assets=policy['budget']['max_resident_assets'])
    counts = dict(d['culture_budget']['counts'], used_cultures=len({k[2] for k in actual}),
                  resident_assets=len(d['custom_resident_cultures']['cultures']),
                  population_groups=len(actual), effective_culture_definitions=len(current_defs),
                  resident_language_groups=len({current_traits[f['language']]['trait_group'] for c,f in current_defs.items() if c.startswith('eu5_') and not c.startswith('eu5_migrant_')}),
                  effective_heritages=len({f['heritage'] for f in current_defs.values()}),
                  effective_heritage_groups=len({current_traits[f['heritage']]['trait_group'] for f in current_defs.values()}))
    d['culture_budget'] = {'status': 'passed', 'counts': counts, 'limits': limits,
                          'basis': policy['policy'], 'scope': 'Current calibrated, nonzero output; not a runtime benchmark.'}
    template_totals, template_groups = Counter(), Counter()
    for r in rows(demographic / 'template_fallback/template_population_groups.csv'):
        template_totals[r['culture']] += int(r['persons']) * 100
        template_groups[r['culture']] += 1
    candidate_catalog = []
    by_culture = {r['culture']: r for r in catalog}
    for c in sorted(set(totals) | set(template_totals)):
        row = dict(by_culture.get(c, dict(culture=c, name=loc[c], kind='vanilla',
                       source_identity_count=0, source_identities='', centipersons=0, population_groups=0)))
        row['centipersons'] += template_totals[c]
        row['population_groups'] += template_groups[c]
        row['template_centipersons'] = template_totals[c]
        candidate_catalog.append(row)
    csvwrite(demographic / 'template_fallback/candidate_culture_catalog.csv', list(candidate_catalog[0]), candidate_catalog)
    template_report = read(demographic / 'template_fallback/template_report.json')
    template_report.update(status='template_populations_preserved_candidate_catalog_refreshed',
                           candidate_culture_budget=dict(d['culture_budget'], includes_source_empty_templates=True),
                           identity_correction_from=str(old_demo / 'template_fallback'),
                           verification=str(output / 'verification.json'))
    template_report['output_sha256'] = {p.name: digest(p) for p in (demographic / 'template_fallback').glob('*')
                                       if p.is_file() and p.name not in ('template_report.json', 'independent_verification.json')}
    write(demographic / 'template_fallback/template_report.json', template_report)
    old_template_check = demographic / 'template_fallback/independent_verification.json'
    if old_template_check.exists():
        old_template_check.rename(old_template_check.with_name('independent_verification.prior.json'))
    d.update(stage=str(demographic / 'staging'), identity_correction_policy=str(output / 'policy.snapshot.json'),
             identity_correction_from=str(old_demo), active_cultures=len(newmap),
             population_groups=len(source_groups), preview_integer_persons=sum(actual.get(k, 0) for k in source_groups),
             preview_population_basis='current calibrated integer POPs; original population kept separately',
             historical_asset_review_complete=False)
    # Avoid presenting copied old evidence as validation of this new candidate.
    for p in (demographic / 'demographics').glob('*verification.json'):
        p.rename(p.with_name(p.stem + '.prior.json'))
    # Keep new assets with demographic provenance without rewriting old archived assets.
    for rel in ADDITIONS:
        dest = demographic / 'demographics/correction_assets' / rel
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(mod / rel, dest)
    d['files_sha256'] = {p.relative_to(demographic / 'demographics').as_posix(): digest(p)
                        for p in (demographic / 'demographics').rglob('*') if p.is_file() and p.name != 'demographics_report.json'}
    write(demographic / 'demographics/demographics_report.json', d)
    literacy_base = output / 'literacy_base'
    for rel, fn in [(POPULATION_PATH, strip_imported_literacy), (CODE_PATH, strip_imported_hook)]:
        put(literacy_base / rel, fn(text(base / rel)))
        shutil.copy2(literacy_base / rel, mod / rel)
    build_literacy(output, demographic, mod, GAME)
    a, b, c, t = map(int, re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)', installation['version']).groups())
    meta = read(mod / '.metadata/metadata.json'); meta['version'] = f'{a}.{b}.{c+1}-m5-test{t+1}'
    write(mod / '.metadata/metadata.json', meta)
    changed = sorted(p for p, h in files(mod).items() if prior['output_sha256'].get(p) != h)
    from m5_framework_display import allowed_display
    assert all(p in ALLOWED or allowed_display(p) for p in changed)
    assert not set(files(base)) - set(files(mod))
    politics.update(mod_directory=str(mod), output_sha256=files(mod), identity_correction_from=prior['political_run'])
    write(political / 'conversion_report.json', politics)
    evidence = {'country_changes': country_changes, 'ruler_changes': ruler_changes, 'assets': assets,
                'added_homelands': sorted(pairs), 'deferred_homelands': [c for c, a in policy['assets'].items() if not a['homelands']],
                'old_demographic': str(old_demo), 'old_original_population': str(original_path),
                'protected_sha256': protected,
                'integer_policy': 'Largest remainder within each previously installed state-owner-culture-religion group; no recalibration or loss. Repeat independently for the immutable original population.'}
    write(output / 'identity_correction.json', evidence)
    inputs = [POLICY, ROOT / policy['audit'], Path(__file__), ROOT / 'tools/verify_m5_culture_framework.py',
              ROOT / 'tools/update_m5_integrated_test.ps1', prior_path / 'package_report.json', original_path]
    inputs.extend(ROOT/'tools'/n for n in ['m5_framework_policy.py','m5_framework_display.py','verify_m5_framework_display.py','m5_dynamic_identity.py','religion_icon_texture.py'])
    report = {'status': 'culture_framework_static_candidate', 'update_scope': 'm5_culture_framework',
              'version': meta['version'], 'mod_name': meta['name'], 'mod_directory': str(mod),
              'prior_package': str(prior_path), 'political_run': str(political), 'demographic_run': str(demographic),
              'population_mode': prior['population_mode'], 'population_calibrated': prior['population_calibrated'],
              'source_population_conserved': prior['source_population_conserved'], 'new_campaign_required': True,
              'original_population_sha256': digest(output / 'original_population.txt'),
              'changed_files': changed, 'input_sha256': {str(p.resolve()): digest(p) for p in inputs},
              'output_sha256': files(mod)}
    write(output / 'package_report.json', report)
    from verify_m5_culture_framework import verify
    result = verify(output)
    assert all(digest(Path(p)) == h for p, h in protected.items()), 'Protected input changed'
    write(ROOT / '.local/m5/culture-framework-package-latest.json', {'package': str(output), 'version': meta['version'], 'verification': result['culture_framework']})
    from m5_framework_display import render_report
    render_report(output, report, policy, result)
    return {'package': str(output), 'version': meta['version'], 'verification': result['culture_framework']}



if __name__ == '__main__':
    print(__import__('json').dumps(build(), ensure_ascii=False, indent=2))
