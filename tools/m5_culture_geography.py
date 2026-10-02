"""Auditable custom culture colours and homelands over the installed M5 baseline."""
import argparse, colorsys, csv, html, json, re, shutil
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import numpy as np
from build_m2_prototype import objects, patch, replace_body
from build_m3_world import load_localization
from m3_world import digest, load_json
from m4_religions import definitions, source_color
from package_m4_population_test import parse_pops
from pdx_text import root

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
CULTURE_FILES=['common/cultures/'+s for s in ('zz_eu5_cultures.txt','zz_eu5_resident_cultures.txt','zz_eu5_migrant_cultures.txt')]
STATE_FILE='common/history/states/00_eu5_world.txt'
COLOR=re.compile(r'\bcolor\s*=\s*(?:(rgb|hsv|hsv360)\s*)?\{([^}]+)\}')
POLICY=ROOT/'config/personal/m5_culture_geography.json'

def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def read_color(body):
    m=COLOR.search(body)
    if not m:raise ValueError('Missing color')
    values=[float(v) for v in m[2].split()]
    if m[1]=='hsv':
        # Two pinned vanilla definitions contain out-of-range HSV brightness.
        # Clamp only for our display-distance comparison; never rewrite vanilla.
        if values in ([0,0,90],[0.01,0.47,67]):values[2]=1
        values=colorsys.hsv_to_rgb(*values)
    elif m[1]=='hsv360':values=colorsys.hsv_to_rgb(values[0]/360,values[1]/100,values[2]/100)
    elif max(values)>1:values=[v/255 for v in values]
    if len(values)!=3 or not all(0<=v<=1 for v in values):raise ValueError('Invalid color')
    return list(values)

def lab(rgb):
    a=np.asarray(rgb,dtype=float);a=np.where(a<=0.04045,a/12.92,((a+0.055)/1.055)**2.4)
    xyz=a@np.array([[.4124564,.3575761,.1804375],[.2126729,.7151522,.0721750],[.0193339,.1191920,.9503041]]).T
    xyz=xyz/np.array([.95047,1,1.08883]);f=np.where(xyz>216/24389,np.cbrt(xyz),xyz*(24389/27)/116+16/116)
    return np.stack([116*f[...,1]-16,500*(f[...,0]-f[...,1]),200*(f[...,1]-f[...,2])],axis=-1)

def majority(n,total):return total>0 and n*2>total

def historical_anchors(path,cross,links,wanted):
    evidence=defaultdict(list);strongest={};unmapped=[]
    for location,obj in objects(root(path.read_text(encoding='utf-8-sig')).fields()['locations']):
        amounts=Counter();members=defaultdict(set)
        for op,pop in objects(obj):
            if op!='define_pop':continue
            f=pop.fields();n=int(Decimal(f['size'])*100000);target=cross.get(f['culture'],f['culture'])
            amounts[target]+=n;members[target].add(f['culture'])
        total=sum(amounts.values())
        for c,n in amounts.items():
            if c not in wanted or not n or not total:continue
            rec={'culture':c,'location':location,'centipersons':n,'location_centipersons':total,
                 'members':sorted(members[c]),'states':sorted(links.get(location,()))}
            previous=strongest.get(c)
            if rec['states'] and (not previous or n*previous['location_centipersons']>previous['centipersons']*total):strongest[c]=rec
            if n*5>=total:
                if rec['states']:evidence[c].append(rec)
                else:unmapped.append(rec)
    return evidence,strongest,unmapped

