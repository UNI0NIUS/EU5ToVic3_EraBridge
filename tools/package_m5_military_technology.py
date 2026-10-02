"""Deploy evidence-based military technology onto the latest installed M5 baseline."""
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
import re
import shutil

from build_economy import expand_template_tech
from build_m2_prototype import patch
from complete_economy import active_laws
from economy_fleets import read_ships
from economy_model import Target, building_rows, closure, definitions
from extract_m3_politics import fields, sequence
from m3_world import digest
from military_technology_design import GAME, ROOT, build as review, read, write
from pdx_text import Object, root

COUNTRIES = 'common/history/countries/00_eu5_world.txt'
FORMATIONS = 'common/history/military_formations/00_eu5_world.txt'
TECH_LINE = re.compile(r'(?m)^[ \t]*(?:add_technology_researched|add_era_researched|effect_starting_technology_\w+)\s*=\s*[^\s{}#]+[ \t]*(?:#[^\n]*)?$')


def canonical(obj):
    return [(k, canonical(v) if isinstance(v, Object) else v) for k, v in obj.entries()]


def is_technology(key):
    return key in ('add_technology_researched', 'add_era_researched') or bool(key and key.startswith('effect_starting_technology_'))


def nontech(obj):
    return [(k, canonical(v) if isinstance(v, Object) else v) for k, v in obj.entries() if not is_technology(k)]


def replace_technology(obj, technologies):
    body, count = TECH_LINE.subn('', obj.text())
    if count != sum(is_technology(k) for k, _ in obj.entries()):
        raise ValueError('Unsupported or nested technology history syntax')
    body += '\n' + ''.join('add_technology_researched = '+t+'\n' for t in sorted(technologies))
    if nontech(root(body)) != nontech(obj): raise ValueError('Non-technology history changed')
    return body


def legal(kind, techs, units):
    return set(sequence(units[kind].get('unlocking_technologies'))) <= techs


def replacement(kind, techs, units):
    if legal(kind, techs, units): return kind
    # Only walk backwards along vanilla upgrade relationships; never upgrade a legal unit.
    candidates = [k for k, f in units.items() if f.get('group') == units[kind].get('group')
                  and kind in sequence(f.get('upgrades')) and legal(k, techs, units)]
    if candidates:
        return max(candidates, key=lambda k: sum(k in sequence(f.get('upgrades')) for f in units.values()))
    basic = 'combat_unit_type_irregular_infantry'
    if not legal(basic, techs, units): raise ValueError('No legal land unit fallback')
    return basic


def convert_armies(text, techs, units):
    edits, changes = [], []
    for key, country in fields(root(text))['MILITARY_FORMATIONS'].entries():
        tag = key[2:]
        if tag not in techs: continue
        for op, form in country.entries():
            if op != 'create_military_formation' or fields(form).get('type') != 'army': continue
            for operation, unit in form.entries():
                if operation != 'combat_unit': continue
                f = fields(unit); old = f['type'].split(':')[-1]; new = replacement(old, techs[tag], units)
                if new == old: continue
                body, n = re.subn(r'(?<!\w)type\s*=\s*unit_type:'+re.escape(old)+r'\b', 'type = unit_type:'+new, unit.text())
                if n != 1: raise ValueError('Ambiguous unit type')
                expected = [(k, 'unit_type:'+new if k == 'type' else v) for k,v in canonical(unit)]
                if canonical(root(body)) != expected: raise ValueError('Unit changed beyond type')
                edits.append((unit.start, unit.end, body))
                changes.append({'country':tag, 'hq_region':fields(form).get('hq_region'), 'state_region':f['state_region'],
                                'count':int(f['count']), 'before':old, 'after':new,
                                'branch_changed':units[old]['group'] != units[new]['group']})
    return patch(text, edits), changes


def army_signature(text, ignore_types=False):
    def walk(obj, unit=False):
        return [(k, walk(v, k == 'combat_unit') if isinstance(v,Object) else
                 '<preserved-count-unit>' if unit and ignore_types and k == 'type' else v) for k,v in obj.entries()]
    return walk(root(text))


