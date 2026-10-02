"""Audited flag-only overlay on the installed personal M5 package."""
import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

from build_m2_prototype import objects
from m3_flags import FlagExporter
from m3_flag_art import economic_features
from pdx_text import root
from render_m3_flags import render

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')
REPORT=ROOT/'.local/m3/runs/20261001-073149-d689a0e7/conversion_report.json'
POLITICS=ROOT/'.local/m3/politics-with-constitution.json'
SAVE=ROOT/'.local/m0/samples/d4e6bcb5f0c9-SP_ITA_1780_07_04_93fd61d6-5caf-4f9c-860e-16418cd4cbb8.eu5'
ECONOMY=ROOT/'.local/economy/source-1780-v2.json'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
def allowed(rel):
    return rel=='.metadata/metadata.json' or any(rel.startswith(x) for x in
        ('common/coat_of_arms/','common/flag_definitions/','common/named_colors/eu5_m3_flags.txt','gfx/coat_of_arms/'))

class Overlay:
    def __init__(self,w,mod): self.w=w;self.mod=mod;self.binary_assets={};self.flag_report=[]
    def write(self,rel,text):
        assert allowed(rel), rel
        p=self.mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8-sig')

def build(package):
    installed=read(ROOT/'.local/economy/installation-latest.json')
    prior=Path(installed['package']); previous=read(prior/'package_report.json')
    base=Path(previous['mod_directory'])
    # Once political identity exists, always refresh through the source-context
    # pipeline and reapply it; the legacy static exporter would remove variants.
    if (base/'common/scripted_triggers/zz_eu5_dynamic_identity.txt').is_file():
        from package_m5_source_identity import build as build_source_identity
        return build_source_identity(package)
    if package.exists(): raise ValueError('Package already exists')
    for rel,sha in previous['output_sha256'].items():
        assert digest(base/rel)==sha, rel
    assert {p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}==set(previous['output_sha256'])
    mod=package/'eu5_economy_test';shutil.copytree(base,mod)
    report=read(REPORT); politics=read(POLITICS)
    assert digest(SAVE)==report['source_sha256']==politics['source_sha256']
    # Read the pinned save header rather than inferring an age from its date.
    with SAVE.open(encoding='utf-8') as f:
        age=next((m[1] for line in f if (m:=re.match(r'^current_age\s*=\s*(\w+)',line))),None)
    assert age, 'Source age absent'
    politics['current_age']=age
    raw=read(ROOT/'.local/m3/countries-raw.json')
    for sid,source in politics['countries'].items():
        old=dict(raw.get(sid,[]))
        if 'previous_tags' in old: source['previous_tags']=[v for _,v in old['previous_tags']]
    native={k for p in (GAME/'common/country_definitions').glob('*.txt') for k,_ in objects(root(p.read_text(encoding='utf-8-sig')))}
    w=SimpleNamespace(countries=report['countries'],country_defs=native,game=GAME,
        politics=politics,edges=report['subjects'],profile=read(ROOT/'config/personal/m3_world.json'))
    w.read=lambda rel: ((base/rel) if (base/rel).exists() else (GAME/rel)).read_text(encoding='utf-8-sig')
    economy=read(ECONOMY);assert economy['source_sha256']==report['source_sha256']
    coastal={k for p in (GAME/'map_data/state_regions').glob('*.txt')
             for k,o in objects(root(p.read_text(encoding='utf-8-sig'))) if re.search(r'\bnaval_exit_id\s*=',o.text())}
    w.flag_features=economic_features(w.countries,economy,coastal)
    out=Overlay(w,mod); flags=FlagExporter(EU5);flags.export(out)
    for rel,src in out.binary_assets.items():
        dest=mod/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    metadata=read(mod/'.metadata/metadata.json');metadata['version']='0.5.4-m5-test5';dump(mod/'.metadata/metadata.json',metadata)
    current={p.relative_to(mod).as_posix():digest(p) for p in sorted(mod.rglob('*')) if p.is_file()}
    changed=[rel for rel,sha in current.items() if previous['output_sha256'].get(rel)!=sha]
    assert set(previous['output_sha256'])<=set(current)
    assert all(allowed(rel) for rel in changed)
    assert len(out.flag_report)==sum(bool(c.get('source_id')) for c in w.countries.values())
    # Resolve every emitted asset/parent reference against the mod + installed game.
    coa_text=(mod/'common/coat_of_arms/coat_of_arms/zz_eu5_world.txt').read_text(encoding='utf-8-sig')
    assert '@' not in re.sub(r'#[^\n]*','',coa_text)
    coas=dict(objects(root(coa_text)))
    for parent in re.findall(r'\bparent\s*=\s*"?(EU5SRC_\w+)',coa_text): assert parent in coas,parent
    for kind,name in re.findall(r'\b(pattern|texture)\s*=\s*"([^"\n]+)"',coa_text):
        folders=['patterns'] if kind=='pattern' else ['colored_emblems','textured_emblems']
        assert any((b/'gfx/coat_of_arms'/f/name).is_file() for b in (mod,GAME) for f in folders),name
    bytag={x['tag']:x for x in out.flag_report}
    assert bytag['CHI']['resolved_source_flag']=='CHI_Ming'
    assert bytag['ITA']['resolved_source_flag']=='ITA_tricolor_genoa'
    for tag in ['E18','E19','E1A','E1R']: assert bytag[tag]['mode']=='imported_eu5_definition',tag
    definitions={k:o for p in (mod/'common/flag_definitions').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    for row in out.flag_report:
        if row['mode']=='existing_v3_identity_flag': continue
        assert row['tag'] in definitions
        for _,fd in objects(definitions[row['tag']]):
            coa=dict(fd.entries()).get('coa');assert coa in coas,coa
            assert fd.fields()['subject_canton']==coa, 'Overlord must provide its flag to subject cantons'
        if row.get('overlord_canton'):
            assert row['overlord'] in w.countries
            assert 'allow_overlord_canton = yes' in definitions[row['tag']].text()
        if row.get('design'):
            d=row['design']
            if d['colonial']:
                for layer in d['layers']+[dict(position=p,scale=d['scale']) for p in d['positions']]:
                    x,y=layer['position'];sx,sy=layer['scale']
                    if not layer.get('background'): assert x-sx/2>=.4 or y-sy/2>=.4
                    assert 0<=x-sx/2<x+sx/2<=1 and 0<=y-sy/2<y+sy/2<=1
    summary=dict(Counter(x['mode'] for x in out.flag_report))
    ancestor=prior;visited=set()
    while not (ancestor/'conversion_report.json').is_file():
        if ancestor in visited: raise ValueError('Cyclic package ancestry')
        visited.add(ancestor);parent=read(ancestor/'package_report.json').get('prior_package')
        if not parent:break
        ancestor=Path(parent)
    previous_flags=read(ancestor/'conversion_report.json')['flags'] if (ancestor/'conversion_report.json').is_file() else report['flags']
    audit={'schema':1,'source_age':politics['current_age'],'countries':report['countries'],'flags':out.flag_report,
           'summary':summary,'vanilla_fallback_countries':[t for t,c in w.countries.items() if not c.get('source_id')],
           'newly_recovered':[t for t,x in bytag.items() if x['mode']=='imported_eu5_definition' and next(f for f in previous_flags if f['tag']==t)['mode']!='imported_eu5_definition']}
    dump(package/'conversion_report.json',audit);render(package,GAME)
    rows=[]
    for f in out.flag_report:
        c=w.countries[f['tag']]
        vals=[f['tag'],c.get('name_simp_chinese',''),c['source_tag'],f['mode'],f.get('resolved_source_flag') or f.get('source_flag_key',''),f.get('overlord') or '',(f.get('design') or {}).get('basis') or f.get('reason') or f.get('limitation','')]
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in vals)+'</tr>')
    (package/'review.html').write_text('<meta charset="utf-8"><title>国旗覆盖与殖民旗设计</title><style>body{font:16px sans-serif;background:#10202d;color:#eee;margin:28px}td,th{padding:9px;border-bottom:1px solid #435361}table{border-collapse:collapse}img{max-width:100%}input{padding:12px;width:60%}</style><h1>M5 国旗修正 · 0.5.3</h1><p>'+html.escape(str(summary))+'</p><p>游戏素材近似预览，灰色角标在游戏中由宗主旗替换。地域徽记是生成设计，不是假定的历史国徽。未知动态旗及王朝/领土条件仍在清单中明确标注。</p><img src="flag-preview.png"><p><a style="color:#9cd" href="flag-catalogue.png">查看全部生成旗帜</a></p><input placeholder="搜索国家 / TAG / 旗帜来源" oninput="document.querySelectorAll(\'tbody tr\').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['V3 TAG','国家','EU5 TAG','处理方式','纹章键','宗主国','依据或限制'])+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table>',encoding='utf-8')
    page=package/'review.html';page.write_text(page.read_text(encoding='utf-8').replace('0.5.3','0.5.4'),encoding='utf-8')
    manifest={'status':'m5_flags_static_verified_runtime_pending','version':metadata['version'],'mod_name':previous['mod_name'],
        'mod_directory':str(mod),'prior_package':str(prior),'update_scope':'m5_flags','changed_files':changed,
        'output_sha256':current,'source_sha256':report['source_sha256'],'flag_summary':summary,
        'input_sha256':{str(p):digest(p) for p in [REPORT,POLITICS,ECONOMY,ROOT/'.local/m3/countries-raw.json',prior/'package_report.json',Path(__file__),ROOT/'tools/m3_flags.py',ROOT/'tools/m3_flag_art.py']}}
    dump(package/'package_report.json',manifest)
    check={'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
        'flags':{'status':'passed','source_countries':len(bytag),'missing_definitions':0,'missing_textures':0,'canton_collisions':0,
                 'runtime_verified':False,'newly_recovered':audit['newly_recovered']},
        'non_flag_files_byte_identical':True,'package_report_sha256':digest(package/'package_report.json')}
    dump(package/'verification.json',check)
    print(json.dumps({'package':str(package),'summary':summary,'recovered':audit['newly_recovered'],'changed_files':len(changed),'files':len(current)},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);a=p.parse_args();build(a.package.resolve())
