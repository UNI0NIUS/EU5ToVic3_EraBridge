"""Merge geographic agriculture and provincial ownership onto the latest M5 package."""
from collections import Counter, defaultdict
from datetime import datetime
import json
import re
from pathlib import Path
import shutil

from build_economy import expand_template_tech
from complete_economy import active_laws, csv_rows, verify as verify_economy
from deploy_political_rules import replace_methods
from economy_agriculture import AgriculturePlanner
from economy_bureaucracy import AdministrationBudget
from economy_capacity import Ledger, write_land, carry_land
from economy_model import Target, building_rows, definitions, render_buildings
from economy_ownership import OwnershipPlanner, province_evidence, vanilla_reference, sector, split_existing
from extract_m3_politics import fields
from m3_world import digest
from pdx_text import Object, root

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')
BUILDINGS = 'common/history/buildings/00_eu5_world.txt'
FORMATIONS = 'common/history/military_formations/00_eu5_world.txt'
CANDIDATE = ROOT/'.local/economy/geography-007-ownership-reference'


def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p, value): Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
def files(p): return {f.relative_to(p).as_posix(): digest(f) for f in p.rglob('*') if f.is_file()}
def canonical(obj): return [(k, canonical(v) if isinstance(v, Object) else v) for k, v in obj.entries()]
def key(r): return r['state'], r['owner'], r['building']
def signature(r): return canonical(root(r['body'])), [canonical(root(g)) for g in r.get('guards', ())]


