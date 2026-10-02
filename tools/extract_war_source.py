"""Extract active EU5 war objects, retaining repeatable histories and raw goals."""
import argparse
from pathlib import Path
from collections import Counter
from pdx_text import root, Object
from extract_m3_politics import fields, sequence, plain
from military_technology_design import read, write, ROOT
from m3_world import digest

KINDS = ('superiority','take_province','independence','take_capital','take_country',
         'naval_superiority','defend_capital','enforce_military_access','take_border')


def decode_locations(value, valid):
    tokens = sequence(value) if isinstance(value,Object) else [value] if value else []
    if not tokens: return []
    if len(tokens)==1: result=[str(int(tokens[0]))]
    else:
        if len(tokens)%2: raise ValueError('Odd packed location sequence')
        result=[]
        for a,b in zip(tokens[::2],tokens[1::2]):
            start,extra=int(a),int(b)
            if start<0 or extra<0 or extra>=len(valid): raise ValueError('Invalid packed location range')
            result.extend(str(i) for i in range(start,start+extra+1))
    if len(set(result))!=len(result) or not set(result)<=set(valid): raise ValueError('Duplicate/unknown target locations')
    return result


def participant(obj):
    f=fields(obj); history=sequence(f.get('all_history')); status=f['status']
    if status not in ('Active','Left','Potential','Declined'): raise ValueError('Unknown participation status: '+status)
    joined=[fields(h) for h in history if 'joined' in fields(h)]
    latest=joined[-1] if joined else fields(history[-1]) if history else {}
    req=fields(latest.get('request')); side=req.get('side')
    if status=='Active' and (not joined or 'left' in latest or side not in ('Attacker','Defender')):
        raise ValueError('Active member has inconsistent participation history')
    return {'source_id':f['country'],'status':status,'side':side,'reason':req.get('reason'),
            'joined_date':fields(latest.get('joined')).get('date'),'history':plain(f.get('all_history'))}


def extract(save, output, expected_sha):
    sha=digest(save)
    if sha!=expected_sha: raise ValueError('War source campaign mismatch')
    doc=root(save.read_text(encoding='utf-8-sig')).fields()
    db=fields(fields(doc['war_manager'])['database'])
    locations=fields(fields(doc['locations'])['locations'])
    provinces=fields(fields(doc['provinces'])['database'])
    wars=[]; used=set()
    for wid,obj in db.items():
        if not isinstance(obj,Object):
            if obj!='none': raise ValueError('Unexpected war database slot')
            continue
        f=fields(obj); goals=[]; members=[]
        for bucket in ('all','potential_for_diplomacy'):
            members.extend(participant(o) for o in sequence(f.get(bucket)))
        active=[p for p in members if p['status']=='Active']
        ids=[p['source_id'] for p in active]
        if len(ids)!=len(set(ids)) or {p['side'] for p in active}!={'Attacker','Defender'}:
            raise ValueError('Duplicate participant or missing war side')
        for kind in KINDS:
            if kind not in f: continue
            g=fields(f[kind]); t=fields(g.get('target')); province=fields(provinces.get(t.get('target_province')))
            lids=decode_locations(t.get('target_locations'),locations); used.update(lids)
            goals.append({'kind':kind,'definition':g['type'],'casus_belli':g.get('casus_belli'),
                          'target':plain(g.get('target')),'location_ids':lids,
                          'province_definition':province.get('province_definition'),'province_capital':province.get('capital')})
        if not goals and f.get('has_civil_war') == 'yes':
            goals.append({'kind':'civil_war','definition':'source_civil_war','casus_belli':None,
                          'target':None,'location_ids':[],'province_definition':None,'province_capital':None,
                          'evidence':'has_civil_war=yes; no serialized territorial objective'})
        if not goals and fields(f.get('war_name')).get('name')=='AGRESSION_WAR_NAME':
            goals.append({'kind':'aggression','definition':'source_aggression_without_serialized_goal','casus_belli':None,
                          'target':None,'location_ids':[],'province_definition':None,'province_capital':None,
                          'evidence':'Native AGRESSION_WAR_NAME; no serialized objective. Converted using explicit humiliation/border-budget approximation; no source territorial demand inferred.'})
        if len(goals)!=1: raise ValueError('Unsupported number of source war objectives: '+wid)
        war_locations=fields(f.get('locations')); used.update(war_locations)
        wars.append({'id':wid,'start_date':f['start_date'],'original_attacker':f['original_attacker'],
                     'original_target':f['original_attacker_target'],'goals':goals,'participants':members,
                     'revolt':f.get('revolt')=='yes','dependency':plain(f.get('dependency')),
                     'war_name':plain(f.get('war_name')),'subjects_fighting_for_independence':sequence(f.get('subjects_fighting_for_independence')),
                     'location_ids':list(war_locations),'raw_attacker_score':f.get('attacker_score'),
                     'raw_defender_score':f.get('defender_score'),
                     'battle_history':[plain(v) for k,v in obj.entries() if k=='battle'],
                     'losses':{k:plain(v) for k,v in obj.entries() if 'losses' in k}})
    selected={lid:{k:v for k,v in fields(locations[lid]).items() if k in ('owner','controller','province','last_controller_change')}
              for lid in sorted(used,key=int)}
    result={'schema':1,'source_sha256':sha,'source_path':str(save),'wars':wars,'locations':selected,
            'slots':len(db),'active_wars':len(wars),'active_memberships':sum(p['status']=='Active' for w in wars for p in w['participants'])}
    write(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    policy=read(ROOT/'config/personal/opening_wars.json');save=Path(read(ROOT/'.local/m1/main-report/import_report.json')['source'])
    result=extract(save,a.output,policy['source_sha256']);print({k:result[k] for k in ('active_wars','active_memberships','slots')})
