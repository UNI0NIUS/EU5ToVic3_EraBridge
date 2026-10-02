"""Apply a hash-pinned political review to an existing M5 package, never install it.

Society technology comes from source evidence and explicit compatibility roots.
Production/military establishments, territory, cultures and diplomatic scripts survive.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil

from pdx_text import Object, root
from extract_m3_politics import fields, sequence
from economy_model import Target, block, building_rows, closure, definitions, map_technology, render_buildings
from build_economy import expand_template_tech
from complete_economy import active_laws, support_good
from economy_capacity import Ledger
from economy_bureaucracy import AdministrationBudget, institution_levels
from economy_development import manufacturing_kinds


ROOT = Path(__file__).resolve().parents[1]
HISTORY = 'common/history/countries/00_eu5_world.txt'
BUILDINGS = 'common/history/buildings/00_eu5_world.txt'
ALLOWED = {'.metadata/metadata.json', HISTORY, BUILDINGS}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
def countries(text): return {k[2:]: v for k, v in fields(root(text))['COUNTRIES'].entries()}


def strip_politics(body):
    body = re.sub(r'(?m)^\s*(?:effect_starting_politics_\w+|effect_starting_technology_\w+|activate_law|add_technology_researched|add_era_researched)\s*=\s*[^\s{}]+\s*$', '', body)
    body = re.sub(r'\bset_institution_investment_level\s*=\s*\{[^{}]*\}', '', body)
    for key, value in root(body).entries():
        if key in ('activate_law', 'add_technology_researched', 'add_era_researched', 'set_institution_investment_level') or key.startswith(('effect_starting_politics_', 'effect_starting_technology_')):
            raise ValueError('Unresolved political history command: '+key)
        if isinstance(value, Object) and re.search(r'\b(?:activate_law|set_institution_investment_level|add_technology_researched)\s*=', value.text()):
            raise ValueError('Conditional political initialization requires explicit handling: '+key)
    return body


def deployment_laws(candidate, lawdefs):
    chosen = {g: r['law'] for g, r in candidate['laws'].items() if r['law']}
    overrides = []
    if 'law_eu5_bakufu' in lawdefs:
        for group,law in list(chosen.items()):
            if law=='law_bakufu':
                chosen[group]='law_eu5_bakufu'
                overrides.append({'group':group,'review_law':law,'deployed_law':'law_eu5_bakufu',
                                  'reason':'imported_shogunate_preserves_union_and_avoids_JAP_only_events'})
    # A decentralized society has no state service institutions. Avoid enabling
    # one implicitly at level one merely by exporting the draft's reference law.
    if candidate['target_country_type'] == 'decentralized':
        inactive = {'lawgroup_policing': 'law_no_police', 'lawgroup_education_system': 'law_no_schools',
                    'lawgroup_colonization': 'law_no_colonial_affairs', 'lawgroup_internal_security': 'law_no_home_affairs',
                    'lawgroup_health_system': 'law_no_health_system', 'lawgroup_welfare': 'law_no_social_security',
                    'lawgroup_labor_rights': 'law_no_workers_rights'}
        for group, law in list(chosen.items()):
            if lawdefs[law].get('institution'):
                overrides.append({'group': group, 'review_law': law, 'deployed_law': inactive[group],
                                  'reason': 'decentralized_no_state_institutions'})
                chosen[group] = inactive[group]
    validate_laws(chosen, lawdefs)
    return chosen, overrides


def validate_laws(chosen, lawdefs):
    laws = set(chosen.values())
    for group, law in chosen.items():
        if lawdefs[law]['group'] != group: raise ValueError('Wrong law group: '+law)
        conflicts = laws.intersection(sequence(lawdefs[law].get('disallowing_laws')))
        if conflicts: raise ValueError('Law conflict: '+law+' '+str(conflicts))


def technology_roots(old, candidate, source, laws, lawdefs, target, economic_rules, rows, extra):
    reasons = defaultdict(list)
    for tech in old:
        if target.techs[tech]['category'] != 'society': reasons[tech].append('preserved_production_or_military')
    _, mapped = map_technology(source, economic_rules, target.techs)
    for tech in mapped['direct']:
        if target.techs[tech]['category'] == 'society': reasons[tech].append('source_evidence:'+mapped['direct'][tech])
    for tech, evidence in candidate['capability_technology_proposals'].items(): reasons[tech].extend(evidence)
    for law in laws:
        for tech in sequence(lawdefs[law].get('unlocking_technologies')): reasons[tech].append('law:'+law)
    for row in rows:
        for tech in sequence(target.buildings[row['building']].get('unlocking_technologies')):
            reasons[tech].append('existing_building:'+row['building'])
        for pm in row['pms']:
            # A law-incompatible PM will be replaced, not used to import more tech.
            if not target.available(pm, set(target.techs), laws): continue
            for tech in sequence(target.pms[pm].get('unlocking_technologies')): reasons[tech].append('existing_pm:'+pm)
    for tech in extra: reasons[tech].append('preserved_diplomatic_prerequisite')
    reasons = {t: sorted(set(r)) for t, r in sorted(reasons.items())}
    selected = closure(reasons, target.techs)
    return selected, {'roots': reasons, 'prerequisites': sorted(selected-set(reasons)),
                      'removed': sorted(old-selected), 'added': sorted(selected-old),
                      'democracy_roots': [t for t in reasons if 'democracy' in closure({t}, target.techs)]}


def institution_plan(candidate, laws, techs, lawdefs, target):
    enabled = {lawdefs[l]['institution'] for l in laws if lawdefs[l].get('institution')}
    levels, caps = {}, {}
    for inst in sorted(enabled):
        key = 'country_'+inst+'_max_investment_add'
        cap = sum(int(fields(f.get('modifier')).get(key, 0)) for f in
                  [*(lawdefs[l] for l in laws), *(target.techs[t] for t in techs)])
        caps[inst] = min(5, max(1, cap))
        levels[inst] = min(caps[inst], max(1, candidate['institutions'][inst]['planned_level']))
    return levels, caps


def history_body(old, laws, techs, institutions):
    text = ''.join('add_technology_researched = '+t+'\n' for t in sorted(techs))
    # Governance and power first; explicit final laws, without regional macros.
    groups = sorted(laws, key=lambda g: (g not in ('lawgroup_governance_principles', 'lawgroup_distribution_of_power'), g))
    text += ''.join('activate_law = law_type:'+laws[g]+'\n' for g in groups)
    text += ''.join('set_institution_investment_level = { institution = '+i+' level = '+str(n)+' }\n' for i, n in sorted(institutions.items()))
    return text+strip_politics(old)


class ExistingDevelopmentEnvelope:
    """Reuse the last reviewed industrial ceilings rather than recalibrating them."""
    def __init__(self, ledger, report):
        self.ledger, self.profiles = ledger, report['countries']
        self.manufacturing = manufacturing_kinds(ledger.target)

    def jobs(self, tag):
        return sum(self.ledger.coefficients(self.ledger.rows[k])['jobs']*self.ledger.rows[k]['levels']
                   for k in self.ledger.by_country[tag] if k in self.ledger.rows and k[2] in self.manufacturing)

    def room(self, state, tag, kind, pms):
        if kind not in self.manufacturing: return math.inf
        ceiling = self.profiles[tag]['manufacturing_job_ceiling']
        jobs = self.ledger.target.coefficients(kind, pms, self.ledger.techs[tag])['jobs']
        return math.floor(max(0, ceiling-self.jobs(tag))/jobs) if jobs else 0


def replace_methods(ledger, row, methods):
    # Preserve public/private/foreign ownership byte-for-byte when only PMs change.
    before = list(row['pms'])
    if methods == before: return
    body, count = re.subn(r'\bactivate_production_methods\s*=\s*\{[^{}]*\}',
                         'activate_production_methods = { '+' '.join(methods)+' }', row['body'])
    if count != 1: raise ValueError('Ambiguous PM block')
    row['body'], row['pms'] = body, methods
    ledger.changes.append({'state': row['state'], 'country': row['owner'], 'building': row['building'],
                           'reason': 'political_law_pm_compatibility', 'before_pms': before, 'after_pms': methods,
                           'before': row['levels'], 'after': row['levels']})


def build(args):
    installed = read(ROOT/'.local/economy/installation-latest.json')
    prior = Path(installed['package']); previous = read(prior/'package_report.json')
    base = Path(previous['mod_directory']); output = args.output.resolve()
    if output.exists(): raise ValueError('Refusing to overwrite a political deployment')
    inputs = [args.review/'report.json', args.review/'verification.json', args.source, args.mapping,
              args.demographic/'demographics/resident_population_groups.csv',
              args.demographic/'template_fallback/template_population_groups.csv',
              args.capacity/'development.json', args.capacity/'bureaucracy.json',
              ROOT/'config/personal/economy.json', ROOT/'config/personal/economy_capacity.json', prior/'package_report.json']
    review = read(args.review/'report.json'); mapping = read(args.mapping); source = read(args.source)
    if review['rule_version'] != 'politics-0.2' or read(args.review/'verification.json')['status'] != 'passed': raise ValueError('Unverified political rulebook')
    if len({r['source_sha256'] for r in (review, mapping, source)}) != 1: raise ValueError('Source mismatch')
    for name, sha in review['input_sha256'].items():
        if digest(Path(name)) != sha: raise ValueError('Political input changed: '+name)
    for name, sha in review['native_reference_files_sha256'].items():
        if digest(Path(name)) != sha: raise ValueError('Native reference changed: '+name)
    for rel, sha in previous['output_sha256'].items():
        if digest(base/rel) != sha: raise ValueError('Base package changed: '+rel)
    mod = output/'eu5_economy_test'; shutil.copytree(base, mod)
    target = Target(args.game); lawdefs = definitions(args.game/'common/laws')
    lawdefs.update(definitions(mod/'common/laws'))
    target.states.update(definitions(mod/'map_data/state_regions'))
    economy_rules = read(ROOT/'config/personal/economy.json')['technology_rules']
    config = read(ROOT/'config/personal/economy_capacity.json')
    old_history = countries((base/HISTORY).read_text(encoding='utf-8-sig'))
    old_rows = building_rows(base/BUILDINGS); rows_by_tag = defaultdict(list)
    for r in old_rows: rows_by_tag[r['owner']].append(r)
    effects = {k: v for k, v in root((args.game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v, Object)}
    extra = defaultdict(set)
    for p in (mod/'common/history/countries').glob('*.txt'):
        if p.name == Path(HISTORY).name: continue
        for tag, obj in countries(p.read_text(encoding='utf-8-sig')).items():
            extra[tag].update(v for k, v in obj.entries() if k == 'add_technology_researched')
    bodies, techs, laws, audits = {}, {}, {}, {}
    for tag, obj in old_history.items():
        old_tech = expand_template_tech(obj, effects, target)
        old_laws = active_laws(obj, target, mapping['countries'][tag])
        c = review['countries'][tag]
        if c['status'] != 'evaluated':
            bodies[tag], techs[tag], laws[tag] = obj.text(), old_tech, old_laws
            continue
        chosen, overrides = deployment_laws(c, lawdefs); laws[tag] = set(chosen.values())
        techs[tag], technology = technology_roots(old_tech, c, source['countries'][str(c['source_id'])], laws[tag], lawdefs, target, economy_rules, rows_by_tag[tag], extra[tag])
        levels, caps = institution_plan(c, laws[tag], techs[tag], lawdefs, target)
        if c['metrics']['slave_population'] > 0 and 'law_slavery_banned' in laws[tag]:
            raise ValueError('Abolition requires a population-preserving emancipation pass: '+tag)
        bodies[tag] = history_body(obj.text(), chosen, techs[tag], levels)
        old_groups = {lawdefs[l]['group']: l for l in old_laws}
        audits[tag] = {'name': c['name'], 'source_id': c['source_id'], 'country_type': c['target_country_type'],
                       'laws': {g: {**c['laws'][g], 'law': law, 'before': old_groups.get(g)} for g, law in chosen.items()},
                       'deployment_overrides': overrides, 'technology': technology,
                       'institutions': levels, 'institution_caps': caps,
                       'prior_institutions': institution_levels(obj, old_laws, lawdefs)}
    # Later history files must not silently replace the reviewed choices. The
    # religious-bloc prerequisite guard is allowed only when it is a no-op.
    auxiliary_guards = []
    for p in (mod/'common/history/countries').glob('*.txt'):
        if p.name == Path(HISTORY).name: continue
        for tag,obj in countries(p.read_text(encoding='utf-8-sig')).items():
            if 'activate_law' not in obj.text() and 'set_institution_investment_level' not in obj.text(): continue
            for key,value in obj.entries():
                if key == 'add_technology_researched': continue
                f = fields(value) if isinstance(value,Object) else {}
                limit = fields(f.get('limit')); condition = fields(limit.get('NOR'))
                terms = sequence(condition.get('has_law_or_variant'))
                # fields() intentionally collapses duplicates, so read NOR entries.
                nor = limit.get('NOR')
                if key != 'if' or set(limit) != {'NOR'} or not isinstance(nor,Object): raise ValueError('Unreviewed later political history: '+str(p))
                entries = list(nor.entries())
                if not entries or any(k!='has_law_or_variant' for k,v in entries) or not any(v.split(':')[-1] in laws[tag] for k,v in entries):
                    raise ValueError('Later political history would override selected laws: '+tag)
                auxiliary_guards.append({'country':tag,'file':p.name,'result':'guard_false_no_law_override'})
    tags = set(audits)
    target.global_technologies = set().union(*techs.values())
    write_history = lambda: (mod/HISTORY).write_text(block('COUNTRIES', ''.join(block('c:'+t, b).replace(' = {', ' ?= {', 1) for t, b in bodies.items())), encoding='utf-8-sig')
    write_history()
    history = countries((mod/HISTORY).read_text(encoding='utf-8-sig'))
    population = Counter()
    for rel, column in [('demographics/resident_population_groups.csv', 'preview_integer_persons'), ('template_fallback/template_population_groups.csv', 'persons')]:
        with (args.demographic/rel).open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f): population[row['state'], row['owner']] += int(row[column])
    owners_path = args.mapping.parent/'province_owners.json'; inputs.append(owners_path)
    preferred = defaultdict(set)
    for r in old_rows: preferred[r['building']].update(r['pms'])
    ledger = Ledger(target, old_rows, population, techs, laws, read(owners_path), preferred, config['employment'])
    for row in ledger.rows.values():
        tag = row['owner']
        if tag not in tags or row.get('guards'): continue
        if any(not target.available(pm, techs[tag], laws[tag]) for pm in row['pms']):
            defaults = ledger.pms(row['building'], tag)
            methods = target.complete_methods(row['building'], [p for p in row['pms'] if target.available(p, techs[tag], laws[tag])], defaults)
            replace_methods(ledger, row, methods)
    ledger.development = ExistingDevelopmentEnvelope(ledger, read(args.capacity/'development.json'))
    managed = {t for t in tags if audits[t]['country_type'] != 'decentralized'}
    budget = AdministrationBudget(ledger, managed, history, mod/'common/history/states/00_eu5_world.txt', config['bureaucracy'])
    before_budget = budget.audit()
    # Preserve existing administrative PMs whenever valid; upgrading unrelated
    # methods here would create new demand unrelated to politics.
    for tag in managed:
        rows = [r for r in rows_by_tag[tag] if r['building'] == 'building_government_administration']
        if rows and all(r['pms'] == rows[0]['pms'] for r in rows) and all(target.available(p, techs[tag], laws[tag]) for p in rows[0]['pms']):
            ledger.pm_cache['building_government_administration', tag, frozenset(techs[tag]), frozenset(laws[tag])] = rows[0]['pms']
    print('Applying laws and planning institutions for '+str(len(tags))+' source countries', flush=True)
    admin_changes = budget.provision([], preserve_existing_methods=True)
    # Only support additional administrative paper demand. Source industrial
    # ceilings remain in force; existing national import needs are not erased.
    old_paper = {r['country']: r['paper_net_industrial_supply'] for r in before_budget['countries']}
    for tag in sorted(managed):
        needed = max(0, min(0, old_paper[tag])-ledger.balance(tag)['paper'])
        if needed: support_good(ledger, tag, 'paper', needed, ['building_paper_mill'], 'political_administration_paper')
    admin_changes.extend(budget.provision([], preserve_existing_methods=True))
    after_budget = budget.audit(); dump(output/'bureaucracy.json', after_budget)
    dump(output/'bureaucracy_before.json', before_budget); dump(output/'administration_changes.json', admin_changes)
    dump(output/'building_changes.json', ledger.changes)
    if after_budget['countries_below_core_demand']: raise ValueError('Core bureaucracy gaps: '+str(after_budget['countries_below_core_demand']))
    (mod/BUILDINGS).write_text(render_buildings(list(ledger.rows.values())), encoding='utf-8-sig')
    actual = building_rows(mod/BUILDINGS)
    expected = {(r['state'], r['owner'], r['building']): r for r in ledger.rows.values()}
    for row in actual:
        key = row['state'], row['owner'], target.aliases.get(row['building'], row['building'])
        if (row['levels'], row['pms']) != (expected[key]['levels'], expected[key]['pms']): raise ValueError('Building readback mismatch')
        if row['owner'] in tags and not row.get('guards'):
            if not all(target.available(p, techs[row['owner']], laws[row['owner']]) for p in row['pms']): raise ValueError('Locked production method: '+str(key))
    for tag, audit in audits.items():
        obj = history[tag]; chosen = {g: v['law'] for g, v in audit['laws'].items()}
        if active_laws(obj, target, mapping['countries'][tag]) != set(chosen.values()): raise ValueError('Law readback mismatch')
        if len([k for k, v in obj.entries() if k == 'activate_law']) != len(chosen): raise ValueError('Duplicate law initialization')
        if institution_levels(obj, laws[tag], lawdefs) != audit['institutions']: raise ValueError('Institution readback mismatch')
        if closure(techs[tag], target.techs) != techs[tag]: raise ValueError('Broken technology chain')
        if strip_politics(obj.text()).split() != strip_politics(old_history[tag].text()).split(): raise ValueError('Unrelated country history change')
        validate_laws(chosen, lawdefs)
        for law in laws[tag]:
            if not set(sequence(lawdefs[law].get('unlocking_technologies'))) <= techs[tag]: raise ValueError('Law prerequisite missing')
    # Do not trade away the source army to make a new military law's limit fit.
    army_limits = []
    for row in old_rows:
        if row['building'] != 'building_barrack': continue
        key = row['state'], row['owner'], row['building']
        if ledger.rows[key]['levels'] != row['levels']: raise ValueError('Source army resized')
        if row['owner'] not in tags: continue
        cap = float(target.base_modifiers.get('state_building_barrack_max_level_add', 0)) + sum(float(fields(f.get('modifier')).get('state_building_barrack_max_level_add', 0)) for f in [*(lawdefs[l] for l in laws[row['owner']]), *(target.techs[t] for t in techs[row['owner']])])
        if cap and row['levels'] > cap: army_limits.append({'state': row['state'], 'country': row['owner'], 'levels': row['levels'], 'law_cap': cap})
    work_gaps = [{'state': s, 'country': t, 'jobs': ledger.jobs(s,t), 'population': n}
                 for (s,t), n in population.items() if ledger.jobs(s,t) > n*config['employment']['maximum_formal_workforce_share']+.001]
    old_techs = {t: expand_template_tech(obj, effects, target) for t,obj in old_history.items()}
    old_ledger = Ledger(target, old_rows, population, old_techs, laws, read(owners_path), preferred, config['employment'])
    for warning in work_gaps:
        warning['prior_jobs'] = old_ledger.jobs(warning['state'], warning['country'])
        if warning['jobs'] > warning['prior_jobs']+.001: raise ValueError('New workforce overload: '+str(warning))
    old_lookup = {(r['state'], r['owner'], target.aliases.get(r['building'], r['building'])): r for r in old_rows}
    for k, row in ledger.rows.items():
        prior_row = old_lookup.get(k)
        if not prior_row or row['levels'] != prior_row['levels']:
            if k[2] not in ('building_government_administration', 'building_paper_mill'): raise ValueError('Unrelated economic resizing')
    for tag in tags:
        excess = ledger.development.jobs(tag)-ledger.development.profiles[tag]['manufacturing_job_ceiling']
        if excess > .001: raise ValueError('Industrial envelope exceeded: '+tag)
    metadata = read(mod/'.metadata/metadata.json'); metadata['version'] = args.version; dump(mod/'.metadata/metadata.json', metadata)
    current = {p.relative_to(mod).as_posix(): digest(p) for p in mod.rglob('*') if p.is_file()}
    changed = [rel for rel, sha in current.items() if previous['output_sha256'].get(rel) != sha]
    if set(current) != set(previous['output_sha256']) or not set(changed) <= ALLOWED: raise ValueError('Unrelated package changes')
    for tag in set(history)-tags:
        if history[tag].text().split() != old_history[tag].text().split(): raise ValueError('Fallback changed')
    summary = {'source_countries': len(tags), 'vanilla_fallback_unchanged': len(history)-len(tags),
               'old_political_templates_remaining': sum('effect_starting_politics_' in history[t].text() for t in tags),
               'democracy_before': sum('democracy' in expand_template_tech(old_history[t], effects, target) for t in tags),
               'democracy_after': sum('democracy' in techs[t] for t in tags),
               'law_changes': sum(r['law'] != r['before'] for a in audits.values() for r in a['laws'].values()),
               'open_border_countries': sorted(t for t in tags if 'law_no_migration_controls' in laws[t]),
               'institution_countries': sum(bool(a['institutions']) for a in audits.values()),
               'administration_levels_added': sum(max(0, r['levels']-old_lookup.get(k,{}).get('levels',0)) for k,r in ledger.rows.items() if k[2]=='building_government_administration'),
               'core_bureaucracy_gaps': len(after_budget['countries_below_core_demand'])}
    for tag in summary['open_border_countries']:
        if not review['countries'][tag]['historical_context']['migration']['eligible']:
            raise ValueError('Open migration outside independent American immigrant states: '+tag)
    if summary['open_border_countries'] != sorted(t for t,c in review['countries'].items() if c.get('laws',{}).get('lawgroup_migration',{}).get('law')=='law_no_migration_controls'):
        raise ValueError('Reviewed migration rule not applied')
    audit = {'rule_version': review['rule_version'], 'status': 'static_verified_runtime_pending', 'summary': summary,
             'countries': audits, 'auxiliary_political_history_guards':auxiliary_guards,
             'military_law_capacity_warnings': army_limits, 'workforce_warnings': work_gaps,
             'limitations': ['Bureaucracy is a staffing estimate, not a runtime tax guarantee.',
                            'Source-backed regular armies are preserved even above a new law construction limit.',
                            'Society technology is evidence-based plus minimum law/building/PM/diplomacy prerequisites.',
                            'Hiring, wages, trade and institutional rollout require a new campaign test.']}
    dump(output/'politics-deployment.json', audit)
    cells = []
    for tag,a in sorted(audits.items()):
        detail = json.dumps(a, ensure_ascii=False, indent=2)
        changes = '<br>'.join(html.escape(g+': '+str(l['before'])+' → '+l['law']) for g,l in a['laws'].items() if l['law']!=l['before'])
        cells.append('<tr><td>'+html.escape(tag+' '+a['name'])+'</td><td>'+changes+'</td><td>'+html.escape(str(a['institutions']))+'</td><td><details><summary>来源与科技前置</summary><pre>'+html.escape(detail)+'</pre></details></td></tr>')
    warnings = '<h2>待游戏内验证</h2><p>保留原存档常备军：'+str(len(army_limits))+' 个州的既有兵营高于新军制建设上限，未削减部队。'+str(len(work_gaps))+' 个地区存在此前已有的劳动力容量警告，本次没有扩大。</p><p>行政储备不足但基本需求已覆盖：'+html.escape(', '.join(after_budget['countries_with_planning_gap']) or '无')+'。纸张缺口保留为贸易需求，不突破原有工业发展上限强建工厂。</p>'
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>politics-0.2 实装核对</title><style>body{font:16px system-ui;margin:28px;background:#f5f4ef}td,th{border:1px solid #bbb;padding:9px;vertical-align:top}table{border-collapse:collapse}pre{white-space:pre-wrap;max-width:700px}</style><h1>politics-0.2 实装核对</h1><p>静态校验通过，需新开战役。行政力为75%就业估算；不保证实际财政或就业。</p><pre>'+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>'+warnings+'<table><tr><th>国家</th><th>法律变化</th><th>机构等级</th><th>完整依据</th></tr>'+''.join(cells)+'</table>', encoding='utf-8')
    inputs.extend(Path(p) for p in review['input_sha256'])
    inputs.extend(Path(__file__).parent/p for p in ['deploy_political_rules.py','economy_bureaucracy.py','economy_model.py','economy_capacity.py','complete_economy.py'])
    for directory in ['common/technology/technologies','common/laws','common/buildings','common/production_methods','common/production_method_groups','common/static_modifiers']:
        inputs.extend(sorted((args.game/directory).glob('*.txt')))
    inputs.append(args.game/'common/defines/00_defines.txt')
    report = {'status': 'm5_politics_static_verified_runtime_pending', 'update_scope': 'm5_politics',
              'version': args.version, 'mod_name': metadata['name'], 'mod_directory': str(mod), 'prior_package': str(prior),
              'political_run': str(args.mapping.parent.resolve()), 'demographic_run': str(args.demographic.resolve()),
              'rule_version': review['rule_version'], 'new_campaign_required': True, 'changed_files': changed,
              'input_sha256': {str(p.resolve()): digest(p) for p in inputs}, 'output_sha256': current}
    dump(output/'package_report.json', report)
    verification = {'status': 'passed_static_runtime_pending', 'literacy': read(prior/'verification.json')['literacy'],
                    'politics': {'status': 'passed', **summary, 'law_conflicts': 0, 'law_technology_gaps': 0, 'institution_cap_violations': 0},
                    'administration': {'status': 'passed', 'core_demand_gaps': 0, 'runtime_verified': False},
                    'source_armies_population_cultures_flags_diplomacy_unchanged': True,
                    'changed_files': changed, 'package_report_sha256': digest(output/'package_report.json'),
                    'audit_sha256': {name: digest(output/name) for name in ('politics-deployment.json','bureaucracy.json','building_changes.json','review.html')}}
    dump(output/'verification.json', verification)
    print(json.dumps({'package': str(output), **summary}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key, default in [('review','.local/politics/review-20261001-v02-release'), ('source','.local/economy/source-1780-v2.json'),
                         ('mapping','.local/m3/runs/20261001-073149-d689a0e7/conversion_report.json'),
                         ('demographic','.local/m4/runs/20261001-073624-1b45ed6d'), ('capacity','.local/economy/capacity-019')]:
        parser.add_argument('--'+key, type=Path, default=ROOT/default)
    parser.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', default='0.5.6-m5-test7')
    build(parser.parse_args())
