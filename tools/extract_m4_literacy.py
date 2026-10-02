"""Extract per-pop EU5 literacy without rewriting the frozen population ledger."""
import csv
from collections import Counter
from decimal import Decimal
import json
from pathlib import Path
from pdx_text import root,Object
from m3_world import load_json,digest

ROOT=Path(__file__).resolve().parents[1]
SAVE=ROOT/'.local/m0/samples/d4e6bcb5f0c9-SP_ITA_1780_07_04_93fd61d6-5caf-4f9c-860e-16418cd4cbb8.eu5'
SOURCE=ROOT/'.local/m4/source-1780-population'
OUT=ROOT/'.local/m4/source-1780-literacy-v1'
SCALE=1000000 # exact micro-percent; fraction denominator is 100*SCALE

def rate_units(value):
    n=Decimal(value)
    if not n.is_finite() or not 0<=n<=100:raise ValueError('Source literacy outside 0..100 percent')
    units=n*SCALE
    if units!=units.to_integral_value():raise ValueError('Literacy needs finer exact precision')
    return int(units)

def extract(SAVE=SAVE, SOURCE=SOURCE, OUT=OUT):
    summary=load_json(SOURCE/'source_summary.json')
    if digest(SAVE)!=summary['source_sha256']:raise ValueError('Unexpected source save')
    if OUT.exists():
        r=load_json(OUT/'source_literacy_report.json')
        if digest(OUT/'source_literacy.csv')!=r['ledger_sha256'] or r['source_sha256']!=summary['source_sha256']:raise ValueError('Existing literacy extraction changed')
        return r
    doc=root(SAVE.read_text(encoding='utf-8')).fields()
    database=doc['population'].fields()['database']
    values={}
    for pid,obj in database.entries():
        if not isinstance(obj,Object):continue
        if pid in values:raise ValueError('Duplicate source POP')
        f=obj.fields();values[pid]=(rate_units(f.get('literacy','0')), 'literacy' not in f,int(Decimal(f.get('size','0'))*100000))
    OUT.mkdir(parents=True)
    totals=Counter();weights=Counter();missing=[];seen=set();entries=[]
    with (SOURCE/'source_populations.csv').open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            pid=row['pop_id'];n=int(row['centipersons']);u,default,source_n=values[pid]
            if pid in seen or n!=source_n:raise ValueError('Source population reconciliation failed')
            seen.add(pid);totals[row['source_owner']]+=n;weights[row['source_owner']]+=n*u
            if default:missing.append(pid)
            entries.append([pid,n,u,int(default)])
    if sum(totals.values())!=summary['world_centipersons']:raise ValueError('World population differs')
    if any(n for pid,(_,_,n) in values.items() if pid not in seen):raise ValueError('Unreferenced nonzero source POP')
    with (OUT/'source_literacy.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['pop_id','centipersons','literacy_micro_percent','omitted_zero']);w.writerows(entries)
    r={'status':'source_literacy_extracted','source_save':str(SAVE),'source_sha256':summary['source_sha256'],
       'population_ledger_sha256':digest(SOURCE/'source_populations.csv'),'ledger_sha256':digest(OUT/'source_literacy.csv'),
       'scale':SCALE,'source_population_objects':len(values),'referenced_objects':len(seen),'omitted_zero_ids':missing,
       'omitted_field_policy':'EU5 omitted scalar defaults to zero; same default as the existing C++ Population.literacy field. Every omission recorded.',
       'world_centipersons':sum(totals.values()),'weighted_literacy_numerator':sum(weights.values()),
       'world_literacy_percent':str(Decimal(sum(weights.values()))/Decimal(sum(totals.values())*SCALE)),
       'source_owner_literacy_percent':{k:str(Decimal(weights[k])/Decimal(n*SCALE)) for k,n in totals.items() if n}}
    (OUT/'source_literacy_report.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
    return r

if __name__=='__main__':
    r=extract();print(json.dumps({k:v for k,v in r.items() if k not in ('source_owner_literacy_percent','omitted_zero_ids')}));print('omitted_zero_fields',len(r['omitted_zero_ids']));print('source_ITA_literacy_percent',r['source_owner_literacy_percent']['1481'])
