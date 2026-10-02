"""Hash-pinned population ledger before any demographic export to V3."""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
from pathlib import Path

from pdx_text import Object, root
from extract_m3_politics import validate_audit_document, fields, sequence
from m3_world import digest


def centipersons(thousands):
    amount = Decimal(thousands) * 100000
    if amount != amount.to_integral_value() or amount < 0:
        raise ValueError('Population cannot be represented exactly in centipersons')
    return int(amount)


def extract(save, audit_path, out):
    if out.exists(): raise ValueError('Refusing to overwrite a population extraction')
    sha = digest(save)
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    doc = root(save.read_text(encoding='utf-8')).fields()
    validate_audit_document(doc, audit)
    db = lambda key: fields(fields(doc[key])['database'])
    cultures = {i:fields(o)['culture_definition'] for i,o in db('culture_manager').items() if isinstance(o,Object)}
    religions = {i:fields(o)['definition'] for i,o in db('religion_manager').items() if isinstance(o,Object)}
    pops, missing_sizes = {}, []
    for pid,o in db('population').items():
        if not isinstance(o,Object): continue
        f=fields(o)
        if 'size' not in f: missing_sizes.append(pid)
        pops[pid]=(cultures[f['culture']],religions[f['religion']],f['type'],centipersons(f.get('size','0')))
    out.mkdir(parents=True)
    used, world, by_owner, by_culture, by_religion = set(),0,Counter(),Counter(),Counter()
    audit_locations={str(l['id']):l for l in audit['locations']}
    processed=set()
    with (out/'source_populations.csv').open('w',encoding='utf-8-sig',newline='') as fp, (out/'source_locations.csv').open('w',encoding='utf-8-sig',newline='') as fl:
        writer=csv.writer(fp); writer.writerow(['location_id','location','source_owner','pop_id','source_culture','source_religion','source_class','centipersons'])
        locwriter=csv.writer(fl);locwriter.writerow(['location_id','location','source_owner','centipersons','pop_groups','culture_groups','religion_groups'])
        for lid,obj in fields(fields(doc['locations'])['locations']).items():
            if lid not in audit_locations: raise ValueError('Location absent from independent audit: '+lid)
            f=fields(obj); a=audit_locations[lid]; owner=str(a['owner'])
            refs=sequence(fields(f.get('population')).get('pops'))
            total=0; cs,rs=set(),set()
            for pid in refs:
                if pid in used:raise ValueError('Duplicate population location: '+pid)
                used.add(pid);c,r,kind,n=pops[pid]
                writer.writerow([lid,a['name'],owner,pid,c,r,kind,n])
                total+=n;by_culture[c]+=n;by_religion[r]+=n
                if n:cs.add(c);rs.add(r)
            if total != int(Decimal(a['population_persons'])*100):raise ValueError('Location population differs from C++ audit: '+lid)
            locwriter.writerow([lid,a['name'],owner,total,len(refs),len(cs),len(rs)])
            world+=total;by_owner[owner]+=total;processed.add(lid)
    if processed != set(audit_locations):raise ValueError('Incomplete location traversal')
    if any(row[3] for pid,row in pops.items() if pid not in used):raise ValueError('Unassigned nonzero population')
    assert world == int(Decimal(audit['world_population_persons'])*100)
    for c in audit['countries']:
        assert by_owner[str(c['id'])] == int(Decimal(c['population_persons'])*100), c['id']
    summary={'schema':1,'source_sha256':sha,'audit_sha256':digest(audit_path),'date':audit['date'],
             'status':'source_ledger_validated_not_exported_to_game','locations':len(processed),
             'population_objects':len(pops),'referenced_objects':len(used),
             'world_centipersons':world,'world_persons':str(Decimal(world)/100),
             'missing_size_default_zero_ids':missing_sizes,
             'culture_centipersons':dict(by_culture),'religion_centipersons':dict(by_religion),
             'files_sha256':{p.name:digest(p) for p in out.glob('*.csv')}}
    (out/'source_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:summary[k] for k in ('status','locations','population_objects','world_persons')}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--save',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(json.dumps(extract(a.save,a.audit,a.out)))
