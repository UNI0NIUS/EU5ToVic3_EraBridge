"""Extract read-only economic observations for historical political priors.

These remain source-game quantities, not V3 GDP or converted budgets.
"""
import argparse
import hashlib
import json
from pathlib import Path
from pdx_text import Object,root
from extract_m3_politics import fields,plain


def extract(save,expected_sha256):
    data=save.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=expected_sha256:raise ValueError('Save hash mismatch')
    doc=root(data.decode('utf-8')).fields();result={}
    for cid,obj in fields(fields(doc['countries'])['database']).items():
        if not isinstance(obj,Object):continue
        result[cid]={k:plain(v) for k,v in fields(obj).items() if k and
                     any(t in k for t in ['econom','income','wealth','tax','budget','gdp','treasury','trade'])}
    return {'source_sha256':digest,'countries':result}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('save','politics','output'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Refusing to replace an economic snapshot')
    politics=json.loads(a.politics.read_text(encoding='utf-8'))
    result=extract(a.save,politics['source_sha256'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'countries':len(result['countries']),'source_sha256':result['source_sha256']}))