def army_goods(text, units):
    result = defaultdict(Counter)
    for key,country in fields(root(text))['MILITARY_FORMATIONS'].entries():
        for op,form in country.entries():
            if op != 'create_military_formation' or fields(form).get('type') != 'army': continue
            for op,unit in form.entries():
                if op != 'combat_unit': continue
                f=fields(unit); kind=f['type'].split(':')[-1]
                for modifier,value in fields(units[kind].get('upkeep_modifier')).items():
                    match=re.fullmatch(r'goods_input_(.+)_add',modifier)
                    if match: result[key[2:]][match[1]] += int(f['count'])*float(value)
    return result


def build():
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
    out=ROOT/'.local/economy/packages'/('m5-military-technology-'+stamp)
    review_dir=ROOT/'.local/military-technology'/('deploy-'+stamp)
    review(review_dir)
    installed=read(ROOT/'.local/economy/installation-latest.json'); prior=Path(installed['package'])
    old=read(prior/'package_report.json'); base=Path(old['mod_directory'])
    reviewed=read(review_dir/'verification.json'); manifest=read(review_dir/'manifest.json')
    if reviewed['baseline_package'] != str(prior): raise ValueError('Baseline changed during review')
    for path,sha in manifest['inputs'].items():
        if digest(Path(path)) != sha: raise ValueError('Review input changed: '+path)
    for rel,sha in manifest['outputs'].items():
        if digest(review_dir/rel) != sha: raise ValueError('Review output changed: '+rel)
    for rel,sha in old['output_sha256'].items():
        if digest(base/rel) != sha: raise ValueError('Baseline file changed: '+rel)
    mapping=read(review_dir/'mapping.json'); target=Target(GAME)
    political=read(Path(old['political_run'])/'conversion_report.json')
    units=definitions(GAME/'common/combat_unit_types'); laws=definitions(GAME/'common/laws')
    military={k for k,f in target.techs.items() if f['category']=='military'}
    effects={k:v for k,v in root((GAME/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig')).entries() if isinstance(v,Object)}
    before=(base/COUNTRIES).read_text(encoding='utf-8-sig')
    histories={k[2:]:v for k,v in fields(root(before))['COUNTRIES'].entries()}
    current=defaultdict(set); extra=defaultdict(set)
    for path in sorted((base/'common/history/countries').glob('*.txt')):
        for key,obj in fields(root(path.read_text(encoding='utf-8-sig')))['COUNTRIES'].entries():
            found=expand_template_tech(obj,effects,target); current[key[2:]].update(found)
            if path.name != Path(COUNTRIES).name: extra[key[2:]].update(found)
    desired={tag:(current[tag]-military)|set(row['transition_military']) for tag,row in mapping.items() if row['status'] != 'fallback_unchanged'}
    edits=[]
    for tag,techs in desired.items():
        if not extra[tag] <= techs: raise ValueError('Later country history would reintroduce removed technology: '+tag)
        if closure(techs,target.techs) != techs: raise ValueError('Technology prerequisites missing: '+tag)
        edits.append((histories[tag].start,histories[tag].end,replace_technology(histories[tag],techs-extra[tag])))
    after=patch(before,edits)
    after_history={k[2:]:v for k,v in fields(root(after))['COUNTRIES'].entries()}
    for tag,obj in histories.items():
        if tag not in desired:
            if after_history[tag].text() != obj.text(): raise ValueError('Fallback country changed')
        elif nontech(obj) != nontech(after_history[tag]) or expand_template_tech(after_history[tag],effects,target)|extra[tag] != desired[tag]:
            raise ValueError('Country history verification failed: '+tag)
    old_form=(base/FORMATIONS).read_text(encoding='utf-8-sig')
    new_form,changes=convert_armies(old_form,desired,units)
    if army_signature(old_form,True) != army_signature(new_form,True): raise ValueError('Army quantities, placement or navy changed')
    if convert_armies(new_form,desired,units) != (new_form,[]): raise ValueError('Army conversion not idempotent')
    for tag,techs in desired.items():
        for law in active_laws(after_history[tag],target,political['countries'][tag]):
            if not set(sequence(laws[law].get('unlocking_technologies'))) <= techs: raise ValueError('Law technology missing')
    final_techs={**current,**desired}; global_techs=set().union(*final_techs.values())
    for row in building_rows(base/'common/history/buildings/00_eu5_world.txt'):
        if row['owner'] not in desired: continue
        for definition in [target.buildings[row['building']]]+[target.pms[pm] for pm in row['pms']]:
            if not set(sequence(definition.get('unlocking_technologies'))) <= desired[row['owner']]: raise ValueError('Building/PM technology missing')
            if not set(sequence(definition.get('unlocking_global_technologies'))) <= global_techs: raise ValueError('Global PM technology missing')
    ships=definitions(GAME/'common/ship_types'); _,fleets=read_ships(new_form,desired)
    for tag,items in fleets.items():
        for item in items:
            if not set(sequence(ships[item['type']].get('unlocking_technologies'))) <= desired[tag]: raise ValueError('Ship technology missing')
    goods_before=army_goods(old_form,units); goods_after=army_goods(new_form,units)
    impact={}
    for tag in sorted({c['country'] for c in changes}):
        delta={g:goods_after[tag][g]-goods_before[tag][g] for g in goods_before[tag].keys()|goods_after[tag].keys()}
        impact[tag]={'goods_before':goods_before[tag], 'goods_after':goods_after[tag], 'goods_delta':delta,
                     'base_price_goods_cost_delta':sum(target.prices[g]*n for g,n in delta.items())}
    mod=out/'eu5_economy_test'; shutil.copytree(base,mod)
    (mod/COUNTRIES).write_text(after,encoding='utf-8-sig'); (mod/FORMATIONS).write_text(new_form,encoding='utf-8-sig')
    meta=read(mod/'.metadata/metadata.json'); v=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',meta['version'])
    if not v: raise ValueError('Unexpected version')
    meta['version']=f'0.5.{int(v[1])+1}-m5-test{int(v[2])+1}'; write(mod/'.metadata/metadata.json',meta)
    hashes={rel:digest(mod/rel) for rel in old['output_sha256']}
    changed=[rel for rel,sha in hashes.items() if sha != old['output_sha256'][rel]]
    if not set(changed) <= {COUNTRIES,FORMATIONS,'.metadata/metadata.json'}: raise ValueError('Unrelated files changed')
    for name in manifest['outputs']: shutil.copy2(review_dir/name,out/('review_'+name))
    shutil.copy2(review_dir/'manifest.json',out/'review_manifest.json')
    write(out/'army_type_changes.json',changes)
    write(out/'military_goods_impact.json',{'countries':impact, 'base_price_goods_cost_delta':sum(c['base_price_goods_cost_delta'] for c in impact.values()),
          'scope':'Full-strength vanilla land unit base upkeep goods only. Wages, technology modifiers, mobilization, market prices and realized fiscal balance require runtime validation; naval forces and production methods are unchanged.'})
    evidence={'status':'passed','military_targets':len(military),'source_countries':len(desired),
              'countries_with_technology_changes':sum(bool(r.get('added') or r.get('removed')) for r in mapping.values()),
              'countries_with_unit_changes':len(impact),'battalions_retyped':sum(c['count'] for c in changes),
              'branch_changed_battalions':sum(c['count'] for c in changes if c['branch_changed']),
              'army_counts_placement_and_navy_preserved':True,'country_non_technology_and_fallback_preserved':True,
              'all_technology_prerequisites_verified':True,'laws_buildings_pms_ships_technology_verified':True,
              'no_later_history_regrants':True,'unrelated_files_byte_identical':True,'army_conversion_idempotent':True,'runtime_verified':False}
    write(out/'military_technology_verification.json',evidence)
    inputs={**manifest['inputs'],str(Path(__file__).resolve()):digest(Path(__file__))}
    for name in ('build_economy.py','build_m2_prototype.py','complete_economy.py','economy_fleets.py','economy_model.py','pdx_text.py','update_m5_integrated_test.ps1'):
        path=ROOT/'tools'/name; inputs[str(path)]=digest(path)
    report={'status':'m5_military_technology_static_verified_runtime_pending','update_scope':'m5_military_technology',
            'version':meta['version'],'mod_name':meta['name'],'mod_directory':str(mod),'prior_package':str(prior),
            'political_run':old['political_run'],'demographic_run':old['demographic_run'],
            'rule_version':reviewed['rule_version'],'new_campaign_required':True,'changed_files':changed,
            'input_sha256':inputs,'output_sha256':hashes}
    write(out/'package_report.json',report)
    audit={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name != 'package_report.json'}
    write(out/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
          'military_technology':evidence,'inherited_verified_package':str(prior),
          'package_report_sha256':digest(out/'package_report.json'),'audit_sha256':audit})
    print(json.dumps({'package':str(out),'version':meta['version'],'verification':evidence,'changed_files':changed},ensure_ascii=False))
    return out


if __name__ == '__main__': build()
