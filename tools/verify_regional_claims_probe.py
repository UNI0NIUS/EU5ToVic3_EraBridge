"""Check isolated start, JAP formation and claim revocation snapshots."""
import argparse
import json
from pathlib import Path
from pdx_text import root,Object
from extract_m3_politics import fields
from regional_claims import tokens,STATES
from package_m5_dynamic_identity import read,dump,digest


def verify(package,runtime):
    report=read(package/'package_report.json');audit=read(package/'regional-claims.json');policy=read(package/'policy.snapshot.json')
    for rel,sha in report['output_sha256'].items():assert digest(package/'eu5_economy_test'/rel)==sha,rel
    base=Path(read(Path(report['prior_package'])/'package_report.json')['mod_directory'])
    original={}
    for state,obj in root((base/STATES).read_text(encoding='utf-8-sig')).fields()['STATES'].entries():
        for k,v in obj.entries():
            if k=='add_claim':original.setdefault(v[2:],set()).add(state[2:])
    expected=set(policy['japan']['states']);result=[]
    for path in sorted((runtime/'save games').glob('TEST_FAIL_eu5_claims_*.v3')):
        doc=root(path.read_text(encoding='utf-8-sig')).fields();date=doc['date']
        countries={k:fields(v) for k,v in fields(fields(doc['country_manager'])['database']).items() if isinstance(v,Object)}
        bytag={}
        for cid,c in countries.items():
            tag=c['definition']
            if tag not in bytag or c.get('capital','4294967295')!='4294967295':bytag[tag]=(cid,c)
        claims={t:set(tokens(c.get('claims'))) for t,(_,c) in bytag.items()}
        living_japan=[]
        for tag in audit['japan_eligible']:
            if tag=='JAP':continue
            assert claims[tag]==original.get(tag,set())|expected,(date,tag,claims[tag])
            living_japan.append(tag)
        for tag in audit['tibet_eligible']:
            wanted=original.get(tag,set())|{r['state'] for r in audit['claims'] if r['tag']==tag}
            assert claims[tag]==wanted,(date,tag,claims[tag],wanted)
        jap=bytag['JAP'][1]
        wanted_jap=(set() if date=='1836.1.3' else expected-({'STATE_RYUKYU_ISLANDS'} if date=='1836.3.2' else set()))
        assert claims['JAP']==wanted_jap,(date,'JAP',claims['JAP'],wanted_jap)
        variables=fields(jap.get('variables')).get('data')
        initialized=any(fields(v).get('flag')=='eu5_japan_claims_initialized' for _,v in variables.entries()) if isinstance(variables,Object) else False
        assert initialized==(date!='1836.1.3'),(date,'initialization guard')
        interests=[]
        ids={bytag[t][0]:t for t in living_japan}
        for v in fields(fields(doc['interest_manager'])['database']).values():
            f=fields(v)
            if f.get('country') in ids and f.get('strategic_region')=='region_northeast_asia':
                interests.append({'tag':ids[f['country']],'involvement':f.get('current_involvement')})
        assert {r['tag'] for r in interests}==set(living_japan),'Claimants need Northeast Asia interest'
        result.append({'date':date,'snapshot_sha256':digest(path),'existing_japan_claimants':living_japan,
                       'claims_per_existing_country':len(expected),'JAP_claims':sorted(claims['JAP']),
                       'JAP_initialized':initialized,'interests':interests,'tibet_gate_verified':True})
    assert {r['date'] for r in result}=={'1836.1.3','1836.2.3','1836.3.2'}
    errors=(runtime/'logs/error.log').read_text(encoding='utf-8-sig',errors='replace')
    # The external test overlay was written without a BOM; the engine explicitly
    # accepts it. Do not confuse that warning with a script failure.
    relevant=[line for line in errors.splitlines() if ('zz_eu5_regional_claims.txt' in line or 'eu5_claims_probe.txt' in line)
              and 'should be in utf8-bom encoding (will try to use it anyways)' not in line]
    assert not relevant,relevant
    evidence={'status':'passed','package_report_sha256':digest(package/'package_report.json'),
              'snapshots':result,'probe_files_sha256':{p.relative_to(runtime).as_posix():digest(p) for p in (runtime/'probe_mod').rglob('*') if p.is_file()},
              'isolated_mutations':'Day 5: E7K changes tag to JAP. Day 36: JAP loses Ryukyu claim. Neither operation is in the installed mod.',
              'scope':'Claims loaded, Tibet no-white gate, dormant JAP, one-time grant after tag change, revoked claim not restored next month. Actual colonization blocking not tested: these regions have no decentralized land in this campaign.'}
    dump(package/'regional-claims-runtime.json',evidence)
    verified=read(package/'verification.json');verified['regional_claims']['runtime_verified']=True
    verified['regional_claims']['runtime_scope']=evidence['scope']
    verified['audit_sha256']['regional-claims-runtime.json']=digest(package/'regional-claims-runtime.json')
    dump(package/'verification.json',verified)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--package',type=Path,required=True);parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args();verify(args.package,args.runtime)
