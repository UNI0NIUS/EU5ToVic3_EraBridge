"""Read native test snapshots; never modify game saves or the installed mod."""
import argparse
import hashlib
import json
from pathlib import Path
from pdx_text import root, Object
from extract_m3_politics import fields


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(package, runtime):
    audit=json.loads((package/'shogunate.json').read_text(encoding='utf-8-sig'))
    report=json.loads((package/'package_report.json').read_text(encoding='utf-8-sig'))
    for rel,sha in report['output_sha256'].items():
        assert digest(package/'eu5_economy_test'/rel)==sha,rel
    results=[]
    for path in sorted((runtime/'save games').glob('TEST_FAIL_eu5_shogunate_*.v3')):
        doc=root(path.read_text(encoding='utf-8-sig')).fields()
        db=lambda key:fields(fields(doc[key])['database'])
        countries={cid:fields(v) for cid,v in db('country_manager').items() if isinstance(v,Object)}
        tags={cid:c['definition'] for cid,c in countries.items()}
        bytag={c['definition']:c for c in countries.values()}
        pacts=[];parents={}
        for obj in db('pacts').values():
            p=fields(obj);targets=fields(p.get('targets'))
            if p.get('action') in {'personal_union','vassal','puppet','dominion','tributary','protectorate','chartered_company'}:
                pair=[tags[targets['first']],tags[targets['second']]]
                parents[pair[1]]=pair[0]
                if p['action']=='personal_union':pacts.append(pair)
        for pair in audit['personal_union_maintenance_checked']:
            assert pair in pacts,('Missing personal union',pair,doc['date'])
        groups=[]
        for expected in audit['blocs']:
            found=[(bid,fields(v)) for bid,v in db('power_bloc_manager').items()
                   if fields(v).get('identity')=='identity_eu5_shogunate'
                   and tags.get(fields(v).get('leader'))==expected['leader']]
            assert len(found)==1
            bid,bloc=found[0];assert bloc['status']=='active'
            members={}
            for tag in expected['members']:
                c=bytag[tag];sovereign=tag;seen=set()
                while sovereign in parents:
                    assert sovereign not in seen;seen.add(sovereign);sovereign=parents[sovereign]
                assert bytag[sovereign].get('power_bloc_as_core')==bid,(tag,sovereign)
                assert not c.get('power_bloc_leave_date'),tag
                members[tag]={'government':c.get('government'),'sovereign':sovereign}
            seat=bytag[expected['nominal_shogun']]
            assert seat.get('government') in {'gov_eu5_shogunate','gov_eu5_regency_shogunate'},seat.get('government')
            # Anonymous variable entries must be iterated, not collapsed into a dict.
            variables={}
            data=fields(bytag[expected['leader']].get('variables')).get('data')
            if isinstance(data,Object):
                variables={fields(v).get('flag'):fields(fields(v).get('data')).get('identity','0') for _,v in data.entries()}
            groups.append({'leader':expected['leader'],'members':members,'authority':int(variables['eu5_shogunate_authority'])/100000,
                           'crisis_months':int(variables['eu5_shogunate_crisis_months'])/100000})
        results.append({'date':doc['date'],'save_sha256':digest(path),'personal_unions_checked':len(audit['personal_union_maintenance_checked']),'blocs':groups})
    assert {r['date'] for r in results}=={'1836.1.3','1836.2.2'},'Both snapshots required'
    logs='\n'.join(p.read_text(encoding='utf-8-sig',errors='replace') for p in (runtime/'logs').glob('*.log'))
    relevant=[line for line in logs.splitlines() if ('already has a journal entry' in line and 'je_eu5_shogunate' in line)
              or ('cannot be maintained' in line and 'personal_union' in line)
              or ('Unexpected token' in line and 'should_be_pinned_by_default' in line)]
    assert not relevant,relevant
    output={'status':'passed','scope':'Opening and first month: personal unions, membership, government, authority; later decisions not verified',
            'package_report_sha256':digest(package/'package_report.json'),'runtime_directory':str(runtime.resolve()),'snapshots':results,
            'snapshot_method':'Scripted test failure conditions intentionally capture saves at requested dates.'}
    (package/'shogunate-runtime.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True);parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args();verify(args.package,args.runtime)
