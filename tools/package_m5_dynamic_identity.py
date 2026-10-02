"""Build a narrowly scoped identity update on the latest installed M5 package."""
import argparse
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import shutil
from m5_dynamic_identity import apply
from verify_dynamic_identity import verify

ROOT=Path(__file__).resolve().parents[1]
GAME=Path('D:/Steam/steamapps/common/Victoria 3/game')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def allowed(rel):
    return rel=='.metadata/metadata.json' or rel.startswith(('common/flag_definitions/','common/dynamic_country_names/')) or rel in (
        'common/scripted_triggers/zz_eu5_dynamic_identity.txt','common/coat_of_arms/coat_of_arms/zz_eu5_dynamic_identity.txt',
        'localization/english/eu5_dynamic_identity_l_english.yml','localization/simp_chinese/eu5_dynamic_identity_l_simp_chinese.yml')

def build(output):
    installed=read(ROOT/'.local/economy/installation-latest.json');prior=Path(installed['package']);previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    for rel,h in previous['output_sha256'].items():assert digest(base/rel)==h,rel
    if output.exists():raise ValueError('Output exists')
    mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    mapping=ROOT/'.local/m3/runs/20261001-073149-d689a0e7/conversion_report.json'
    audit=apply(mod,GAME,read(mapping));verification=verify(mod,GAME,audit)
    # Reapplication must not strip the recovered native variants or multiply entries.
    first={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    repeated=apply(mod,GAME,read(mapping))
    assert first=={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()},'Identity overlay not idempotent'
    meta=read(mod/'.metadata/metadata.json')
    import re
    match=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',installed['version']);assert match
    meta['version']=f'0.5.{int(match[1])+1}-m5-test{int(match[2])+1}';dump(mod/'.metadata/metadata.json',meta)
    current={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    changed=[p for p,h in current.items() if previous['output_sha256'].get(p)!=h]
    assert set(previous['output_sha256'])<=set(current)
    assert all(allowed(p) for p in changed),changed
    audit.update(base_version=installed['version'],version=meta['version']);dump(output/'dynamic_identity.json',audit)
    rows=[]
    for tag,c in audit['countries'].items():
        rows.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in [tag,c['name'],c['initial_laws'],len(c['restored_native_flags']),len(c['restored_native_names']),c['generic_flag_variants']])+'</tr>')
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>动态国旗与国名</title><style>body{font:16px system-ui;margin:28px;background:#f5f4ef}td,th{padding:9px;border:1px solid #bbb}table{border-collapse:collapse}</style><h1>动态国旗与国名 · '+meta['version']+'</h1><p>开局沿用源旗帜和国名；改变政体、权力分配或独立状态后，按原版及通用条件选择。恢复原开局政治形态时可恢复源身份。税制、贸易和学校法律不影响开局保留。原版条件保留不代表每个事件和 DLC 分支已完成实机验证。</p><pre>'+html.escape(json.dumps(audit['summary'],ensure_ascii=False,indent=2))+'</pre><p>中国共和国和社会主义旗使用原版变体；大清名称仍要求满族主流文化。自定义国家的新旗式是政治变体设计，不是恢复的 EU5 历史旗。</p><table><tr><th>TAG</th><th>国家</th><th>保留的开局政治形态</th><th>原版旗帜变体</th><th>原版名称变体</th><th>通用旗式</th></tr>'+''.join(rows)+'</table>',encoding='utf-8')
    inputs=[prior/'package_report.json',mapping,Path(__file__),ROOT/'tools/m5_dynamic_identity.py',ROOT/'tools/verify_dynamic_identity.py']
    for folder in ['common/flag_definitions','common/dynamic_country_names','common/scripted_triggers','common/laws']:
        inputs.extend((GAME/folder).glob('*.txt'))
    report={'status':'m5_dynamic_identity_static_verified_runtime_pending','version':meta['version'],'mod_name':meta['name'],
            'mod_directory':str(mod),'prior_package':str(prior),'update_scope':'m5_dynamic_identity','new_campaign_required':False,
            'changed_files':changed,'output_sha256':current,'input_sha256':{str(p.resolve()):digest(p) for p in inputs}}
    dump(output/'package_report.json',report)
    check={'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
           'dynamic_identity':verification,'unrelated_files_byte_identical':True,'idempotent':True,
           'package_report_sha256':digest(output/'package_report.json'),'audit_sha256':{n:digest(output/n) for n in ['dynamic_identity.json','review.html']}}
    dump(output/'verification.json',check)
    print(json.dumps({'package':str(output),'version':meta['version'],'changed':changed,**audit['summary']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.local/economy/packages'/('m5-dynamic-identity-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    build(p.parse_args().output.resolve())