def build():
    installation = read(ROOT/'.local/economy/installation-latest.json')
    prior = Path(installation['package']); previous = read(prior/'package_report.json')
    base = Path(previous['mod_directory'])
    assert files(base) == previous['output_sha256'], 'Prior package changed'
    assert files(Path(installation['target'])) == previous['output_sha256'], 'Installed baseline changed'
    manifest = read(CANDIDATE/'manifest.json')
    superseded_tools = []
    for group, items in manifest.items():
        for name, sha in items.items():
            path = CANDIDATE/name if group == 'outputs' else Path(name)
            if group == 'tools' and path.name in ('economy_fleets.py','complete_economy.py') and digest(path) != sha:
                # Naval code has since gained source-fleet support. This merge
                # inherits the installed navy and does not rerun naval allocation.
                superseded_tools.append(str(path))
                continue
            assert digest(path) == sha, 'Candidate changed: '+str(path)
    mapping_path = Path(previous['political_run'])/'conversion_report.json'
    mapping = read(mapping_path)
    tags = {t for t,c in mapping['countries'].items() if c['source_id'] is not None}
    demographic = Path(previous['demographic_run'])
    config_path = ROOT/'config/personal/economy_capacity.json'; config = read(config_path)
    population = Counter()
    for rel, column in [('demographics/resident_population_groups.csv','preview_integer_persons'), ('template_fallback/template_population_groups.csv','persons')]:
        for r in csv_rows(demographic/rel): population[r['state'],r['owner']] += int(r[column])
    # Refined culture splits must not change the source population used by either module.
    old_population = Counter()
    old_demo = ROOT/'.local/m4/runs/20261001-073624-1b45ed6d'
    for rel, column in [('demographics/resident_population_groups.csv','preview_integer_persons'), ('template_fallback/template_population_groups.csv','persons')]:
        for r in csv_rows(old_demo/rel): old_population[r['state'],r['owner']] += int(r[column])
    def source_classes(demo):
        result = Counter()
        for r in csv_rows(demo/'staging/province_population_draft.csv'):
            result[r['target_state'],r['target_owner'],r['target_province'],r['source_class']] += int(r['centipersons'])
        return result
    assert source_classes(demographic) == source_classes(old_demo), 'Source population/class mapping changed'
    assert sum(population.values()) == sum(old_population.values()), 'Population total changed'
    rounding_changes = [{'state':s,'country':t,'before':old_population[s,t],'after':n} for (s,t),n in population.items() if n!=old_population[s,t]]
    target = Target(GAME)  # Geographic capacities deliberately come from vanilla.
    history = {k[2:]:v for k,v in fields(root((base/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects = {k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    techs = {t:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws = {t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()}
    for p in (base/'common/history/countries').glob('*.txt'):
        if p.name == '00_eu5_world.txt': continue
        for k,o in fields(root(p.read_text(encoding='utf-8-sig')))['COUNTRIES'].entries():
            techs[k[2:]].update(v for op,v in o.entries() if op=='add_technology_researched')
    target.global_technologies = set().union(*techs.values())
    old_rows = building_rows(base/BUILDINGS)
    new_rows = building_rows(CANDIDATE/'overlay'/BUILDINGS)
    # Keep latest administration, military, ports, universities, construction,
    # monuments and fallback history. Economic productive sectors and railways
    # use the reviewed finite-geography candidate.
    def economic(r):
        return r['owner'] in tags and not r.get('guards') and (sector(target,r['building']) is not None or r['building']=='building_railway')
    merged = [dict(r) for r in old_rows if not economic(r)] + [dict(r) for r in new_rows if economic(r)]
    assert len({key(r) for r in merged}) == len(merged)
    preferred = defaultdict(set)
    for r in old_rows: preferred[r['building']].update(r['pms'])
    ledger = Ledger(target, merged, population, techs, laws, read(mapping_path.parent/'province_owners.json'), preferred, config['employment'])
    for r in ledger.rows.values():
        if r['owner'] not in tags or r.get('guards'): continue
        if any(not target.available(pm,techs[r['owner']],laws[r['owner']]) for pm in r['pms']):
            defaults = ledger.pms(r['building'],r['owner'])
            methods = target.complete_methods(r['building'],[pm for pm in r['pms'] if target.available(pm,techs[r['owner']],laws[r['owner']])],defaults)
            replace_methods(ledger,r,methods)
    agriculture = read(CANDIDATE/'agriculture.json')
    ledger.agriculture = AgriculturePlanner.__new__(AgriculturePlanner)
    ledger.agriculture.ledger, ledger.agriculture.policy = ledger, agriculture['policy']
    ledger.agriculture.profiles = {(p['state'],p['country']):p for p in agriculture['states']}
    for p in agriculture['states']:
        ledger.source_paid_agriculture[p['state'],p['country']] = p['source_paid_agriculture_person_equivalents']
    for r in csv_rows(demographic/'staging/province_population_draft.csv'):
        ledger.source_classes[r['target_state'],r['target_owner'],r['source_class']] += int(r['centipersons'])/100
    ag_audit = ledger.agriculture.audit()
    assert not any(p['commercial_job_excess'] or p['commercial_land_excess'] for p in ag_audit['states']), 'New laws exceed reviewed agriculture envelope'
    print('Latest public services and military preserved; economic PMs checked against current laws', flush=True)
    source_path = ROOT/'.local/economy/source-1780-v2.json'
    provinces = province_evidence(csv_rows(demographic/'staging/province_population_draft.csv'),read(source_path))
    ledger.ownership = OwnershipPlanner(ledger,provinces,tags,config['ownership'],vanilla_reference(target,config['ownership']))
    before_ownership = {key(r):(r['levels'],r['pms'][:],[(k,canonical(root(v))) for k,v in split_existing(r)[1]]) for r in ledger.rows.values()}
    ledger.ownership.apply()
    for r in ledger.rows.values():
        assert before_ownership[key(r)] == (r['levels'],r['pms'],[(k,canonical(root(v))) for k,v in split_existing(r)[1]]), 'Ownership changed productive or protected holdings'
    out = ROOT/'.local/economy/packages'/('m5-economic-modules-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod = out/'eu5_economy_test'; shutil.copytree(base,mod)
    (mod/BUILDINGS).write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    land = {s:int(f['arable_land']) for s,f in target.states.items() if 'arable_land' in f}
    land_files = write_land(target,base,mod,land,{s:True for s,f in target.states.items() if 'arable_land' in f or 'capped_resources' in f})
    actual = building_rows(mod/BUILDINGS)
    assert {key(r):signature(r) for r in actual if not economic(r)} == {key(r):signature(r) for r in old_rows if not economic(r)}, 'Protected buildings changed'
    # Reuse the comprehensive economic validator against the merged package,
    # including army/barracks equality and fleet support, without installing it.
    validation = out/'validation'; shutil.copytree(mod/'map_data',validation/'overlay/map_data')
    for rel in (BUILDINGS,FORMATIONS):
        p = validation/'overlay'/rel; p.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(mod/rel,p)
    navy_package = prior
    while not (navy_package/'fleet_mapping.json').exists():
        navy_package = Path(read(navy_package/'package_report.json')['prior_package'])
    from economy_market import land_edges
    _,ledger.coastal_provinces = land_edges(GAME,ROOT/'.local/economy/land_edges.json',ledger.owners)
    _, employment = carry_land(ledger,ledger.source_classes,tags)
    checks = verify_economy(ledger,validation,read(CANDIDATE/'army_mapping.json'),land,employment,read(navy_package/'fleet_mapping.json'))
    for r in actual:
        if r['owner'] in tags and not r.get('guards'):
            assert all(target.available(pm,techs[r['owner']],laws[r['owner']]) for pm in r['pms']), 'Law-incompatible PM'
    managed = {t for t in tags if mapping['countries'][t]['country_type'] != 'decentralized'}
    admin = AdministrationBudget(ledger,managed,history,mod/'common/history/states/00_eu5_world.txt',config['bureaucracy']).audit()
    assert not admin['countries_below_core_demand'], 'Core bureaucracy gap'
    old_ledger = Ledger(target,old_rows,population,techs,laws,ledger.owners,preferred,config['employment'])
    ownership = ledger.ownership.audit()
    installed_ownership = defaultdict(Counter)
    for r in old_rows:
        if economic(r): installed_ownership[r['owner']].update(split_existing(r)[2])
    for t,c in ownership['countries'].items(): c['installed_private_levels_before'] = dict(installed_ownership[t])
    new_overloads = []
    for (s,t),n in population.items():
        owners = ledger.ownership_jobs[s,t]
        planned = (ledger.jobs(s,t)-owners)*config['employment']['formal_staffing_safety_fraction']+owners
        old_planned = old_ledger.jobs(s,t)*config['employment']['formal_staffing_safety_fraction']
        if planned > max(n*config['employment']['workforce_share'],old_planned)+.001:
            new_overloads.append({'state':s,'country':t,'planned_jobs':planned,'prior_planned_jobs':old_planned,'workforce':n*config['employment']['workforce_share']})
    assert not new_overloads, 'New workforce overloads: '+str(new_overloads[:5])
    infrastructure = []
    for (s,t),n in population.items():
        if t not in tags: continue
        rs=ledger.local(s,t)
        usage=sum(target.infrastructure_usage(r['building'])*r['levels'] for r in rs)
        usage+=sum(target.infrastructure_usage({'manor':'building_manor_house','finance':'building_financial_district'}[k])*v for k,v in ledger.ownership.hosts[s,t].items())
        capacity=target.infrastructure(s,n,techs[t],rs)
        if usage>capacity+.001: infrastructure.append({'state':s,'country':t,'usage':usage,'capacity':capacity,'deficit':usage-capacity})
    meta=read(mod/'.metadata/metadata.json')
    version=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',previous['version'])
    assert version, 'Unrecognized installed version'
    major,minor,patch,test=map(int,version.groups())
    meta['version']=f'{major}.{minor}.{patch+1}-m5-test{test+1}'
    write(mod/'.metadata/metadata.json',meta)
    output=files(mod); changed=sorted(p for p,sha in output.items() if previous['output_sha256'].get(p)!=sha)
    assert not set(previous['output_sha256'])-set(output), 'Unexpected file removal'
    assert set(output)-set(previous['output_sha256'])<=set(land_files), 'Unexpected file addition'
    assert set(changed)<={BUILDINGS,'.metadata/metadata.json',*land_files}, 'Unrelated change'
    evidence={'status':'passed','geographic_caps_match_vanilla':True,'province_ownership_verified':True,'protected_buildings_unchanged':True,
        'other_files_byte_identical':True,'current_laws_and_technology_verified':True,'core_bureaucracy_gaps':0,'new_workforce_overloads':0,
        'mapped_province_parts':len(provinces),'ownership_rows':checks['province_based_ownership_rows_verified'],
        'commercial_agricultural_levels_before':sum(r['levels'] for r in old_rows if r['building'] in ledger.arable_kinds),
        'commercial_agricultural_levels_after':sum(r['levels'] for r in actual if r['building'] in ledger.arable_kinds),
        'infrastructure_gap_parts':len(infrastructure),'runtime_verified':False,
        'not_verified':['actual_hiring','owner_initialization_and_dividends','food_prices_and_living_standards','treasury_balance','actual_market_access']}
    for name,value in [('economic_modules_verification.json',evidence),('ownership.json',ownership),('ownership_provinces.json',list(provinces.values())),('agriculture.json',ag_audit),('bureaucracy.json',admin),('infrastructure_gaps.json',infrastructure),('pm_compatibility_changes.json',ledger.changes),('inherited_population_rounding.json',rounding_changes),('employment.json',employment)]:write(out/name,value)
    inputs=[Path(__file__),ROOT/'tools/update_m5_integrated_test.ps1',prior/'package_report.json',CANDIDATE/'manifest.json',config_path,source_path,mapping_path,demographic/'staging/province_population_draft.csv',navy_package/'fleet_mapping.json',*[Path(p) for p in manifest['tools']]]
    report={'status':'economic_modules_static_verified_runtime_pending','update_scope':'m5_economic_modules','version':meta['version'],'mod_name':meta['name'],
        'mod_directory':str(mod),'prior_package':str(prior),'economic_candidate':str(CANDIDATE),'political_run':previous['political_run'],'demographic_run':previous['demographic_run'],
        'new_campaign_required':True,'changed_files':changed,'superseded_candidate_tools':superseded_tools,'input_sha256':{str(p):digest(p) for p in inputs},'output_sha256':output}
    write(out/'package_report.json',report)
    write(out/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],'economic_modules':evidence,
        'economy_static_checks':checks,'package_report_sha256':digest(out/'package_report.json'),
        'audit_sha256':{p.name:digest(p) for p in out.glob('*.json') if p.name!='package_report.json'}})
    print(json.dumps({'package':str(out),'verification':evidence,'changed_files':changed,'ITA':ownership['countries']['ITA'],'BOH':ownership['countries']['BOH']},ensure_ascii=False))


if __name__=='__main__': build()