def build():
    policy=load_json(POLICY)
    assert policy['ordinary_homelands']['minimum_source_location_share_percent']==20
    assert policy['migrant_homelands']['rule']=='strictly_greater_than_50_percent'
    assert policy['dispersed_policy'] in ('no_forced_homeland','strongest_historical_location')
    installed=load_json(ROOT/'.local/m5/installation-latest.json');base=Path(installed['package'])
    baseline=load_json(base/'package_report.json');source=Path(baseline['mod_directory'])
    for rel,sha in baseline['output_sha256'].items():assert digest(source/rel)==sha,rel
    demographic=Path(load_json(ROOT/'.local/m4/demographics-latest.json')['run'])
    catalog={r['culture']:r for r in rows(demographic/'template_fallback/candidate_culture_catalog.csv')}
    culture_objects={c:(rel,o) for rel in CULTURE_FILES for c,o in objects(root((source/rel).read_text(encoding='utf-8-sig')))}
    wanted=set(culture_objects);assert len(wanted)==140 and all(c.startswith('eu5_') for c in wanted)
    migrant={c for c in wanted if c.startswith('eu5_migrant_')};ordinary=wanted-migrant
    pops=parse_pops(source/'common/history/pops/00_eu5_world.txt');state_total=Counter();counts=Counter();totals=Counter()
    for (s,owner,c,religion),n in pops.items():state_total[s]+=n;counts[s,c]+=n;totals[c]+=n
    cross={r['source_culture']:r['target_culture'] for r in rows(demographic/'demographics/resident_culture_crosswalk.csv')}
    links=defaultdict(set)
    for r in rows(demographic/'staging/province_population_draft.csv'):links[r['source_location']].add(r['target_state'])
    histpath=EU5/'main_menu/setup/start/06_pops.txt'
    anchors,strongest,unmapped=historical_anchors(histpath,cross,links,ordinary)
    homeland=defaultdict(set);reasons=defaultdict(list)
    for c,records in anchors.items():
        for e in records:
            for s in e['states']:
                homeland[c].add(s);reasons[c,s].append({'rule':'1337_local_share_at_least_20_percent',**e})
    for (s,c),n in counts.items():
        if c in wanted and majority(n,state_total[s]):
            homeland[c].add(s);reasons[c,s].append({'rule':'1780_output_state_strict_majority','integer_persons':n,'state_integer_persons':state_total[s]})
    for c in ordinary:
        if not homeland[c] and c in policy['dispersed_exceptions']:
            if policy['dispersed_policy']=='strongest_historical_location':
                e=strongest[c];s=e['states'][0]
                homeland[c].add(s);reasons[c,s].append({'rule':'user_selected_strongest_historical_location',**e})
        elif not homeland[c]:raise ValueError('Unreviewed ordinary culture without a homeland: '+c)
    native={c:o for p in sorted((GAME/'common/cultures').glob('*.txt')) for c,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    native_colors={c:read_color(o.text()) for c,o in native.items()}
    defs=definitions(EU5/'in_game/common/cultures');named=(EU5/'main_menu/common/named_colors/02_map.txt').read_text(encoding='utf-8-sig')
    preferred={};preference_basis={}
    for c,(rel,o) in culture_objects.items():
        key=c.removeprefix('eu5_resident_') if c.startswith('eu5_resident_') else c.removeprefix('eu5_')
        if c in migrant:key=c.removeprefix('eu5_migrant_').rsplit('_',1)[0] # overridden from audited migrant record below
        if c in migrant:
            d=load_json(demographic/'demographics/demographics_report.json')
            key=next(r['source'] for r in d['migrant_cultures']['cultures'] if r['target']==c)
        try:preferred[c]=source_color(named,defs[key]['color'])[0];preference_basis[c]='EU5 source '+key
        except (ValueError,KeyError):preferred[c]=read_color(o.text());preference_basis[c]='existing explicitly normalized asset color'
    # A deterministic palette with perceptual separation, preferentially near
    # the source hue; shared-state neighbours receive extra separation weight.
    candidates=np.array([colorsys.hsv_to_rgb(h/96,s,v) for h in range(96) for s in (.40,.55,.70,.85,.98) for v in (.50,.62,.74,.86,.98)])
    labs=lab(candidates);existing=dict(native_colors);assigned={};color_audit={}
    for c in sorted(wanted,key=lambda c:(-totals[c],c)):
        occupied=lab(list(existing.values()));distance=np.linalg.norm(labs[:,None,:]-occupied[None,:,:],axis=2).min(axis=1)
        pref=lab(preferred[c]);near=np.linalg.norm(labs-pref,axis=1)
        states={s for s,k in counts if k==c}
        neighbours=[k for k in existing if any(counts[s,k]>0 for s in states)]
        local=np.linalg.norm(labs[:,None,:]-lab([existing[k] for k in neighbours])[None,:,:],axis=2).min(axis=1) if neighbours else distance
        allowed=distance>=policy['colors']['minimum_delta_e_76']
        if not allowed.any():raise ValueError('Color separation budget exhausted')
        score=np.where(allowed,-near+0.65*np.minimum(local,35),-1e9);idx=int(score.argmax())
        rgb=[round(float(v),5) for v in candidates[idx]];assigned[c]=rgb;existing[c]=rgb
        color_audit[c]={'preferred_rgb':preferred[c],'basis':preference_basis[c],'rgb':rgb,
                        'hex':'#'+''.join(f'{round(v*255):02X}' for v in rgb),
                        'nearest_assigned_delta_e':float(distance[idx]),'nearest_assigned_same_state_delta_e':float(local[idx])}
    out=ROOT/'.local/economy/packages'/('m5-cultural-homelands-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    mod=out/'eu5_economy_test';shutil.copytree(source,mod)
    for rel in CULTURE_FILES:
        text=(source/rel).read_text(encoding='utf-8-sig');edits=[]
        for c,o in objects(root(text)):
            body,n=COLOR.subn('color = { '+' '.join(f'{v:.5f}' for v in assigned[c])+' }',o.text());assert n==1
            edits.append(replace_body(o,body))
        (mod/rel).write_text(patch(text,edits),encoding='utf-8-sig')
    text=(source/STATE_FILE).read_text(encoding='utf-8-sig');edits=[];states=root(text).fields()['STATES'].fields()
    assert all('s:'+s in states for ss in homeland.values() for s in ss)
    for scope,obj in states.items():
        additions=sorted(c for c in wanted if scope.removeprefix('s:') in homeland[c])
        if additions:edits.append(replace_body(obj,obj.text()+''.join('\nadd_homeland = cu:'+c+'\n' for c in additions)))
    (mod/STATE_FILE).write_text(patch(text,edits),encoding='utf-8-sig')
    meta=load_json(mod/'.metadata/metadata.json');meta['version']='0.5.3-m5-test4'
    meta['short_description']='Integrated M5: distinct custom culture colors and evidence-based homelands; migrant homelands require strict state majority. New campaign required.'
    (mod/'.metadata/metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    inputs=[POLICY,base/'package_report.json',histpath,EU5/'main_menu/common/named_colors/02_map.txt',demographic/'demographics/resident_culture_crosswalk.csv',demographic/'staging/province_population_draft.csv',demographic/'demographics/demographics_report.json',demographic/'location_reviews.snapshot.json']
    inputs+=sorted((EU5/'in_game/common/cultures').glob('*.txt'))+sorted((GAME/'common/cultures').glob('*.txt'))
    audit={'policy':policy,'colors':color_audit,'homelands':{c:sorted(homeland[c]) for c in sorted(wanted)},
           'homeland_evidence':[{'culture':c,'state':s,'evidence':e} for (c,s),e in sorted(reasons.items())],
           'historical_anchors_without_mapping':unmapped,'no_homeland':{c:('no_state_strict_majority' if c in migrant else 'explicit_dispersed_exception') for c in sorted(wanted) if not homeland[c]},
           'historical_strongest_for_dispersed':{c:strongest.get(c) for c in policy['dispersed_exceptions']},
           'demographic_run':str(demographic),'input_sha256':{str(p):digest(p) for p in inputs}}
    (out/'culture_geography.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'culture_geography.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['culture','name','kind','population','color_hex','homeland_count','homelands','status'])
        for c in sorted(wanted):w.writerow([c,catalog[c]['name'],catalog[c]['kind'],totals[c],color_audit[c]['hex'],len(homeland[c]),'|'.join(sorted(homeland[c])),audit['no_homeland'].get(c,'assigned')])
    labels=load_localization(GAME/'localization/simp_chinese')
    trs=[]
    for c in sorted(wanted,key=lambda c:-totals[c]):
        color=color_audit[c]['hex'];label=catalog[c]['name'];hs='、'.join(labels.get(s,s)+' ('+s+')' for s in sorted(homeland[c])) or ('无：没有超过半数的州' if c in migrant else '无：分散少数文化，保留无本土')
        trs.append('<tr><td><span class="swatch" style="background:'+color+'"></span>'+color+'</td><td>'+html.escape(label)+'<small>'+c+'</small></td><td>'+f'{totals[c]:,}'+'</td><td>'+str(len(homeland[c]))+'</td><td>'+html.escape(hs)+'</td></tr>')
    page='<!doctype html><meta charset="utf-8"><title>M5 新文化颜色与本土</title><style>body{font:15px/1.6 system-ui;margin:32px;background:#f5f3ef;color:#24302e}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}th{position:sticky;top:0;background:#e1e9e4}small{display:block;color:#677}td:last-child{max-width:700px}.swatch{display:inline-block;width:40px;height:22px;vertical-align:middle;margin-right:10px;border:1px solid #555}input{padding:10px;width:60%}</style><h1>M5：140 种新文化颜色与本土</h1><p>普通文化：EU5 1337 年地点占比至少20%的聚居地，并补充1780年严格多数州。移民文化：整个州内超过50%，包括分割州的所有政权人口。已有本土全部保留。颜色仅用于地图区分。</p><input placeholder="搜索文化或州" oninput="for(const r of document.querySelectorAll(\'tbody tr\'))r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase())"><table><thead><tr><th>颜色</th><th>文化</th><th>人口</th><th>本土州数</th><th>本土</th></tr></thead><tbody>'+''.join(trs)+'</tbody></table>'
    (out/'culture_geography.html').write_text(page,encoding='utf-8')
    changed={*CULTURE_FILES,STATE_FILE,'.metadata/metadata.json'}
    for rel,sha in baseline['output_sha256'].items():
        if rel not in changed:assert digest(mod/rel)==sha,rel
    report=dict(baseline);report.update(status='m5_culture_geography_static_candidate',version=meta['version'],mod_directory=str(mod),prior_package=str(base),update_scope='m5_culture_geography',
        culture_geography_sha256=digest(out/'culture_geography.json'),input_sha256=audit['input_sha256'],
        output_sha256={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()})
    (out/'package_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'package':str(out),'custom_cultures':len(wanted),'homeland_pairs':sum(map(len,homeland.values())),'no_homeland':audit['no_homeland'],'unmapped_historical_anchors':len(unmapped)},ensure_ascii=True))
    return out

if __name__=='__main__':build()
