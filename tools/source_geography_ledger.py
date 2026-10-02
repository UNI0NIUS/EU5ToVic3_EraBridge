"""Extract save-specific population/culture evidence for generic terrain checks."""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import json
from pdx_text import root,Object
from extract_m3_politics import fields,sequence
from m3_world import digest


def extract(save,audit_path,out):
    save,audit_path,out=Path(save),Path(audit_path),Path(out)
    sha,audit_sha=digest(save),digest(audit_path)
    audit=json.loads(audit_path.read_text(encoding='utf-8-sig'))
    if out.exists():
        previous=json.loads(out.read_text(encoding='utf-8'))
        if (previous.get('source_sha256'),previous.get('audit_sha256'),previous.get('extractor_sha256'))==(sha,audit_sha,digest(__file__)):
            return previous
    doc=root(save.read_text(encoding='utf-8')).fields()
    if fields(doc.get('metadata')).get('date')!=audit['date']:raise ValueError('Save/audit date mismatch')
    cultures={i:fields(o)['culture_definition'] for i,o in fields(fields(doc['culture_manager'])['database']).items() if isinstance(o,Object)}
    pops={}
    for pid,o in fields(fields(doc['population'])['database']).items():
        if not isinstance(o,Object):continue
        f=fields(o);amount=Decimal(f.get('size','0'))*100000
        if amount<0 or amount!=amount.to_integral_value():raise ValueError('Invalid source population')
        pops[pid]=(cultures[f['culture']],int(amount))
    locations={str(l['id']):l for l in audit['locations']};totals={};used=set()
    for lid,o in fields(fields(doc['locations'])['locations']).items():
        f=fields(o);location=locations[lid];counts=Counter()
        if str(location['owner'])!=str(f.get('owner','0')):raise ValueError('Save/audit owner mismatch')
        for pid in sequence(fields(f.get('population')).get('pops')):
            if pid in used:raise ValueError('Duplicate source population reference')
            used.add(pid);culture,amount=pops[pid];counts[culture]+=amount
        if sum(counts.values())!=int(Decimal(location['population_persons'])*100):raise ValueError('Save/audit location population mismatch')
        totals[location['name']]=dict(counts)
    if set(totals)!={l['name'] for l in locations.values()}:raise ValueError('Incomplete source locations')
    if any(n for pid,(c,n) in pops.items() if pid not in used):raise ValueError('Unlocated positive population')
    world=sum(sum(c.values()) for c in totals.values())
    if world!=int(Decimal(audit['world_population_persons'])*100):raise ValueError('Save/audit world population mismatch')
    result={'source_sha256':sha,'source_date':audit['date'],'audit_sha256':audit_sha,
            'extractor_sha256':digest(__file__),'location_cultures':totals,'source_populations':len(used),'world_centipersons':world}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    return result
