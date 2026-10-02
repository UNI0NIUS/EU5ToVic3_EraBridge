"""Index EU5 bookmark colonial rights as evidence, never grant V3 claims."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from pdx_text import root


def audit(game, output):
    source=game/'main_menu/setup/start/23_colonies.txt'
    data=source.read_bytes();container=root(data.decode('utf-8-sig')).fields()['colony_manager']
    unique={};duplicates=[]
    for province,obj in container.entries():
        row={'source_province':province,**obj.fields()}
        if province in unique:
            if unique[province]!=row:raise ValueError('Conflicting bookmark rights: '+province)
            duplicates.append(province)
        unique[province]=row
    result={'status':'evidence_only_no_claims_generated','basis':'EU5 1337 bookmark setup',
            'source_path':str(source.resolve()),'source_sha256':hashlib.sha256(data).hexdigest(),
            'rights':list(unique.values()),'identical_duplicate_provinces':duplicates,
            'unique_provinces_by_tag':dict(Counter(r['tag'] for r in unique.values())),
            'required_before_conversion':['Check actual source save for superseding rights and ownership.',
                'Identify surviving holder or evidenced successor; no automatic conquest or culture-only succession.',
                'Map exact source provinces to target geography; do not expand a small right to an unrelated whole state.',
                'Require actual decentralized land and viable claimant; no forced restoration of the 1337 map.']}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','unique_provinces_by_tag','identical_duplicate_provinces']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--output',type=Path,default=Path('.local/regional-claims/1337-baseline-audit.json'))
    a=p.parse_args();audit(a.game,a.output)
