"""Apply naval allocation to the latest integrated package without reverting politics."""
from collections import Counter, defaultdict
from datetime import datetime
import argparse
import json
from pathlib import Path
import re
import shutil

from build_economy import expand_template_tech
from complete_economy import active_laws, csv_rows
from economy_capacity import Ledger
from economy_fleets import BUILDING, convert, verify, read_ships
from economy_naval_source import prepare as prepare_source
from economy_market import land_edges
from economy_model import Target, building_rows, definitions, render_buildings
from extract_m3_politics import fields
from m3_world import digest
from pdx_text import Object, root

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')
BUILDINGS = 'common/history/buildings/00_eu5_world.txt'
FORMATIONS = 'common/history/military_formations/00_eu5_world.txt'


def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def canonical(obj): return [(k,canonical(v) if isinstance(v,Object) else v) for k,v in obj.entries()]


def build(naval_path=None, source_path=None):
    if bool(naval_path) != bool(source_path): raise ValueError('Provide both naval and economic source ledgers')
    installed = read(ROOT/'.local/economy/installation-latest.json')
    prior = Path(installed['package']); previous = read(prior/'package_report.json')
    base = Path(previous['mod_directory'])
    for rel,sha in previous['output_sha256'].items():
        if digest(base/rel) != sha: raise ValueError('Base package changed: '+rel)
    mapping_path = Path(previous['political_run'])/'conversion_report.json'
    mapping = read(mapping_path); demographic = Path(previous['demographic_run'])
    config_path = ROOT/'config/personal/economy_capacity.json'; config = read(config_path)
    population,classes = Counter(),Counter()
    for rel,column in [('demographics/resident_population_groups.csv','preview_integer_persons'),('template_fallback/template_population_groups.csv','persons')]:
        for row in csv_rows(demographic/rel): population[row['state'],row['owner']] += int(row[column])
    links = defaultdict(Counter)
    for row in csv_rows(demographic/'staging/province_population_draft.csv'):
        classes[row['target_state'],row['target_owner'],row['source_class']] += int(row['centipersons'])/100
        links[row['source_location']][row['target_state'],row['target_owner']] += int(row['centipersons'])
    links = {k:{pair:n/sum(v.values()) for pair,n in v.items()} for k,v in links.items() if sum(v.values())}
    target = Target(GAME); target.states.update(definitions(base/'map_data/state_regions'))
    history = {k[2:]:v for k,v in fields(root((base/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
    effects = {
        k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    techs = {t:expand_template_tech(o,effects,target) for t,o in history.items()}
    laws = {t:active_laws(o,target,mapping['countries'][t]) for t,o in history.items()}
    for path in (base/'common/history/countries').glob('*.txt'):
        if path.name == '00_eu5_world.txt': continue
        for key,obj in fields(root(path.read_text(encoding='utf-8-sig')))['COUNTRIES'].entries():
            techs[key[2:]].update(v for k,v in obj.entries() if k=='add_technology_researched')
    target.global_technologies = set().union(*techs.values())
    old_rows = building_rows(base/BUILDINGS)
    preferred = defaultdict(set)
    for row in old_rows: preferred[row['building']].update(row['pms'])
    owners_path = mapping_path.parent/'province_owners.json'
    ledger = Ledger(target,old_rows,population,techs,laws,read(owners_path),preferred,config['employment'])
    _,ledger.coastal_provinces = land_edges(GAME,ROOT/'.local/economy/land_edges.json',ledger.owners)
    managed = {t for t,c in mapping['countries'].items() if c['source_id'] is not None}
    old_text = (base/FORMATIONS).read_text(encoding='utf-8-sig')
    source_ships,source_report = None,None
    if naval_path:
        naval = read(naval_path)
        for path,sha in naval['unit_definition_sha256'].items():
            if digest(Path(path)) != sha: raise ValueError('Source naval definition changed: '+path)
        source_ships,source_report = prepare_source(ledger,read(source_path),naval,mapping,links)
    text,report = convert(ledger,old_text,managed,classes,config['military'],source_ships)
    verify(ledger,text,report)
    out = ROOT/'.local/economy/packages'/('m5-navy-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod = out/'eu5_economy_test'; shutil.copytree(base,mod)
    country_file = 'common/history/countries/00_eu5_world.txt'
    if source_report:
        from build_m2_prototype import patch
        before_text = (base/country_file).read_text(encoding='utf-8-sig')
        edits = [(history[t].end,history[t].end,''.join('\nadd_technology_researched = '+v+'\n' for v in added))
                 for t,added in source_report['technology_added'].items() if added]
        (mod/country_file).write_text(patch(before_text,edits),encoding='utf-8-sig')
        after_history = {k[2:]:v for k,v in fields(root((mod/country_file).read_text(encoding='utf-8-sig')))['COUNTRIES'].entries()}
        for tag,obj in history.items():
            expected = canonical(obj)+[('add_technology_researched',v) for v in source_report['technology_added'].get(tag,[])]
            if canonical(after_history[tag]) != expected: raise ValueError('Country history changed beyond naval prerequisites')
    (mod/BUILDINGS).write_text(render_buildings(list(ledger.rows.values())),encoding='utf-8-sig')
    (mod/FORMATIONS).write_text(text,encoding='utf-8-sig')
    actual = building_rows(mod/BUILDINGS)
    signature = lambda rows: {(r['state'],r['owner'],r['building']):(canonical(root(r['body'])),[canonical(root(g)) for g in r.get('guards',())]) for r in rows if r['owner'] not in managed or r['building']!=BUILDING}
    if signature(actual) != signature(old_rows): raise ValueError('Non-naval building changed')
    before,_ = read_ships(old_text,managed); after,_ = read_ships(text,managed)
    if {t:[canonical(root(v)) for v in vs] for t,vs in before.items() if vs} != {t:[canonical(root(v)) for v in vs] for t,vs in after.items() if vs}:
        raise ValueError('Army or fallback formation changed')
    ledger.rows = {(r['state'],r['owner'],r['building']):r for r in actual}
    fleets = verify(ledger,(mod/FORMATIONS).read_text(encoding='utf-8-sig'),report)
    for row in actual:
        if row['owner'] in managed and row['building']==BUILDING:
            if not ledger.allowed(BUILDING,row['owner']) or any(not target.available(pm,techs[row['owner']],laws[row['owner']]) for pm in row['pms']):
                raise ValueError('Naval department technology/law mismatch')
    meta = read(mod/'.metadata/metadata.json')
    version = re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',meta['version'])
    if not version: raise ValueError('Unexpected base version: '+meta['version'])
    meta['version']=f'0.5.{int(version[1])+1}-m5-test{int(version[2])+1}'
    write(mod/'.metadata/metadata.json',meta)
    changed = [rel for rel,sha in previous['output_sha256'].items() if digest(mod/rel)!=sha]
    allowed = {BUILDINGS,FORMATIONS,'.metadata/metadata.json'} | ({country_file} if source_report else set())
    if not set(changed) <= allowed or not {BUILDINGS,FORMATIONS,'.metadata/metadata.json'} <= set(changed): raise ValueError('Unexpected package changes')
    write(out/'fleet_mapping.json',report)
    for name in ('conversion_report.json',):
        if (prior/name).exists(): shutil.copy2(prior/name,out/name)
    evidence = {'status':'passed','fleets':fleets,
                **{k:sum(c[k] for c in report['countries'].values()) for k in ('input_ships','exported_ships','department_levels')},
                'unallocated_ships':sum(len(c['unallocated_ships']) for c in report['countries'].values()),
                'non_naval_buildings_unchanged':True,'armies_and_fallback_formations_unchanged':True,
                'country_history_and_other_files_byte_identical':country_file not in changed,'runtime_verified':False}
    if source_report:
        for tag,c in report['countries'].items():
            if c['input_ships'] != source_report['countries'][tag]['source_warships']:
                raise ValueError('Source warship count mismatch: '+tag)
        exported_ids = [uid for f in report['formations'] for uid in f['source_ids']]
        missing_ids = [s['source_id'] for c in report['countries'].values() for s in c['unallocated_ships']]
        expected_ids = [s['source_id'] for members in source_ships.values() for s in members]
        if Counter(exported_ids+missing_ids) != Counter(expected_ids): raise ValueError('Source ship identity conservation failed')
        evidence.update(source_warships=sum(c['source_warships'] for c in source_report['countries'].values()),
                        source_transports=sum(c['source_transports'] for c in source_report['countries'].values()),
                        source_ship_identity_conservation=True,country_technology_additions_only=True,
                        unrelated_files_byte_identical=True)
        write(out/'source_navy_mapping.json',source_report)
    write(out/'navy_verification.json',evidence)
    inputs = [prior/'package_report.json',mapping_path,owners_path,config_path,Path(__file__),ROOT/'tools/economy_fleets.py',ROOT/'tools/economy_capacity.py',ROOT/'tools/economy_model.py',
              demographic/'demographics/resident_population_groups.csv',demographic/'template_fallback/template_population_groups.csv',demographic/'staging/province_population_draft.csv']
    inputs += [p for folder in ('ship_types','ship_modifications','defines','strategic_regions','production_methods','buildings','laws') for p in sorted((GAME/'common'/folder).glob('*.txt'))]
    if source_report: inputs += [naval_path,source_path,ROOT/'tools/economy_naval_source.py',ROOT/'tools/extract_naval_source.py']
    package = {'status':'m5_navy_static_verified_runtime_pending','update_scope':'m5_navy_source' if source_report else 'm5_navy','version':meta['version'],
               'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),
               'political_run':previous['political_run'],'demographic_run':previous['demographic_run'],
               'new_campaign_required':True,'changed_files':changed,
               'input_sha256':{str(p):digest(p) for p in inputs},
               'output_sha256':{rel:digest(mod/rel) for rel in previous['output_sha256']}}
    write(out/'package_report.json',package)
    old_checks = read(prior/'verification.json')
    checks = {'status':'passed_static_runtime_pending','literacy':old_checks['literacy'],'navy':evidence,
              'inherited_verified_package':str(prior),'package_report_sha256':digest(out/'package_report.json'),
              'audit_sha256':{n:digest(out/n) for n in ['fleet_mapping.json','navy_verification.json']+(['source_navy_mapping.json'] if source_report else [])}}
    write(out/'verification.json',checks)
    print(json.dumps({'package':str(out),'verification':evidence,'ITA':{k:report['countries']['ITA'][k] for k in ('exported_ships','formation_count','department_levels')},'changed_files':changed}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--naval',type=Path);parser.add_argument('--source',type=Path)
    args=parser.parse_args();build(args.naval,args.source)
