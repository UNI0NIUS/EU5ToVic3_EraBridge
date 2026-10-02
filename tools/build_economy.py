"""Generate a reviewable economic overlay; no installation or game writes."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re

from economy_model import (Target, apportioned, block, british_baseline, building_rows,
                           closure, definitions, industry_mapping, map_technology, render_buildings)
from extract_m3_politics import fields, sequence
from m3_world import digest
from pdx_text import Object, root
from technology_mapping import TechnologyMapper
from economy_infrastructure import support


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def rows(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def expand_template_tech(obj, effects, target):
    result = set()
    for key, value in obj.entries():
        if key == 'add_technology_researched': result.add(value)
        elif key == 'add_era_researched':
            result.update(k for k, f in target.techs.items() if f['era'] == value and f.get('can_research') != 'no')
        elif key and key.startswith('effect_starting_technology_'):
            result.update(expand_template_tech(effects[key], effects, target))
    return result


def build(source_path, package, game, eu5, baseline_path, config_path, output):
    if output.exists(): raise ValueError('Refusing to overwrite economic run')
    source, config = load(source_path), load(config_path)
    package_report = load(package/'package_report.json')
    mod = Path(package_report['mod_directory'])
    political_run = Path(package_report['political_run'])
    political = load(political_run/'conversion_report.json')
    demographic = Path(package_report['demographic_run'])
    stage = demographic/'staging'
    stage_report = load(stage/'staging_report.json')
    if source['source_sha256'] != political['source_sha256'] or source['source_sha256'] != stage_report['source_sha256']:
        raise ValueError('Economic and territorial source mismatch')
    for rel, sha in package_report['output_sha256'].items():
        if digest(mod/rel) != sha: raise ValueError('Baseline package changed: '+rel)
    for rel, sha in stage_report['files_sha256'].items():
        if digest(stage/rel) != sha: raise ValueError('Population stage changed: '+rel)
    target = Target(game)
    baseline = british_baseline(baseline_path, target)
    mapper = TechnologyMapper(eu5, target, baseline['technologies'], config['technology_progression'], config['technology_rules'])
    mapping, stages = industry_mapping(eu5, config)
    source_advances = definitions(eu5/'in_game/common/advances')
    for rule in config['technology_rules']:
        for advance in rule.get('advances_all', [])+rule.get('advances_any', []):
            if advance not in source_advances: raise ValueError('Undefined source advance: '+advance)
        if rule['target'] not in target.techs: raise ValueError('Undefined target technology')
    industries = set(mapping.values())
    resources = set(config['raw_materials'].values())
    managed = industries | resources
    if managed - target.buildings.keys(): raise ValueError('Undefined target building')
    old_buildings = building_rows(mod/'common/history/buildings/00_eu5_world.txt')
    effects = {k: o for k, o in root((game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries()
               if isinstance(o, Object)}
    country_doc = fields(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    history = {k[2:]: o for k, o in country_doc.entries()}
    researched, proposed, tech_report, laws = {}, {}, {}, {}
    for tag, country in political['countries'].items():
        sid = country['source_id']
        old = expand_template_tech(history[tag], effects, target)
        laws[tag] = {v.split(':')[-1] for k, v in history[tag].entries() if k == 'activate_law'}
        if sid is None:
            researched[tag] = old; continue
        mapped, report = mapper.map(source['countries'][str(sid)])
        # This task changes economics. Army and society proposals are reported,
        # while existing military/law setup continues using its original techs.
        production = {t for t in mapped if target.techs[t]['category'] == 'production'}
        retained = {t for t in old if target.techs[t]['category'] != 'production'}
        researched[tag] = closure(production | retained, target.techs)
        proposed[tag] = mapped
        report['applied_production'] = sorted(t for t in researched[tag] if target.techs[t]['category'] == 'production')
        report['compatibility_prerequisites'] = sorted(researched[tag] - production - retained)
        report['source_advance_count'] = len(source['countries'][str(sid)]['advances'])
        report['source_age_counts'] = dict(Counter(source_advances[a].get('age', 'special') for a in source['countries'][str(sid)]['advances'] if a in source_advances))
        tech_report[tag] = report
    # Use the already reviewed population links, so split locations retain their
    # exact territorial proportions rather than being sent to a national capital.
    links = defaultdict(Counter)
    for r in rows(stage/'province_population_draft.csv'):
        links[r['source_location']][r['target_state'], r['target_owner']] += int(r['centipersons'])
    for name, weights in links.items():
        total = sum(weights.values())
        links[name] = {k: v/total for k, v in weights.items()}
    population = Counter()
    for r in rows(demographic/'demographics/resident_population_groups.csv'):
        population[r['state'], r['owner']] += int(r['preview_integer_persons'])
    for r in rows(demographic/'template_fallback/template_population_groups.csv'):
        population[r['state'], r['owner']] += int(r['persons'])
    national_pop = Counter()
    for (state, tag), n in population.items(): national_pop[tag] += n
    weights, unmapped, source_types = Counter(), [], Counter()
    # Keep ceramic evidence even though V3 has one combined glassworks building.
    # Ordinary pottery is not promoted to luxury porcelain without source evidence.
    product_types = {}
    for filename, product in [('production_glass','glass'),('production_porcelain','porcelain'),('production_pottery','pottery')]:
        for key, obj in root((eu5/'in_game/common/building_types'/(filename+'.txt')).read_text(encoding='utf-8-sig')).entries():
            if isinstance(obj,Object): product_types[key] = product
    product_weights = defaultdict(Counter)
    employment_constants = {}
    for key, val in root((eu5/'main_menu/common/script_values/default_values.txt').read_text(encoding='utf-8-sig')).entries():
        if key in ('guild_employment', 'workshop_employment', 'manufactory_employment', 'mills_employment'):
            employment_constants[key.replace('_employment', '').replace('mills', 'mill')] = float(val)*1000
    for b in source['buildings']:
        kind = mapping.get(b['type'])
        if not kind: continue
        location = source['locations'][b['location']]
        stage_name = stages[b['type']]
        occupied = float(b.get('employed', 0))*1000
        capacity = int(b.get('level', 0))*employment_constants[stage_name]
        # 75% observed employment + 25% installed capacity protects partly idle
        # factories without treating every empty factory as fully productive.
        weight = (0.75*occupied + 0.25*capacity)*config['calibration']['stage_weights'][stage_name]
        source_types[b['type']] += weight
        if location['name'] not in links:
            unmapped.append({'id': b['id'], 'type': b['type'], 'location': location['name'], 'score': weight}); continue
        for (state, tag), fraction in links[location['name']].items():
            weights[state, tag, kind] += weight*fraction
            if b['type'] in product_types:
                product_weights[state,tag][product_types[b['type']]] += weight*fraction
    for location in source['locations'].values():
        kind = config['raw_materials'].get(location['raw_material'])
        if not kind: continue
        for (state, tag), fraction in links.get(location['name'], {}).items():
            weights[state, tag, kind] += location['rgo_workers']*fraction
    scores = Counter()
    for (state, tag, kind), weight in weights.items():
        if kind in industries: scores[tag] += weight
    calibration = config['calibration']
    intensities = sorted(scores[t]/n for t, n in national_pop.items() if n >= calibration['frontier_population_min'] and scores[t] > 0)
    if not intensities: raise ValueError('No frontier calibration countries')
    frontier = intensities[math.ceil((len(intensities)-1)*calibration['frontier_quantile'])]
    uk_pms = defaultdict(set); uk_gross = Counter(); uk_jobs = Counter(); uk_levels = Counter()
    for r in baseline['buildings']:
        kind = r['building']; uk_levels[kind] += r['levels']; uk_pms[kind].update(r['pms'])
        if kind not in managed: continue
        c = target.coefficients(kind, r['pms'], set(baseline['technologies']))
        uk_gross[kind] += c['gross']*r['levels']; uk_jobs[kind] += c['jobs']*r['levels']
    gross_per_person = sum(uk_gross[k] for k in industries)/baseline['population']
    scalar = gross_per_person/frontier
    resource_scores = Counter()
    for (state, tag, kind), weight in weights.items():
        if kind in resources: resource_scores[tag] += weight
    resource_intensities = sorted(resource_scores[t]/n for t,n in national_pop.items()
                                 if n >= calibration['frontier_population_min'] and resource_scores[t] > 0)
    resource_frontier = resource_intensities[math.ceil((len(resource_intensities)-1)*calibration['frontier_quantile'])]
    resource_scalar = sum(uk_gross[k] for k in resources)/baseline['population']/resource_frontier
    selected, coefficients, floating = {}, {}, {}
    rejected = []
    owners = load(political_run/'province_owners.json')
    for (state, tag, kind), weight in sorted(weights.items()):
        if weight <= 0: continue
        if fields(target.buildings[kind].get('potential')).get('is_coastal') == 'yes':
            if 'naval_exit_id' not in target.states[state] or owners[state].get(target.states[state].get('port')) != tag:
                rejected.append({'state': state, 'country': tag, 'building': kind, 'reason': 'no_owned_state_port', 'score': weight}); continue
        if not set(sequence(target.buildings[kind].get('unlocking_technologies'))) <= researched[tag]:
            rejected.append({'state': state, 'country': tag, 'building': kind, 'reason': 'building_technology_locked', 'score': weight}); continue
        pair = state, tag, kind
        if pair not in selected:
            selected[pair] = target.select(kind, researched[tag], uk_pms[kind], laws[tag])
            if kind == 'building_glassworks':
                from economy_supply_chain import source_glass_methods
                selected[pair] = source_glass_methods(target,selected[pair],researched[tag],laws[tag],product_weights[state,tag])
            coefficients[pair] = target.coefficients(kind, selected[pair], researched[tag])
        c = coefficients[pair]
        if c['gross'] <= 0 or c['jobs'] <= 0: raise ValueError('Invalid production coefficients: '+kind)
        if kind in industries:
            intensity = scores[tag]/national_pop[tag]
            limiter = min(1, calibration['maximum_relative_intensity']*frontier/intensity)
            desired_gross = weight*scalar*limiter
        else:
            # Preserve actual extraction intensity as well as its distribution.
            intensity = resource_scores[tag]/national_pop[tag]
            limiter = min(1, calibration['maximum_relative_intensity']*resource_frontier/intensity)
            desired_gross = weight*resource_scalar*limiter
        floating[state, tag, kind] = desired_gross/c['gross']
    # Aggregate rounding by country/industry conserves intended capacity.
    groups = defaultdict(dict)
    for (state, tag, kind), value in floating.items(): groups[tag, kind][state] = value
    levels = {(s, t, k): n for (t, k), ws in groups.items() for s, n in apportioned(ws).items() if n}
    caps = []
    for state, province_owners in owners.items():
        shares = Counter(province_owners.values())
        for kind in resources:
            capacity = int(fields(target.states[state].get('capped_resources')).get(kind, 0))
            split = apportioned(shares, capacity)
            for tag, cap in split.items():
                key = state, tag, kind
                if levels.get(key, 0) > cap:
                    caps.append({'state': state, 'country': tag, 'building': kind, 'before': levels[key], 'after': cap, 'reason': 'resource_cap'})
                    levels[key] = cap
    retained, removals, downgraded = [], [], []
    for row in old_buildings:
        tag, kind = row['owner'], target.aliases.get(row['building'], row['building'])
        if political['countries'][tag]['source_id'] is not None and kind in managed: continue
        if political['countries'][tag]['source_id'] is not None:
            missing = set(sequence(target.buildings[kind].get('unlocking_technologies'))) - researched[tag]
            if missing:
                removals.append({'state': row['state'], 'country': tag, 'building': kind, 'levels': row['levels'], 'missing': sorted(missing)})
                continue
            pms = []
            for pm in row['pms']:
                missing = set(sequence(target.pms[pm].get('unlocking_technologies'))) - researched[tag]
                if missing:
                    group = next(g for g in sequence(target.buildings[kind].get('production_method_groups')) if pm in sequence(target.groups[g]['production_methods']))
                    candidates = [p for p in sequence(target.groups[group]['production_methods']) if target.available(p, researched[tag], laws[tag])]
                    if not candidates: raise ValueError('Cannot downgrade retained PM: '+pm)
                    replacement = candidates[0]
                    downgraded.append({'country': tag, 'state': row['state'], 'from': pm, 'to': replacement})
                    pms.append(replacement)
                else: pms.append(pm)
            if pms != row['pms']:
                row['body'] = re.sub(r'activate_production_methods\s*=\s*\{[^}]*\}', 'activate_production_methods = { '+' '.join(pms)+' }', row['body'])
                row['pms'] = pms
        retained.append(row)
    retained_jobs = Counter()
    for r in retained:
        retained_jobs[r['state'], r['owner']] += max(0, target.coefficients(r['building'], r['pms'], researched[r['owner']])['jobs'])*r['levels']
    for state, tag in sorted(population):
        keys = [k for k in levels if k[:2] == (state, tag) and levels[k] > 0]
        jobs = sum(levels[k]*coefficients[k]['jobs'] for k in keys)
        budget = max(0, population[state, tag]*calibration['workforce_share_ceiling']-retained_jobs[state, tag])
        industry_jobs = sum(levels[k]*coefficients[k]['jobs'] for k in keys if k[2] in industries)
        industry_budget = population[state, tag]*calibration['industrial_workforce_share_ceiling']
        for k in keys:
            factor = min(1, budget/jobs if jobs else 1,
                         industry_budget/industry_jobs if industry_jobs and k[2] in industries else 1)
            n = math.floor(levels[k]*factor)
            if n < levels[k]:
                caps.append({'state': state, 'country': tag, 'building': k[2], 'before': levels[k], 'after': n, 'reason': 'workforce_cap'})
                levels[k] = n
    generated = [{'state': s, 'owner': t, 'building': k, 'levels': n, 'pms': selected[s, t, k]}
                 for (s, t, k), n in sorted(levels.items()) if n > 0 and political['countries'][t]['source_id'] is not None]
    infrastructure = support(target, retained, generated, population, researched, laws, owners, uk_pms, calibration)
    # Economic and technology file overlay only; source package is immutable.
    building_text = render_buildings(retained+generated)
    countries = []
    for tag, obj in sorted(history.items()):
        body = obj.text()
        if tag in tech_report:
            body = re.sub(r'(?m)^\s*effect_starting_technology_\w+\s*=\s*yes\s*$', '', body)
            body = re.sub(r'(?m)^\s*add_technology_researched\s*=\s*\w+\s*$', '', body)
            body = ''.join('add_technology_researched = '+t+'\n' for t in sorted(researched[tag]))+body
        countries.append(block('c:'+tag, body).replace(' = {', ' ?= {', 1))
    output.mkdir(parents=True)
    overlay = output/'overlay/common/history'
    (overlay/'buildings').mkdir(parents=True); (overlay/'countries').mkdir()
    (overlay/'buildings/00_eu5_world.txt').write_text(building_text, encoding='utf-8-sig')
    (overlay/'countries/00_eu5_world.txt').write_text(block('COUNTRIES', ''.join(countries)), encoding='utf-8-sig')
    write_json(output/'technology_mapping.json', tech_report)
    write_json(output/'source_glass_products.json',[
        {'state':s,'country':t,'weighted_source_products':dict(v),
         'chosen_methods':selected.get((s,t,'building_glassworks'),[]),
         'note':'Dominant source porcelain selects native ceramics; pottery remains an unresolved basic-housewares mapping, not luxury porcelain. Input availability is checked by the capacity pass.'}
        for (s,t),v in sorted(product_weights.items())])
    write_json(output/'technology_catalogue.json', mapper.catalogue_report())
    write_json(output/'infrastructure.json', infrastructure)
    write_json(output/'british_baseline.json', {**baseline, 'levels': dict(uk_levels), 'managed_gross': dict(uk_gross), 'managed_jobs': dict(uk_jobs)})
    totals, supply, demand, jobs = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), Counter()
    for r in retained+generated:
        tag, kind, n = r['owner'], r['building'], r['levels']; totals[tag][kind] += n
        c = target.coefficients(kind, r['pms'], researched[tag]); jobs[tag] += c['jobs']*n
        for g, v in c['outputs'].items(): supply[tag][g] += v*n
        for g, v in c['inputs'].items(): demand[tag][g] += v*n
    summary = {}
    for tag in sorted(national_pop):
        summary[tag] = {'population': national_pop[tag], 'industrial_score': scores[tag],
                        'relative_industrial_intensity': scores[tag]/national_pop[tag]/frontier if national_pop[tag] else 0,
                        'building_levels': dict(totals[tag]), 'building_job_capacity': jobs[tag],
                        'domestic_industrial_input_gaps': {g: round(v-supply[tag][g], 3) for g, v in demand[tag].items() if v > supply[tag][g]},
                        'production_technologies': sorted(t for t in researched[tag] if target.techs[t]['category'] == 'production')}
    write_json(output/'country_economy.json', summary)
    with (output/'building_levels.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(['state','country','building','levels','production_methods','jobs_per_level','gross_base_price_per_level'])
        for r in generated:
            c = target.coefficients(r['building'], r['pms'], researched[r['owner']])
            writer.writerow([r['state'], r['owner'], r['building'], r['levels'], ';'.join(r['pms']), c['jobs'], c['gross']])
    report = {'schema': 1, 'status': 'economic_candidate_runtime_pending', 'full_conversion_ready': False,
              'source_sha256': source['source_sha256'], 'p001_skipped': source['p001_skipped'],
              'baseline_package': str(package.resolve()), 'frontier_intensity': frontier,
              'british_industrial_gross_per_person': gross_per_person, 'score_to_gross': scalar,
              'resource_frontier_intensity': resource_frontier, 'resource_score_to_gross': resource_scalar,
              'generated_rows': len(generated), 'generated_levels': sum(r['levels'] for r in generated),
              'retained_rows': len(retained), 'caps': caps, 'locked_source_capacity': rejected,
              'unmapped_industrial_buildings': unmapped, 'removed_locked_template_buildings': removals,
              'downgraded_template_pms': downgraded,
              'input_sha256': {str(p.resolve()): digest(p) for p in (source_path, config_path, baseline_path, package/'package_report.json', stage/'staging_report.json')},
              'limitations': ['Gross output is not GDP; no runtime prices or trade simulation.',
                              'Military/society mappings are proposals; only production mapping is applied.',
                              'Farms, government, military and ports retain template levels, with locked PM downgrades.',
                              'Resource caps use province shares; no capacity is silently moved to another state.',
                              'No scale economies, state traits or market price modifiers in base-price estimates.',
                              'Input gaps omit subsistence and trade and do not establish market shortages.',
                              'Infrastructure is statically estimated; qualifications, wages and five-year solvency require runtime testing.']}
    write_json(output/'economy_report.json', report)
    verification = verify(output, target, population, political, researched, managed)
    write_json(output/'verification.json', verification)
    definition_paths = []
    for directory in ('common/technology/technologies', 'common/buildings', 'common/building_groups', 'common/production_methods',
                      'common/production_method_groups', 'common/goods', 'common/state_traits', 'common/static_modifiers',
                      'map_data/state_regions', 'common/defines'):
        definition_paths.extend((game/directory).glob('*.txt'))
    for directory in ('in_game/common/advances', 'in_game/common/building_types'):
        definition_paths.extend((eu5/directory).glob('*.txt'))
    definition_paths += [eu5/'main_menu/common/script_values/default_values.txt',
                         eu5/'main_menu/localization/simp_chinese/advances_l_simp_chinese.yml',
                         game/'common/scripted_effects/00_starting_inventions.txt']
    write_json(output/'manifest.json', {'definitions': {str(p.resolve()):digest(p) for p in sorted(definition_paths)},
                                       'tools': {p.name:digest(p) for p in (Path(__file__), Path(__file__).with_name('economy_model.py'),
                                                                         Path(__file__).with_name('economy_supply_chain.py'),
                                                                         Path(__file__).with_name('technology_mapping.py'),
                                                                         Path(__file__).with_name('economy_infrastructure.py'))},
                                       'outputs': {p.relative_to(output).as_posix():digest(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return {k: report[k] for k in ('status', 'generated_rows', 'generated_levels')}


def verify(output, target, population, political, researched, managed):
    actual = building_rows(output/'overlay/common/history/buildings/00_eu5_world.txt')
    seen = set(); caps = Counter(); errors = []
    for r in actual:
        key = r['state'], r['owner'], r['building']
        if key in seen: errors.append('Duplicate building '+str(key))
        seen.add(key)
        if key[:2] not in population: errors.append('Unknown state owner '+str(key))
        if r['levels'] <= 0: errors.append('Nonpositive building '+str(key))
        techs = researched[r['owner']]
        if not set(sequence(target.buildings[r['building']].get('unlocking_technologies'))) <= techs:
            errors.append('Locked building '+str(key))
        pmgroups = sequence(target.buildings[r['building']].get('production_method_groups'))
        selected_groups = []
        for pm in r['pms']:
            matching = [g for g in pmgroups if pm in sequence(target.groups[g]['production_methods'])]
            if len(matching) != 1: errors.append('PM does not match building '+str(key)+' '+pm)
            selected_groups += matching
            if not set(sequence(target.pms[pm].get('unlocking_technologies'))) <= techs:
                errors.append('Locked PM '+str(key)+' '+pm)
        if len(selected_groups) != len(set(selected_groups)): errors.append('Duplicate PM group '+str(key))
        caps[r['state'], r['building']] += r['levels']
    for (s, b), n in caps.items():
        defined = fields(target.states[s].get('capped_resources'))
        if b in managed and b in defined and n > int(defined[b]): errors.append('Resource cap exceeded '+s+' '+b)
    doc = fields(root((output/'overlay/common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    for key, obj in doc.entries():
        tag = key[2:]
        ts = {v for k, v in obj.entries() if k == 'add_technology_researched'}
        if political['countries'][tag]['source_id'] is not None and ts != researched[tag]: errors.append('Technology export mismatch '+tag)
        if political['countries'][tag]['source_id'] is not None and closure(ts, target.techs) != ts: errors.append('Missing prerequisite '+tag)
    if errors: raise ValueError('Economic verification failed: '+json.dumps(errors[:20]))
    return {'status': 'passed_static_readback_runtime_pending', 'buildings': len(actual), 'countries': len(researched),
            'checks': ['unique_building_scopes', 'positive_levels', 'state_owner_exists', 'building_and_pm_technology',
                       'pm_group_membership', 'resource_caps', 'technology_export_and_prerequisite_closure']}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('source', 'package', 'game', 'eu5', 'baseline', 'config', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.source, a.package, a.game, a.eu5, a.baseline, a.config, a.output)))
