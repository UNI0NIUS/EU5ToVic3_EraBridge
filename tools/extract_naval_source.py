"""Count extant EU5 hull entities, independently of fleet templates or damage."""
import argparse
from collections import Counter
import json
from pathlib import Path

from economy_model import definitions
from extract_m3_politics import fields
from extract_military_source import inherited
from m3_world import digest
from pdx_text import Object, root


def flagged(value): return value not in (None, 'no', '0', '4294967295')


def extract(save, eu5, output):
    if output.exists(): raise ValueError('Refusing to overwrite naval source ledger')
    sha = digest(save)
    defs = definitions(eu5/'in_game/common/unit_types')
    doc = root(save.read_text(encoding='utf-8-sig')).fields()
    units = fields(fields(doc['unit_manager'])['database'])
    subunits = fields(fields(doc['subunit_manager'])['database'])
    ships, exclusions, counts = [], [], Counter()
    for uid,obj in subunits.items():
        if not isinstance(obj,Object): continue
        f = fields(obj); category = inherited(defs,f['type']).get('category','')
        if not category.startswith('navy_'): continue
        parent = fields(units.get(f.get('unit')))
        reason = None
        if flagged(f.get('prisoner')): reason = 'prisoner'
        elif flagged(f.get('mercenary')) or flagged(parent.get('mercenary')): reason = 'mercenary'
        elif isinstance(f.get('levies'),Object) and list(f['levies'].entries()): reason = 'levy'
        elif not parent: reason = 'missing_parent_fleet'
        elif parent.get('is_army') == 'yes': raise ValueError('Ship belongs to army: '+uid)
        elif f.get('owner') != parent.get('country'): raise ValueError('Ship/fleet owner mismatch: '+uid)
        if not f.get('owner'): raise ValueError('Ship without owner: '+uid)
        row = {'id':uid,'owner':f['owner'],'controller':f.get('controller'),'unit':f.get('unit'),
               'home':f.get('home'),'last_port':parent.get('last_port'),'type':f['type'],'category':category,
               'hulls':1,'serialized_strength':float(f['strength']) if 'strength' in f else None}
        counts[category] += 1
        if reason: exclusions.append({**row,'reason':reason})
        else: ships.append(row)
    data = {'schema':1,'source_sha256':sha,'ships':ships,'excluded':exclusions,'categories':dict(counts),
            'count_basis':'One extant naval subunit ID is one hull; damage, number labels and fleet templates never multiply counts.',
            'unit_definition_sha256':{str(p):digest(p) for p in sorted((eu5/'in_game/common/unit_types').glob('*.txt'))}}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'ships':len(ships),'excluded':len(exclusions),'categories':dict(counts),'source_sha256':sha}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('save','eu5','output'): parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args(); print(json.dumps(extract(a.save,a.eu5,a.output)))
