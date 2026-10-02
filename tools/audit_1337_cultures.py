"""Freeze an offline 1337 culture review. Never writes production configuration.

Uses the verified source-population ledger, not inferred map area or ruler culture.
New mappings and incomplete assets are proposals, NOT a deployable package.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import html
import json
from pathlib import Path

from audit_m5_culture_identity import (ROOT, EU5, GAME, read, write, sha, tree,
    csvrows, csvwrite, source_catalog, load_localization, effective)
from culture_1337_rules import complete_proposals, REFS, SPECIAL

OUT = ROOT / 'outputs/01a0f510-fde4-7dd3-983c-d5b74834b7cf-culture1337'
LABELS = {'existing_category':'现有类别候选', 'source_field_correction':'源字段纠错候选',
 'extend_closed_composite':'封闭合称增补候选', 'preserve_identity_candidate':'独立身份资产候选',
 'inherited':'沿用既有对应'}

def protected():
    paths = list((ROOT/'config').rglob('*.json'))
    paths += [ROOT/p for p in ['.local/m5/installation-latest.json',
      '.local/economy/installation-latest.json',
      '.local/m3/terrain-workstation-1337/terrain_reviews.json',
      '.local/m4/location-workstation/location_reviews.json']]
    return {str(p):sha(p) for p in paths if p.is_file()}

def build(out):
    out.mkdir(parents=True, exist_ok=True)
    install = read(ROOT/'.local/m5/installation-latest.json')
    mod = Path(install['target'])
    before, files_before = tree(mod), protected()
    package = read(Path(install['package'])/'package_report.json')
    crosswalk_path = Path(package['demographic_run'])/'demographics/resident_culture_crosswalk.csv'
    old = {r['source_culture']:r for r in csvrows(crosswalk_path)}
    prior_path = Path(read(ROOT/'.local/m5/culture-identity-audit-latest.json')['run'])/'audit.json'
    prior = {r['source_culture']:r for r in read(prior_path)['rows']}
    evidence_path = ROOT/'outputs/terrain-1337-reviewed-geography-20261002/source_evidence.json'
    evidence = read(evidence_path)
    source_path = ROOT/'.local/m0/clean-starts/eu5-start.txt'
    assert sha(source_path)==evidence['source_sha256'], 'Source save changed'
    import_path = ROOT/'.local/m1/start-report/import_report.json'
    imported = read(import_path)
    assert imported['date']==evidence['source_date']
    locations = {r['name']:r for r in imported['locations']}
    by_culture, core, unowned = Counter(), defaultdict(list), Counter()
    for loc, pops in evidence['location_cultures'].items():
        assert loc in locations
        for culture, n in pops.items():
            assert isinstance(n,int) and n>=0
            if not n: continue
            by_culture[culture]+=n
            core[culture].append((loc,n))
            if not locations[loc]['owner']: unowned[culture]+=n
    assert sum(by_culture.values())==evidence['world_centipersons']
    assert not set(old)-by_culture.keys(), 'Unexpected 1780-only source identities'
    catalog, hashes = source_catalog()
    definitions = effective(mod,'common/cultures')
    names = load_localization(EU5/'main_menu/localization/simp_chinese')
    target_names = load_localization(GAME/'localization/simp_chinese')
    target_names.update(load_localization(mod/'localization/simp_chinese'))
    new = set(by_culture)-old.keys()
    proposals = complete_proposals(new,catalog,definitions)
    for p in proposals.values():
        if p.get('template'): assert p['template'] in definitions
        else: assert p['target'] in definitions
    rows=[]
    for key,n in sorted(by_culture.items(), key=lambda kv:(kv[0] not in new,-kv[1],kv[0])):
        is_new=key in new
        if is_new:
            p=proposals[key]
        else:
            target=old[key]['target_culture']
            assert prior[key]['target_culture']==target, 'Baseline audit is stale'
            p=dict(target=target,status='inherited',reason=prior[key]['reason'],refs=[],
                language_note='沿用当前资产；旧审查问题继续保留，不代表1337年代核定通过。',
                homeland_note='按1337分布重新核查；不复制1780州级本土。',
                language_candidate=definitions[target].get('language',''),
                heritage_candidate=definitions[target].get('heritage',''), issue='继承既有审查状态')
        source_name=names.get(key,key)
        special=SPECIAL.get(key,{})
        rows.append(dict(source_culture=key,source_name=source_name,
            population_1337_centipersons=n,population_1780_centipersons=int(old[key]['centipersons']) if not is_new else 0,
            new_in_1337=is_new,target_culture=p['target'],
            target_name=target_names.get(p['target'],source_name+'（候选）'),
            decision=p['status'],decision_name=LABELS[p['status']],
            inherited_audit=prior[key]['status'] if not is_new else '',
            source_language=catalog[key]['language'],source_groups=catalog[key]['groups'],
            language_candidate=p['language_candidate'],heritage_candidate=p['heritage_candidate'],
            language_note=p['language_note'],homeland_note=p['homeland_note'],
            issue=p['issue'],reason=p['reason'],
            source_location_count=len(core[key]),unowned_centipersons=unowned[key],
            top_locations=[dict(location=l,name=names.get(l,l),centipersons=v) for l,v in sorted(core[key],key=lambda z:-z[1])[:5]],
            reference_urls=[REFS[k][1] for k in p['refs']],
            inherited_reference_ids=prior[key]['sources'] if not is_new else [],
            historically_approved=False))
    mapping={r['source_culture']:r['target_culture'] for r in rows}
    targets=Counter()
    for r in rows:targets[r['target_culture']]+=r['population_1337_centipersons']
    assets={k:p for k,p in proposals.items() if p['target'] not in definitions}
    pending_legacy=[r for r in rows if r['inherited_audit'] in ('scope_design','historical_review','source_label_review')]
    summary=dict(source_date=evidence['source_date'],baseline_version=install['version'],
        cultures_1337=len(rows),cultures_1780=len(old),additional_1337=len(new),
        persons_1337=sum(by_culture.values())/100,
        new_decisions=dict(Counter(p['status'] for p in proposals.values())),
        existing_target_candidates=sum(p['target'] in definitions for p in proposals.values()),
        new_asset_candidates=len(assets),inherited_pending_rows=len(pending_legacy),
        base_resident_targets=len(targets),effective_definitions_before=len(definitions),
        effective_definitions_if_all_added=len(definitions)+len(assets),
        production_limits=dict(used_cultures=605,effective_definitions=665,custom_resident_assets=300),
        deployment_ready=False)
    audit=dict(created=datetime.now().isoformat(timespec='seconds'),summary=summary,rows=rows,
        references={k:dict(title=v[0],url=v[1],scope=v[2]) for k,v in REFS.items()},
        inputs=dict(source_sha256=evidence['source_sha256'],source_ledger_sha256=sha(evidence_path),
            source_catalog_sha256=hashes,baseline_crosswalk_sha256=sha(crosswalk_path),
            inherited_audit_sha256=sha(prior_path),import_report_sha256=sha(import_path),
            installed_files_sha256=before,protected_files_sha256=files_before,
            rules_sha256=sha(Path(__file__).with_name('culture_1337_rules.py'))))
    write(out/'audit.json',audit)
    csvwrite(out/'all_cultures.csv',rows)
    csvwrite(out/'additional_1337.csv',[r for r in rows if r['new_in_1337']])
    write(out/'candidate_mapping.json',dict(schema=1,stage='review_only',source_date=evidence['source_date'],
        source_sha256=evidence['source_sha256'],unknown_source_policy='reject_for_review',
        inherited_1780_mappings_unchanged=True,mappings=mapping,
        limitations=['基础居民身份对应，不含迁移分支运行结果','不得直接导入生产配置','新资产和上限尚未通过']))
    write(out/'candidate_assets.json',dict(stage='incomplete_design_only',assets=assets,
        unresolved_fields=['language','names','graphics','homelands','historical_scope','asset_budget'],
        policy='模板仅提示共享传承，不复制整套资产；空语言表示未定，不是默认采用模板语言。'))
    csvwrite(out/'candidate_target_populations.csv',[dict(target_culture=k,centipersons=n) for k,n in sorted(targets.items())])
    # Independent readback of frozen files, not only in-memory counters.
    saved=read(out/'candidate_mapping.json')['mappings']
    replay=Counter()
    for pops in evidence['location_cultures'].values():
        for k,n in pops.items():
            if n:replay[saved[k]]+=n
    validation=dict(source_count=len(saved),missing=sorted(set(by_culture)-saved.keys()),
       extra=sorted(saved.keys()-set(by_culture)),inherited_changes=[k for k in old if saved[k]!=old[k]['target_culture']],
       population_reconciled=(sum(replay.values())==evidence['world_centipersons']),
       target_totals_reconciled=(replay==targets),
       installed_files_unchanged=(before==tree(mod)),protected_files_unchanged=(files_before==protected()),
       pending_asset_count=len(assets),deployment_ready=False)
    assert not validation['missing'] and not validation['extra'] and not validation['inherited_changes']
    assert all(validation[k] for k in ['population_reconciled','target_totals_reconciled','installed_files_unchanged','protected_files_unchanged'])
    write(out/'validation.json',validation)
    render(out,audit)
    print(json.dumps(dict(output=str(out),summary=summary,validation=validation),ensure_ascii=False,indent=2))

def render(out,audit):
    s=audit['summary']; by={r['source_culture']:r for r in audit['rows']}
    jewish=['ashkenazi','qayfengi','sephardi','italki','romanyoti','kalimi','gurji','kochini','beyte_yisrael','mizrahi','mustaarabi']
    report=f'''# 1337 文化清单与候选处理

源开局日期 {s['source_date']}，对照当前 {s['baseline_version']} 的1780文化框架。仅生成离线候选，没有实装。

1337 有 **{s['cultures_1337']}** 条正人口文化，1780 有 **{s['cultures_1780']}** 条。1337 多出的 **{s['additional_1337']}** 条已逐项列出；1780 的全部文化也都存在于1337。

“1780未检出”只表示这份战役存档没有该文化人口，不表示真实历史中该民族灭绝。阿什肯纳兹在1780仍有2.48人，不能判作消失。

## 整理结果

- 新增546条中，391条拟接入现有类别，2条在纠正源分组后接入现有类别，1条拟扩充原有约库茨封闭合称。
- 另152条暂保留独立身份，生成未完成资产设计。没有把这些候选直接写进生产规则。
- 原有1540条基础映射不变；其中 **{s['inherited_pending_rows']}** 条旧范围、历史及源标签问题继续保留，不伪装为已解决。
- 候选基础居民目标共 **{s['base_resident_targets']}** 类。若全部新增资产，有效定义将从{s['effective_definitions_before']}增到 **{s['effective_definitions_if_all_added']}**，超过现有665定义上限；基础居民目标本身也超过605使用上限。需要继续审定合理宽类和明确合称，不能直接全部实装。

## 犹太社群对照

人数取源存档人口账本，未做目标人口缩放。

|源文化|1337人数|1780人数|候选目标|
|---|---:|---:|---|
'''
    for k in jewish:
        if k in by:
            r=by[k]; report+=f"|{r['source_name']} `{k}`|{r['population_1337_centipersons']/100:,.2f}|{r['population_1780_centipersons']/100:,.2f}|{r['target_name']}|\n"
    report+='''
开封、意大利、罗曼尼奥特、波斯、格鲁吉亚和柯枝犹太社群分别保留候选身份。共用宗教不作为合并民族或统一语言的理由。地区文化只是共享传承的设计参考；既有犹太社群例外规则仍须逐项对照，不能直接套模板。1337的语言阶段、本土范围和姓名尚未全部核定。

## 原住民与源字段问题

- 澳洲新增182条延续原版澳洲原住民宽类别，同时保留每一来源、人数、语言及分布。现代原住民地图不直接当作1337国界。
- 源文件的13条“密克罗尼西亚”组实际对应瓦努阿图、新喀里多尼亚及洛亚蒂群岛，本轮拟按美拉尼西亚区域宽类整理。
- 布纳克、法塔卢库和托雷斯海峡岛民从源Papuan大组中单列；不能依源组名统一当作新几内亚民族。
- 泰诺、卢卡约、西瓜约、马科里什等保留来源区别。历史资料不足的语言亲缘明确留空，不生成确定族谱。

|源文化|需要处理的字段|候选说明|
|---|---|---|
'''
    for k,p in SPECIAL.items():
        if k in by:
            refs=' '.join(f'[{REFS[z][0]}]({REFS[z][1]})' for z in p.get('refs',[]))
            report+=f"|{by[k]['source_name']} `{k}`|{p.get('issue','语言及身份分别审定')}|{p.get('language','')} {refs}|\n"
    report+='''
## 通用转换应采用的规则

1. 先从实际存档建立文化全集，再查显式映射。不能只使用1780曾出现过的文化清单，也不能把未命中的文化自动塞进某个邻近民族。
2. 文化身份、语言、传承、宗教、本土分开处理。允许复用原版宽类和已审定的有限成员合称；共享传承不表示同一民族。原版宽类别的单一语言也是玩法抽象。
3. 未殖民地先取源地区实际主体文化，再执行文化映射，最后合并同一目标民族的相邻地块。地理归属参考只补地理证据；不能把参考地区的统治者、目标原版国家或整州文化强加给已有源人口。
4. 有殖民者占主导的地区，按源人口和政治事实判定，不因地块被标为白地而一律创建原住民部落。连片合并只决定国家组合，不搬动或替换已有POP文化。
5. 1337本土须按当时证据重建。社群存在于开封，不等于整州河南自动成为其本土。迁移分支重新按源文化和实际居住区域判断，不照搬1780的14条分支人口或后世迁徙。
6. 未识别来源进入待核清单，不静默回退。新增候选资产需核定语言、姓名、外观、历史范围及性能预算，然后才可进入完整转换验证。

## 文件与验证

- [可搜索全量清单](index.html)：支持文化名、源键、分组和处理说明检索。
- [全部文化CSV](all_cultures.csv) 与 [1337新增CSV](additional_1337.csv)。
- [冻结候选映射](candidate_mapping.json)：2086条显式基础居民对应；不是生产配置，也不包含迁移分支结果。
- [资产设计草案](candidate_assets.json)：152条未完成设计，未知字段不伪造。
- [独立回读验证](validation.json)：源人口总量394,540,033.77守恒，逐目标合计一致，既有映射、安装文件、正式配置及地点审核未改变。

本轮完成的是全量清单、映射风险筛查及新增候选处理。没有逐一证明2086个族名在1337的历史真实性，也未生成可启动的1337模组。所有自动类别选取都已冻结为明确源键；不会形成对未来未知文化的泛化兜底。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    payload=json.dumps(audit['rows'],ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>1337文化清单</title><style>body{font:15px/1.6 system-ui,"Microsoft YaHei";margin:28px;color:#21344a;background:#f7f9fc}h1{margin-bottom:4px}a{color:#1463a5}input,select{font:inherit;padding:8px;margin:8px}input{width:42%}table{border-collapse:collapse;background:white;width:100%}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{background:#dfe8f4}small{color:#56697b}.notice{padding:14px;background:#fff1d5}button{padding:7px;margin:8px}</style><h1>1337文化清单与候选处理</h1><p>2086条来源 · 相对1780新增546条 · 未实装</p><p class="notice">152条独立身份仍是未完成资产设计。语言、姓名、外观、本土及文化数量上限尚未全部通过，不能直接导入生产配置。</p><p><a href="README.md">审查说明</a> · <a href="additional_1337.csv">新增文化CSV</a> · <a href="candidate_mapping.json">候选映射</a></p><input id="q" placeholder="文化名、源键、语言、处理说明…"><select id="mode"><option value="new">仅1337新增</option><option value="all">全部文化</option><option value="pending">独立身份候选</option><option value="legacy">旧待核问题</option></select><span id="count"></span><p><button id="prev">上一页</button><button id="next">下一页</button></p><table><thead><tr><th>源文化</th><th>1337 / 1780人数</th><th>候选目标与状态</th><th>语言 / 传承</th><th>主要源地点</th><th>依据及待核说明</th></tr></thead><tbody id="body"></tbody></table><script>const rows=PAYLOAD;let page=0;const el=id=>document.getElementById(id);function show(){const q=el('q').value.toLowerCase(),mode=el('mode').value;const found=rows.filter(r=>(mode==='all'||mode==='new'&&r.new_in_1337||mode==='pending'&&r.decision==='preserve_identity_candidate'||mode==='legacy'&&['scope_design','historical_review','source_label_review'].includes(r.inherited_audit))&&JSON.stringify(r).toLowerCase().includes(q));page=Math.min(page,Math.max(0,Math.ceil(found.length/60)-1));el('body').replaceChildren();for(const r of found.slice(page*60,page*60+60)){const tr=document.createElement('tr');for(const v of [r.source_name+' ['+r.source_culture+']',(r.population_1337_centipersons/100).toLocaleString()+' / '+(r.population_1780_centipersons/100).toLocaleString(),r.target_name+' ['+r.target_culture+'] — '+r.decision_name+(r.inherited_audit?'；旧审查 '+r.inherited_audit:''),r.source_language+' → '+(r.language_candidate||'语言未定')+'；'+r.heritage_candidate,r.top_locations.map(l=>l.name+' '+(l.centipersons/100).toLocaleString()).join('；'),r.reason+' '+r.language_note]){const td=document.createElement('td');td.textContent=v;tr.append(td)}el('body').append(tr)}el('count').textContent=found.length+'条 / 第'+(page+1)+'页';el('prev').disabled=page===0;el('next').disabled=(page+1)*60>=found.length}el('q').oninput=el('mode').onchange=()=>{page=0;show()};el('prev').onclick=()=>{page--;show()};el('next').onclick=()=>{page++;show()};show()</script></html>'''.replace('PAYLOAD',payload)
    (out/'index.html').write_text(page,encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT)
    build(parser.parse_args().output)
