"""Review all military technologies against source evidence; never deploy history."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import json
from pathlib import Path

from build_economy import expand_template_tech
from complete_economy import active_laws
from economy_fleets import read_ships
from economy_model import Target, building_rows, closure, definitions
from extract_m3_politics import fields, sequence
from m3_world import digest
from pdx_text import Object, root

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5 = Path('D:/Steam/steamapps/common/Europa Universalis V/game')
PREDICATES = {'advances_any','advances_all','institutions_any','unlocked_units_any','actual_units_any','regular_army','any_ship'}


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,obj): Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def validate(policy, target, advances, units, institutions):
    expected = {k for k,f in target.techs.items() if f['category']=='military'}
    if set(policy['rules']) != expected: raise ValueError('Military target catalogue coverage mismatch')
    if policy['military_generic_progress_grants'] is not False: raise ValueError('Generic progress grants are disabled')
    for key,rule in policy['rules'].items():
        if rule['mode'] not in ('evidence','combined','withhold'): raise ValueError('Unknown military rule mode')
        if (rule['mode']=='withhold') == bool(rule['any_of']): raise ValueError('Invalid evidence/withhold clauses: '+key)
        if set(rule.get('related_advances',[]))-advances.keys(): raise ValueError('Unknown related source evidence')
        for clause in rule['any_of']:
            if not clause or set(clause)-PREDICATES: raise ValueError('Unknown/empty military rule predicate')
            for predicate,values in clause.items():
                if predicate in ('regular_army','any_ship'):
                    if values is not True: raise ValueError('Invalid actual-force predicate')
                    continue
                valid = advances if predicate.startswith('advances_') else institutions if predicate=='institutions_any' else units
                if not values or set(values)-valid.keys(): raise ValueError('Unknown source reference: '+key+' '+predicate)
    closure(target.techs,target.techs)


def evaluate(country, actual_units, regular_army, any_ship, policy, target, advances):
    known = set(country['advances'])
    if known-advances.keys(): raise ValueError('Unknown researched source advances')
    unlocked = defaultdict(list)
    for key in sorted(known):
        unit = advances[key].get('unlock_unit')
        if isinstance(unit,str): unlocked[unit].append(key)
    facts = {'advances_any':known,'advances_all':known,'institutions_any':set(country['institutions']),
             'unlocked_units_any':set(unlocked),'actual_units_any':set(actual_units)}
    roots, decisions = {}, {}
    for key,rule in policy['rules'].items():
        matches = []
        for clause in rule['any_of']:
            evidence = {}
            for predicate,expected in clause.items():
                if predicate in ('regular_army','any_ship'):
                    hit = regular_army if predicate=='regular_army' else any_ship
                    if not hit: break
                    evidence[predicate] = True
                else:
                    hit = set(expected)&facts[predicate]
                    if not hit or predicate=='advances_all' and hit!=set(expected): break
                    evidence[predicate] = sorted(hit)
                    if predicate=='unlocked_units_any': evidence['unlock_advance_ids'] = sorted({a for u in hit for a in unlocked[u]})
            else: matches.append(evidence)
        if matches: roots[key] = matches
        decisions[key] = {'mode':rule['mode'],'reason':rule['reason'],'source_evidence':matches,
                          'related_researched':sorted(known & set(rule.get('related_advances',[]))),
                          'decision':'source_evidence' if matches else 'withheld' if rule['mode']=='withhold' else 'missing_source_evidence'}
    selected = closure(roots,target.techs)
    for key in selected-set(roots):
        if key in decisions:
            decisions[key]['decision']='prerequisite_closure'
            decisions[key]['required_by']=sorted(k for k in roots if key in closure({k},target.techs))
    return selected,decisions


def build(output):
    if output.exists(): raise ValueError('Refusing to overwrite a military design review')
    installed = read(ROOT/'.local/economy/installation-latest.json')
    package = Path(installed['package']); report = read(package/'package_report.json'); mod = Path(report['mod_directory'])
    for rel,sha in report['output_sha256'].items():
        if digest(mod/rel)!=sha: raise ValueError('Installed baseline package changed: '+rel)
    config_path=ROOT/'config/personal/military_technology.json'; policy=read(config_path)
    target=Target(GAME); advances=definitions(EU5/'in_game/common/advances')
    units=definitions(EU5/'in_game/common/unit_types'); institutions=definitions(EU5/'in_game/common/institution')
    validate(policy,target,advances,units,institutions)
    source_path=ROOT/'.local/economy/source-1780-v2.json'; source=read(source_path)
    land_path=ROOT/'.local/economy/source-military-1780-v2.json'; land=read(land_path)
    navy_path=ROOT/'.local/economy/source-navy-1780-v1.json'; navy=read(navy_path)
    mapping_path=Path(report['political_run'])/'conversion_report.json'; mapping=read(mapping_path)
    if len({x['source_sha256'] for x in (source,land,navy,mapping)})!=1: raise ValueError('Military design source mismatch')
    current, histories = defaultdict(set), {}
    effects={k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    for path in sorted((mod/'common/history/countries').glob('*.txt')):
        for key,obj in fields(root(path.read_text(encoding='utf-8-sig')))['COUNTRIES'].entries():
            tag=key[2:]; current[tag].update(expand_template_tech(obj,effects,target))
            if path.name=='00_eu5_world.txt': histories[tag]=obj
    actual,regular,ship_owners=defaultdict(set),set(),set()
    for row in land['subunits']:
        if row['levies'] or row['mercenary']:continue
        actual[row['owner']].add(row['type'])
        if row['category']!='army_auxiliary':regular.add(row['owner'])
    for row in navy['ships']: ship_owners.add(row['owner'])
    rows=building_rows(mod/'common/history/buildings/00_eu5_world.txt')
    compatibility=defaultdict(lambda:defaultdict(list))
    def protect(tag,key,reason): compatibility[tag][key].append(reason)
    for row in rows:
        tag=row['owner']
        for key in sequence(target.buildings[row['building']].get('unlocking_technologies')):protect(tag,key,'building:'+row['building'])
        for pm in row['pms']:
            for key in sequence(target.pms[pm].get('unlocking_technologies')):protect(tag,key,'production_method:'+pm)
    laws=definitions(GAME/'common/laws')
    for tag,obj in histories.items():
        for law in active_laws(obj,target,mapping['countries'][tag]):
            for key in sequence(laws[law].get('unlocking_technologies')):protect(tag,key,'law:'+law)
    formation_text=(mod/'common/history/military_formations/00_eu5_world.txt').read_text(encoding='utf-8-sig')
    _,fleets=read_ships(formation_text,current)
    ships=definitions(GAME/'common/ship_types')
    for tag,items in fleets.items():
        for kind in sorted({x['type'] for x in items}):
            for key in sequence(ships[kind].get('unlocking_technologies')):protect(tag,key,'preserved_vanilla_ship:'+kind)
    combat=definitions(GAME/'common/combat_unit_types'); army_types=defaultdict(Counter)
    for key,country in fields(root(formation_text))['MILITARY_FORMATIONS'].entries():
        for op,form in country.entries():
            if op!='create_military_formation' or fields(form).get('type')!='army':continue
            for operation,unit in form.entries():
                if operation=='combat_unit':army_types[key[2:]][fields(unit)['type'].split(':')[-1]]+=int(fields(unit)['count'])
    results={}; military={k for k,f in target.techs.items() if f['category']=='military'}
    for tag,country in sorted(mapping['countries'].items()):
        if country['source_id'] is None:
            results[tag]={'status':'fallback_unchanged','current':sorted(current[tag]&military)};continue
        sid=str(country['source_id'])
        selected,decisions=evaluate(source['countries'][sid],actual[sid],sid in regular,sid in ship_owners,policy,target,advances)
        keep=current[tag]-military
        safe=closure(selected|keep|set(compatibility[tag]),target.techs)
        for key in military:
            decisions[key].update(source_selected=key in selected,transition_selected=key in safe,current=key in current[tag])
            if key in safe-selected:
                decisions[key]['compatibility_roots']=sorted(set(compatibility[tag].get(key,[])))
                decisions[key]['compatibility_required_by']=sorted(k for k in keep|set(compatibility[tag]) if key in closure({k},target.techs))
        conflicts={kind:n for kind,n in army_types[tag].items() if not set(sequence(combat[kind].get('unlocking_technologies'))) <= safe}
        results[tag]={'status':'design_review_only','source_id':sid,'source_military':sorted(selected&military),
                      'transition_military':sorted(safe&military),'compatibility_only':sorted((safe-selected)&military),
                      'added':sorted((safe-current[tag])&military),'removed':sorted((current[tag]-safe)&military),
                      'land_unit_type_conflicts':conflicts,'decisions':decisions}
    output.mkdir(parents=True)
    write(output/'mapping.json',results);write(output/'policy.snapshot.json',policy)
    source_refs={a for rule in policy['rules'].values() for clause in rule['any_of'] for k,vs in clause.items() if k.startswith('advances_') for a in vs}
    source_refs.update(a for r in policy['rules'].values() for a in r.get('related_advances',[]))
    write(output/'source_evidence.json',{k:{f:(v.text() if isinstance(v,Object) else v) for f,v in advances[k].items()} for k in sorted(source_refs)})
    with (output/'target_rules.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['technology','era','mode','prerequisites','source_conditions','reason'])
        for key,rule in policy['rules'].items():writer.writerow([key,target.techs[key]['era'],rule['mode'],' '.join(sequence(target.techs[key].get('unlocking_technologies'))),json.dumps(rule['any_of'],ensure_ascii=False),rule['reason']])
    managed=[r for r in results.values() if r['status']=='design_review_only']
    summary={'status':'validated_design_not_deployed','baseline_version':installed['version'],'baseline_package':str(package),
             'rule_version':policy['rule_version'],'military_targets':len(military),'source_countries':len(managed),
             'fallback_countries':len(results)-len(managed),'rule_modes':dict(Counter(r['mode'] for r in policy['rules'].values())),
             'countries_with_changes':sum(bool(r['added'] or r['removed']) for r in managed),
             'countries_with_land_type_conflicts':sum(bool(r['land_unit_type_conflicts']) for r in managed),
             'conflicting_battalions':sum(sum(r['land_unit_type_conflicts'].values()) for r in managed),
             'checks':['all_58_targets_have_explicit_rules','all_source_references_resolve','source_hash_agreement','prerequisite_closure','separate_source_and_compatibility_evidence','no_game_or_package_writes'],
             'limitations':['Proposed rules are conversion policy, not historical identity proofs.','Conditional PMs are conservatively protected until deployment evaluates guards.','No candidate mod or runtime validation is produced.']}
    write(output/'verification.json',summary)
    inputs=[config_path,source_path,land_path,navy_path,mapping_path,package/'package_report.json',Path(__file__)]
    inputs += [p for folder in ('advances','unit_types','institution') for p in sorted((EU5/'in_game/common'/folder).glob('*.txt'))]
    inputs += [p for folder in ('technology/technologies','buildings','production_methods','combat_unit_types','ship_types','laws','scripted_effects') for p in sorted((GAME/'common'/folder).glob('*.txt'))]
    write(output/'manifest.json',{'inputs':{str(p.resolve()):digest(p) for p in inputs},'outputs':{p.name:digest(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(output),**summary},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'.local/military-technology'/datetime.now().strftime('review-%Y%m%d-%H%M%S'))
    build(parser.parse_args().output)
