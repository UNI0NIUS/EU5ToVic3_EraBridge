"""Display-only patch and readable framework register on a preserved M5 baseline."""
from collections import Counter
import csv
import html
import json
from pathlib import Path
import re

from build_m2_prototype import objects, patch, replace_body
from build_m3_world import block, load_localization
from m3_world import digest
from m5_dynamic_identity import entries
from package_m4_population_test import effective, parse_pops, GAME
from package_m5_culture_refinement import read, write, homeland_pairs
from extract_m3_politics import fields
from pdx_text import root
from religion_icon_texture import compile_icon
from verify_dynamic_identity import evaluate, choose

TRIGGERS='common/scripted_triggers/zz_eu5_dynamic_identity.txt'
ART='common/coat_of_arms/coat_of_arms/zz_eu5_dynamic_identity.txt'
LOCFILES=['localization/replace/'+l+'/eu5_framework_names_l_'+l+'.yml' for l in ('english','simp_chinese')]


def allowed_display(p):
    return p in {TRIGGERS,ART,*LOCFILES} or p.startswith('common/flag_definitions/') or bool(re.fullmatch(r'gfx/interface/icons/religion_icons/eu5_religion_[a-z_]+\.dds',p))


def put(p,s):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding='utf-8-sig')


def apply_display(mod,world,policy,out):
    # Surgical patch: preserve latest shogunate name logic, custom law guards and
    # every native flag variant. Only split status-dependent flag preservation.
    guard_path=mod/TRIGGERS; raw=guard_path.read_text(encoding='utf-8-sig')
    guards=entries(guard_path); additions=[]; guard_names={}
    for key,obj in guards.items():
        if not key.startswith('eu5_identity_start_'):continue
        new=key.replace('eu5_identity_start_','eu5_flag_start_',1)
        body=re.sub(r'(?m)^\s*is_subject\s*=\s*(yes|no)\s*$', '', obj.text())
        additions.append(block(new,body));guard_names[key]=new
    assert guard_names
    put(guard_path,raw+'\n'+''.join(additions))
    updated_flags=[]
    for path in (mod/'common/flag_definitions').glob('*.txt'):
        raw=path.read_text(encoding='utf-8-sig');changed=raw
        for old,new in guard_names.items():
            changed=re.sub(r'\b'+old+r'\b',new,changed)
        if raw!=changed:
            put(path,changed);updated_flags.append(path.relative_to(mod).as_posix())
    art=(mod/ART).read_text(encoding='utf-8-sig')
    old_geometry='scale = { 0.46 0.46 } offset = { 0.50 0.46 }'
    count=art.count(old_geometry);assert count>0
    art=art.replace(old_geometry,'scale = { 1 1 } offset = { 0 0 }')
    art=art.replace('position = { 0.65 0.23 } scale = { 0.23 0.32 }','position = { 0.82 0.22 } scale = { 0.16 0.22 }')
    put(mod/ART,art)
    scripts={k:v for base in (GAME,mod) for path in (base/'common/scripted_triggers').glob('*.txt') for k,v in entries(path).items()}
    flags={k:v for path in (mod/'common/flag_definitions').glob('*.txt') for k,v in entries(path).items()}
    checked=[]
    for tag,flag in flags.items():
        opening=[fields(v) for k,v in flag.entries() if k=='flag_definition' and fields(v).get('priority')=='100000']
        if not opening:continue
        assert len(opening)==1
        f=opening[0];new='eu5_flag_start_'+tag
        if new not in scripts:continue
        body=scripts[new].text()
        context={'laws':set(re.findall(r'has_law\s*=\s*law_type:(\w+)',body)),'ideology':'ideology_moderate'}
        for subject in (False,True):
            context['subject']=subject
            assert choose(flag,context,scripts,'flag_definition')==f['coa'],(tag,subject)
        checked.append(tag)
    assert checked
    icons={}
    for p in sorted((mod/'gfx/interface/icons/religion_icons').glob('eu5_religion_*.dds')):
        source=Path('D:/Steam/steamapps/common/Europa Universalis V/game/main_menu/gfx/interface/icons/religion')/(p.name.removeprefix('eu5_religion_'))
        icons[p.relative_to(mod).as_posix()]=dict(compile_icon(source,p),source=str(source),source_sha256=digest(source))
    # Authoritative replace localizations also cover old save keys. Do not rename
    # internal reviewed_* IDs: old saves may still reference those stable keys.
    categories=['common/cultures','common/discrimination_traits','common/discrimination_trait_groups']
    keys=set().union(*(set(effective(mod,d)) for d in categories))
    markers=re.compile(r'审核|审查|映射|待审|待定|暂定|未核|候选|review|pending|mapping|provisional|candidate',re.I)
    for lang,rel in zip(('english','simp_chinese'),LOCFILES):
        loc=load_localization(GAME/'localization'/lang)
        loc.update(load_localization(mod/'localization'/lang))
        loc.update(load_localization(mod/'localization/replace'/lang))
        index=0 if lang=='english' else 1
        loc.update({k:v[index] for k,v in policy['labels'].items()})
        for c,spec in policy['assets'].items():loc[c]=spec['labels'][index]
        missing=[k for k in keys if not loc.get(k) or loc[k]==k]
        bad=[(k,loc[k]) for k in keys if markers.search(loc.get(k,''))]
        assert not missing and not bad,('Display labels',missing,bad)
        put(mod/rel,'l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(loc[k],ensure_ascii=False)+'\n' for k in sorted(keys)))
    result={'flags':{'status_only_transitions_checked':len(checked),'country_tags':checked,
              'full_size_compositions':count,'names_and_law_guards_preserved':True,
              'native_flag_conditions_preserved':True,'runtime_verified':False,
              'bloc_scenario':'Bloc operations do not appear in the generated preservation guards; engine-specific overlays still require runtime inspection.'},
            'icons':icons,'localization':{'keys_per_language':len(keys),'missing':0,'review_markers':0,'stable_old_save_keys_retained':True},
            'changed_flag_files':updated_flags}
    return result


def render_report(out,report,policy,verification):
    mod=Path(report['mod_directory']);cultures=effective(mod,'common/cultures')
    traits=effective(mod,'common/discrimination_traits');groups=effective(mod,'common/discrimination_trait_groups')
    loc=load_localization(GAME/'localization/simp_chinese');loc.update(load_localization(mod/'localization/simp_chinese'));loc.update(load_localization(mod/'localization/replace/simp_chinese'))
    pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');totals=Counter()
    for (_,_,c,_),n in pops.items():totals[c]+=n
    pairs=homeland_pairs((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig'))
    rows=[]
    for c,f in sorted(cultures.items(),key=lambda x:-totals[x[0]]):
        h,l=f['heritage'],f['language'];hg=traits[h]['trait_group']
        rows.append(dict(key=c,name=loc[c],population=totals[c],heritage=loc[h],heritage_group=loc[hg],language=loc[l],
                         homelands=' | '.join(s for s,k in sorted(pairs) if k==c),
                         decision='新增具名身份/封闭合称' if c in policy['assets'] else '本次调整正式名称' if c in policy['labels'] else '保留既有框架'))
    with (out/'culture_framework.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    esc=lambda v:html.escape(str(v)); check=verification['culture_framework'];display=read(out/'display.json')
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 文化框架与显示修复</title><style>body{font:16px/1.7 system-ui;margin:30px;background:#f3f5f8;color:#203346}table{border-collapse:collapse;width:100%;background:white}td,th{border:1px solid #ccd6df;padding:8px;text-align:left}th{position:sticky;top:0;background:#e5edf4}input{font:inherit;padding:9px;width:65%}.note{padding:15px;background:#fff1d4}a{color:#1763a4}</style><h1>M5 文化框架与显示修复 · '+esc(report['version'])+'</h1>'
    page+='<p>当前人口 '+f"{check['population']:,}"+'；使用文化 '+str(check['used_cultures'])+'；新增身份资产 '+str(check['new_culture_assets'])+'；新增传承 0；新增历史本土 '+str(check['added_homeland_pairs'])+' 对。</p>'
    page+='<p>正式文化、语言、传承与文化圈名称统一输出；保留稳定键以兼容旧存档引用。人口文化和本土需新开战役，旧存档不会被自动迁移。</p>'
    unresolved=[k for k,x in policy['decisions'].items() if x['evidence_status']=='historical_boundary_unresolved']
    page+='<p class="note">逐项记录 '+str(len(policy['decisions']))+' 个映射问题组；其中 '+str(len(unresolved))+' 组仍有历史边界证据限制，保留/限制设计不等于历史定论。姓名池和外观仍沿用模板。没有把未知身份改标为历史审核通过。</p>'
    page+='<p>独立不再触发缩小原旗；政体变体保留全尺寸原旗。8种新增宗教图标编译为256像素居中纹理。静态回读通过，游戏内独立／国家集团与UI效果尚待实测。</p>'
    page+='<p><a href="verification.json">独立验证</a> · <a href="policy.snapshot.json">逐项设计与史料</a> · <a href="culture_framework.csv">完整表 CSV</a> · <a href="display.json">国旗和图标证据</a> · <a href="installation.json">安装记录</a></p>'
    page+='<h2>逐项决定</h2><table><tr><th>组</th><th>决定</th><th>证据状态</th></tr>'+''.join('<tr><td>'+esc(k)+'</td><td>'+esc(v['decision'])+'</td><td>'+('边界仍有证据限制' if k in unresolved else '有限游戏设计')+'</td></tr>' for k,v in policy['decisions'].items())+'</table>'
    page+='<h2>全部有效文化</h2><input id="q" placeholder="搜索名称、传承、文化圈或本土"><table><thead><tr>'+''.join('<th>'+x+'</th>' for x in ['正式名称','人口','传承','文化圈','语言','本土','本轮处理'])+'</tr></thead><tbody id="rows">'+''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in ['name','population','heritage','heritage_group','language','homelands','decision'])+'</tr>' for r in rows)+'</tbody></table>'
    page+='<h2>本轮引用</h2><ul>'+''.join('<li><a href="'+esc(u)+'">'+esc(k)+'</a></li>' for k,u in policy['sources'].items())+'</ul><script>document.getElementById("q").oninput=function(){let q=this.value.toLowerCase();for(let r of document.querySelectorAll("#rows tr"))r.hidden=!r.textContent.toLowerCase().includes(q)}</script></html>'
    (out/'index.html').write_text(page,encoding='utf-8')
