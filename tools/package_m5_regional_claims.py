"""Apply opening claims to the latest installed package, preserving all other work."""
import argparse
from datetime import datetime
from pathlib import Path
import html
import json
import re
import shutil
from regional_claims import ROOT,POLICY,STATES,COUNTRIES,CODE,HOOKS,EFFECTS,definitions,bloc_leaders,plan,apply,source_tibetan_cultures,japan_runtime
from package_m5_dynamic_identity import GAME,read,dump,digest
from package_m5_culture_refinement import files
from pdx_text import root
from build_m3_world import load_localization

EU5=Path('D:/Steam/steamapps/common/Europa Universalis V/game')


def build(output):
    installed=read(ROOT/'.local/economy/installation-latest.json')
    prior=Path(installed['package']);previous=read(prior/'package_report.json');base=Path(installed['target'])
    assert files(base)==previous['output_sha256'],'Installed baseline changed'
    assert not output.exists()
    policy=read(POLICY);world_path=ROOT/'.local/m3/runs/20261001-073149-d689a0e7/conversion_report.json'
    world=read(world_path)
    src=source_tibetan_cultures(EU5,policy['tibet']['source_culture_group'])
    source={t:c['source_culture'] for t,c in world['countries'].items() if c.get('source_culture') in src}
    country_defs=definitions(GAME,'country_definitions',mod=base);cultures=definitions(GAME,'cultures',mod=base)
    leaders=bloc_leaders([p.read_text(encoding='utf-8-sig') for p in (base/'common/history/power_blocs').glob('*.txt')],policy['japan']['bloc_identity'])
    state_text=(base/STATES).read_text(encoding='utf-8-sig');country_text=(base/COUNTRIES).read_text(encoding='utf-8-sig')
    audit=plan(state_text,country_text,country_defs,cultures,leaders,policy,source)
    labels=load_localization(base/'localization/simp_chinese')
    audit['country_names']={t:labels.get('EU5_DYNAMIC_SOURCE_'+t,labels.get(t,c.get('name_simp_chinese',t)))
                            for t,c in world['countries'].items()}
    audit['country_names'].setdefault('JAP','日本')
    new=apply(state_text,audit)
    assert apply(new,audit)==new
    clean=lambda text:re.sub(r'\s+','',re.sub(r'\badd_claim\s*=\s*c:\w+','',text))
    assert clean(new)==clean(state_text),'Non-claim state history changed'
    before=root(state_text).fields()['STATES'].fields();after=root(new).fields()['STATES'].fields()
    for state,obj in before.items():
        old={v for k,v in obj.entries() if k=='add_claim'}
        actual={v for k,v in after[state].entries() if k=='add_claim'}
        expected={'c:'+r['tag'] for r in audit['claims'] if 's:'+r['state']==state}
        assert actual==old|expected,state
    mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    (mod/STATES).write_text(new,encoding='utf-8-sig')
    runtime=japan_runtime((base/CODE).read_text(encoding='utf-8-sig'),policy)
    assert japan_runtime(runtime[CODE],policy)==runtime
    for rel,text in runtime.items():
        path=mod/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig')
    meta=read(mod/'.metadata/metadata.json');m=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',installed['version']);assert m
    meta['version']=f'0.5.{int(m[1])+1}-m5-test{int(m[2])+1}';dump(mod/'.metadata/metadata.json',meta)
    dump(output/'regional-claims.json',audit);dump(output/'policy.snapshot.json',policy)
    names=audit['country_names'];label=lambda tag:names.get(tag,tag)+' ('+tag+')'
    rows=''.join('<tr><td>'+html.escape(r['state'])+'</td><td>'+html.escape(label(r['tag']))+'</td><td>'+r['rule']+'</td></tr>' for r in audit['claims'])
    review='''<!doctype html><meta charset="utf-8"><title>地区宣称与殖民边界</title><style>body{font:17px/1.8 system-ui;max-width:1050px;margin:40px auto}td,th{padding:6px 15px;border-bottom:1px solid #ddd}table{border-collapse:collapse}</style>'''
    review+='<h1>地区宣称 · '+meta['version']+'</h1><p>日本本土十州及琉球：授予幕府法国家、幕府集团首领与 JAP。JAP 未建国时无实际宣称；建国时一次性授予，月度检查兜底。不包含库页岛、朝鲜和整个东北亚战略区。</p>'
    review+='<p>藏文化国家按实际主流文化及藏文化源身份识别；仅给仍有分权国家土地的阿里、拉萨、青海授予宣称。本档这三州均无白地，未新增藏区宣称。候选国家：'+html.escape('、'.join(label(t) for t in audit['tibet_eligible']))+'。</p>'
    review+='<p>宣称作用于整州，不能只圈定州内白地，不改变领土归属。原版殖民阻挡还要求宣称国有当地利益且能够到达；已有宣称的其他国家仍可殖民，后续撤销宣称也不会被脚本强制恢复。保留原版殖民法律、机构和战争规则。</p>'
    review+='<p>后续扩展以 EU5 1337 开局为历史基准，并核对实际源存档的变化；优先调查源游戏已有的排他殖民条约，例如瑞典／诺夫哥罗德的诺特堡条约范围。北亚、美洲和太平洋须从当地政权、居民与政治联系确定候选，不套用 V3 后来的殖民版图。目标须仍有白地，权利国须存续或存在明确继承证据。V3 原版用于机制参考；这些扩展尚未启用。</p>'
    review+='<p><a href="https://www.paradoxinteractive.com/games/victoria-3/news/dev-diary-78-update-1-2-changelog">原版宣称殖民规则</a> · <a href="regional-claims.json">完整审计</a></p><table><tr><th>州</th><th>宣称国</th><th>规则</th></tr>'+rows+'</table>'
    (output/'review.html').write_text(review,encoding='utf-8')
    current=files(mod);changed=sorted(k for k,v in current.items() if previous['output_sha256'].get(k)!=v)
    assert set(changed)<= {STATES,CODE,HOOKS,EFFECTS,'.metadata/metadata.json'}
    assert set(previous['output_sha256'])<=set(current)
    inputs=[POLICY,Path(__file__),ROOT/'tools/regional_claims.py',ROOT/'tools/build_m3_world.py',world_path,prior/'package_report.json']
    inputs.extend(p for folder in [GAME/'common/country_definitions',GAME/'common/cultures',EU5/'in_game/common/cultures'] for p in folder.glob('*.txt'))
    report={'status':'m5_regional_claims_static_verified_runtime_pending','version':meta['version'],'mod_name':meta['name'],
        'mod_directory':str(mod),'prior_package':str(prior),'update_scope':'m5_regional_claims','new_campaign_required':True,
        'changed_files':changed,'output_sha256':current,'input_sha256':{str(p.resolve()):digest(p) for p in inputs}}
    dump(output/'package_report.json',report)
    dump(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
        'regional_claims':{'status':'passed','claims_only':True,'existing_claims_preserved':True,'white_land_gate_verified':True,'idempotent':True,'runtime_verified':False},
        'unrelated_files_byte_identical':True,'package_report_sha256':digest(output/'package_report.json'),
        'audit_sha256':{n:digest(output/n) for n in ['regional-claims.json','policy.snapshot.json','review.html']}})
    print(json.dumps({'package':str(output),'version':meta['version'],'japan':audit['japan_eligible'],'tibet':audit['tibet_eligible'],
                      'claims':len(audit['claims']),'skipped':audit['skipped']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.local/economy/packages'/('m5-regional-claims-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    build(p.parse_args().output.resolve())
