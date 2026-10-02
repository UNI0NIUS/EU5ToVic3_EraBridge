"""Audit every active source culture against the installed M5; never edit game data.

Run normally to create an immutable local report, or --verify DIR for readback.
This inventories identity mapping, not complete historical validation of assets.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
import shutil

from build_m2_prototype import objects, strings
from build_m3_world import load_localization
from m3_world import fields
from package_m4_population_test import GAME, effective, parse_pops
from pdx_text import root
from m5_identity_audit_rules import SOURCES, LABELS, FINDINGS, BROAD, COMPOSITES, SOURCE_BROAD

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / '.local/m5/installation-latest.json'
EU5 = Path('D:/Steam/steamapps/common/Europa Universalis V/game')
FLAGS = {'identity_mismatch', 'scope_design', 'historical_review'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def csvrows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def csvwrite(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        out = csv.DictWriter(f, fieldnames=list(rows[0]))
        out.writeheader()
        for row in rows:
            out.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                          for k, v in row.items()})


def source_catalog():
    catalog, hashes = {}, {}
    for p in sorted((EU5 / 'in_game/common/cultures').glob('*.txt')):
        hashes[str(p)] = sha(p)
        for key, obj in objects(root(p.read_text(encoding='utf-8-sig'))):
            f = fields(obj)
            catalog[key] = {'language': f.get('language', ''),
                            'groups': list(strings(f['culture_groups'])) if 'culture_groups' in f else [],
                            'file': str(p)}
    return catalog, hashes


def render(out, audit):
    esc = lambda x: html.escape(str(x))
    counts = audit['summary']
    cards = ''.join(f'<div><b>{n:,}</b><span>{esc(LABELS[k])}</span></div>'
                    for k, n in counts['classification_counts'].items())
    rows = []
    for finding in audit['findings']:
        country_text = '、'.join(x['name'] + ' (' + x['tag'] + ')' for x in finding['primary_countries']) or '无直接主流文化命中'
        links = ' '.join(f'<a href="{esc(SOURCES[s][1])}" target="_blank" rel="noopener">{esc(SOURCES[s][0])}</a>' for s in finding['sources']) or '本机定义／映射风险筛查；尚无逐项外部定论'
        rows.append('<tr>' + ''.join(f'<td>{x}</td>' for x in [esc(LABELS[finding['status']]),
            esc('、'.join(finding['member_names']) + ' → ' + finding['target_name']),
            f"{finding['source_centipersons']/100:,.2f}", esc(country_text),
            esc(finding['reason']), esc(finding['proposal']), links]) + '</tr>')
    refs = ''.join(f'<li><a href="{esc(v[1])}">{esc(v[0])}</a>：{esc(v[2])}</li>' for v in SOURCES.values())
    options = ''.join(f'<option value="{k}">{esc(v)}</option>' for k, v in LABELS.items())
    payload = json.dumps(audit['rows'], ensure_ascii=False).replace('<', '\\u003c')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 文化身份全量排查</title>
<style>body{font:15px/1.65 system-ui,"Microsoft Yahei",sans-serif;background:#f4f6f9;color:#192534;margin:0}main{max-width:1600px;margin:auto;padding:32px}h1{font-size:30px}h2{margin-top:36px}.note{background:#fff2d8;border-left:5px solid #bf831d;padding:16px}.cards{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}.cards div{background:white;border:1px solid #d6dde6;border-radius:8px;padding:14px;min-width:145px}.cards b{display:block;font-size:28px}.cards span{color:#586778}table{border-collapse:collapse;width:100%;background:white}td,th{padding:11px;text-align:left;vertical-align:top;border:1px solid #dae0e8}th{background:#e7edf4;position:sticky;top:0}a{color:#165eab}input,select,button{font:inherit;padding:8px;border:1px solid #bbc8d6;border-radius:5px}input{width:38%}.scroll{overflow:auto}small{color:#59697a}code{font-size:12px;overflow-wrap:anywhere}.toolbar{display:flex;gap:12px;flex-wrap:wrap;margin:15px 0}.num{white-space:nowrap}</style><main>
<h1>M5 文化身份全量排查</h1>'''
    page += f'<p>基线 <b>{esc(audit["installation"]["version"])}</b> · {esc(audit["created"])} · 仅审计，未改映射、游戏安装或地点审核。</p>'
    page += f'<p>检查全部 <b>{counts["source_cultures"]:,}</b> 条源文化、<b>{counts["converted_countries"]}</b> 个转换国家，并回读 <b>{counts["installed_pop_groups"]:,}</b> 个实际人口组。当前使用 <b>{counts["installed_used_cultures"]}</b> 类文化。</p>'
    page += '<div class="note"><b>共用传承不等于替换民族。</b> 保留原版宽类别和已批准的封闭合称；重点找出把宽身份变成特定分支、跨民族替换、年代错置和未经证实的语族归属。“未发现”只指本轮映射筛查，不代表语言、姓名、外观、本土全部历史审核通过。代码中的 reviewed_alias 也不是历史审核证书。</div>'
    page += f'<div class="cards">{cards}</div>'
    page += '<p><a href="all_source_mappings.csv">全部源映射 CSV</a> · <a href="findings.csv">问题批次 CSV</a> · <a href="countries.csv">全部国家主流映射</a> · <a href="target_cultures.csv">全部有效文化资产与实际人口</a> · <a href="inactive_aliases.json">未命中的旧配置别名</a> · <a href="validation.json">独立验证</a></p>'
    page += '<h2>需要处理的批次</h2><p>按明确问题优先、同级源人口降序排列。人数为校准前源存档人数，不是当前游戏中的精确受影响人数；共享目标还包含其他来源，不能将整个目标人口都归给某个错误来源。外部资料只支持表中所述区别，不直接证明1780年边界。</p><div class="scroll"><table><thead><tr><th>判定</th><th>源身份 → 当前目标</th><th>源人数</th><th>直接涉及主流文化的国家</th><th>原因</th><th>建议</th><th>依据</th></tr></thead><tbody>'
    page += ''.join(rows) + '</tbody></table></div>'
    page += '<h2>全部源文化检索</h2><p>默认每页100项。可按国家、源键、文化名、目标、问题搜索。当前目标总人数仅供观察目标规模，跨源行不可相加。</p><div class="toolbar"><input id="q" placeholder="搜索瓦剌／高昌／romansh…" aria-label="搜索"><select id="status" aria-label="分类"><option value="all">全部分类</option>' + options + '</select><button id="prev">上一页</button><button id="next">下一页</button><span id="count"></span></div><div class="scroll"><table><thead><tr><th>源文化</th><th>目标文化</th><th>判定</th><th>源人数</th><th>当前目标总人数</th><th>国家主流</th><th>依据／设计说明</th></tr></thead><tbody id="body"></tbody></table></div>'
    page += '<h2>处理边界与实施顺序</h2><ol><li>先修明确错配，优先有政治主流或人口较大的条目。政治与居民映射须同步，避免只改名称掩盖错配。</li><li>名称过窄的集合先考虑合理宽称或封闭合称；保持现有大传承，不恢复上千种资产。</li><li>安第斯、非洲和古代考古标签的待核项，先确认成员与年代，再做少量拆分；不能把待核当作全部错误。</li><li>迁移人口保留已批准的来源＋地区规则。修改文化键时须同步人口、识字率选择器、主流文化、颜色及本土，并在最新包上独立回读。</li></ol>'
    page += '<h2>资料与限制</h2><ul>' + refs + '</ul><p>当前审计没有修改任何安装文件；现代目录只反证某些名称并非同义，不以现代官方民族表直接重建1780。7条原本含糊的源标签另列待核。原版宽类别的单一语言资产也不代表其全部居民历史上只说一种语言。</p></main>'
    page += '<script>const rows=' + payload + ';let page=0;const labels=' + json.dumps(LABELS, ensure_ascii=False) + ''';const q=document.getElementById('q'),st=document.getElementById('status');function show(){const needle=q.value.trim().toLowerCase(),found=rows.filter(r=>(st.value==='all'||r.status===st.value)&&JSON.stringify(r).toLowerCase().includes(needle));page=Math.min(page,Math.max(0,Math.ceil(found.length/100)-1));const body=document.getElementById('body');body.replaceChildren();for(const r of found.slice(page*100,page*100+100)){const tr=document.createElement('tr');const values=[r.source_name+' ['+r.source_culture+']',r.target_name+' ['+r.target_culture+']',labels[r.status],(r.source_centipersons/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}),r.current_target_population.toLocaleString(),r.primary_countries.map(c=>c.name+' ('+c.tag+')').join('、')||'—',r.reason];for(const v of values){const td=document.createElement('td');td.textContent=v;tr.append(td)}body.append(tr)}document.getElementById('count').textContent=found.length+'项，第'+(page+1)+'页';document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=(page+1)*100>=found.length}q.oninput=st.onchange=()=>{page=0;show()};document.getElementById('prev').onclick=()=>{page--;show()};document.getElementById('next').onclick=()=>{page++;show()};show();</script>'''
    (out / 'index.html').write_text(page, encoding='utf-8')


def build():
    install = read(INSTALL)
    package = Path(install['package'])
    from package_m5_uncolonized import inherited_report
    report = inherited_report(package)
    demo = Path(report['demographic_run'])
    political = Path(report['political_run'])
    mod = Path(install['target'])
    protected_paths = [INSTALL, ROOT / '.local/economy/installation-latest.json',
        ROOT / '.local/m4/location-workstation/location_reviews.json',
        ROOT / 'config/personal/m3_world.json', ROOT / 'config/personal/m5_culture_refinement.json']
    protected = {str(p): sha(p) for p in protected_paths}
    before = tree(mod)
    assert before == {k.replace('\\', '/'): v for k, v in report['output_sha256'].items()}, 'Installed package drift'
    raw = csvrows(demo / 'demographics/resident_culture_crosswalk.csv')
    mapping = {x['source_culture']: x for x in raw}
    assert len(mapping) == len(raw), 'Duplicate source identity'
    definitions = effective(mod, 'common/cultures')
    countries_def = effective(mod, 'common/country_definitions')
    pops = parse_pops(mod / 'common/history/pops/00_eu5_world.txt')
    population = Counter()
    for (_, _, c, _), n in pops.items():
        population[c] += n
    names = load_localization(GAME / 'localization/simp_chinese')
    for d in [mod / 'localization/simp_chinese', mod / 'localization/replace/simp_chinese']:
        names.update(load_localization(d))
    source, source_hashes = source_catalog()
    group_map, corrected, framework_rows = {}, {}, {}
    demo_report = read(demo / 'demographics/demographics_report.json')
    framework = {}
    if demo_report.get('framework_overrides'):
        framework = read(Path(demo_report['identity_correction_policy']))
        assert framework['mappings'] == demo_report['framework_overrides']
    correction_path = ROOT / 'config/personal/m5_culture_identity_corrections.json'
    corrections = read(correction_path)['mappings'] if correction_path.exists() else {}
    for g in FINDINGS:
        assert all(ref in SOURCES for ref in g['sources'])
        for s in g['members']:
            assert s not in group_map, ('Duplicate finding', s)
            if g['id'] in framework.get('decisions', {}):
                decision = framework['decisions'][g['id']]
                assert mapping[s]['target_culture'] == framework['mappings'].get(s,g['target']), ('Framework drift',s)
                framework_rows[s] = decision
                if decision['evidence_status'] == 'historical_boundary_unresolved':
                    group_map[s] = dict(g, status='historical_review', reason=decision['decision'],
                                        proposal='保留已实施的有限设计；历史边界未决，不能标为全部历史审核通过。')
                continue
            if (s in mapping and mapping[s]['method'] == 'm5_explicit_identity_correction'
                    and mapping[s]['target_culture'] == corrections.get(s)):
                corrected[s] = g
                continue
            assert s in mapping and mapping[s]['target_culture'] == g['target'], ('Stale finding', s)
            group_map[s] = g
    demo_report = read(demo / 'demographics/demographics_report.json')
    migrants = demo_report['migrant_cultures']['cultures']
    countries = read(political / 'conversion_report.json')['countries']
    country_rows, by_source = [], defaultdict(list)
    for tag, c in countries.items():
        actual = list(strings(countries_def[tag]['cultures']))
        assert actual == c.get('cultures', [c['culture']]), ('Political readback mismatch', tag)
        s = c.get('source_culture')
        if s:
            assert s in mapping
        authorized_migrant = any(m['source'] == s and m['target'] == c['culture']
                                and c.get('capital') in m['states'] for m in migrants)
        row = {'tag': tag, 'name': c.get('name_simp_chinese', names.get(tag, tag)),
               'source_culture': s, 'reported_culture': c['culture'], 'installed_cultures': actual,
               'resident_base_target': mapping[s]['target_culture'] if s else None,
               'political_resident_agree': c['culture'] == mapping[s]['target_culture'] if s else None,
               'authorized_migrant_region_match': authorized_migrant,
               'finding': group_map[s]['id'] if s in group_map else None,
               'status': group_map[s]['status'] if s in group_map else ('no_flag' if s else 'template_fallback')}
        country_rows.append(row)
        if s:
            by_source[s].append({'tag': tag, 'name': row['name'], 'installed_cultures': actual})
    target_sources = defaultdict(list)
    for r in raw:
        target_sources[r['target_culture']].append(r['source_culture'])
    rows = []
    for r in raw:
        s, t = r['source_culture'], r['target_culture']
        assert t in definitions and s in source, (s, t)
        g = group_map.get(s)
        if s in framework_rows:
            decision = framework_rows[s]
            status = 'historical_review' if decision['evidence_status'] == 'historical_boundary_unresolved' else 'framework_decided'
            reason, proposal = decision['decision'], '按已冻结框架复核；历史限制与姓名外观模板状态仍保留。'
        elif s in corrected:
            status, reason, proposal = 'corrected_identity', '已按明确政策修复原映射：' + corrected[s]['reason'], '保留修复；模板姓名、外观及个别历史本土仍按修复报告说明。'
        elif g:
            status, reason, proposal = g['status'], g['reason'], g['proposal']
        elif s in SOURCE_BROAD:
            status, reason, proposal = 'source_label_review', '源标签本身范围宽；保留该源身份，不冒称已厘清内部成员。', '继续核定原标签，不扩为新的兜底。'
        elif framework and t == 'eu5_chokwe':
            assert set(target_sources[t]) == {'chokwe','mbunda','luvale','luchazi_culture'}
            status, reason, proposal = 'approved_composite', '乔奎、姆本达、卢瓦莱、卢查齐四成员封闭合称；共享传统属于有限游戏聚合。', '维持冻结成员清单，不扩作邻近民族兜底。'
        elif t in COMPOSITES:
            status, reason, proposal = 'approved_composite', '沿用已批准、成员封闭且已采用合称的有限合并；不重新膨胀。', '维持既有合称。'
        elif t.startswith('eu5_'):
            assert t in ('eu5_' + s, 'eu5_resident_' + s) and len(target_sources[t]) == 1, ('Unexpected custom identity', s, t)
            status, reason, proposal = 'source_preserved', '输出一对一保留源身份；本轮未检测身份替换，资产历史真实性仍属另一审核层。', '保留身份与既有大传承。'
        elif t in BROAD:
            status, reason, proposal = 'vanilla_broad', '按已授权粒度沿用原版宽泛文化；不是声称所有成员民族或语言相同。显式边界疑点已另列。', '保留原版大类。'
        else:
            status, reason, proposal = 'no_flag', '已列入全量对照，本轮未发现同类身份替换风险；不能等同于完整历史审核通过。', '暂保留；后续证据可重开。'
        rows.append({'source_culture': s, 'source_name': r['name'], 'target_culture': t,
            'target_name': names.get(t, t), 'status': status, 'finding': g['id'] if g else None,
            'source_centipersons': int(r['centipersons']), 'current_target_population': population[t],
            'primary_countries': by_source[s], 'method': r['method'], 'original_reason': r['reason'],
            'source_language': source[s]['language'], 'source_groups': source[s]['groups'],
            'source_definition': source[s]['file'], 'target_language': definitions[t]['language'],
            'target_heritage': definitions[t]['heritage'], 'reason': reason, 'proposal': proposal,
            'sources': g['sources'] if g else []})
    row_map = {r['source_culture']: r for r in rows}
    findings = []
    for g in FINDINGS:
        if all(s in framework_rows for s in g['members']):
            if not any(s in group_map for s in g['members']):
                continue
            members=[row_map[s] for s in g['members']]
            findings.append(dict(group_map[next(s for s in g['members'] if s in group_map)],
                target_name=' / '.join(sorted({r['target_name'] for r in members})),
                member_names=[r['source_name'] for r in members],
                source_centipersons=sum(r['source_centipersons'] for r in members),
                primary_countries=[c for r in members for c in r['primary_countries']]))
            continue
        if all(s in corrected for s in g['members']):
            continue
        assert not any(s in corrected for s in g['members']), 'Partially corrected group requires an explicit audit split'
        members = [row_map[s] for s in g['members']]
        findings.append(dict(g, target_name=names.get(g['target'], g['target']),
            member_names=[r['source_name'] for r in members],
            source_centipersons=sum(r['source_centipersons'] for r in members),
            primary_countries=[c for r in members for c in r['primary_countries']]))
    order = {'identity_mismatch': 0, 'scope_design': 1, 'historical_review': 2}
    findings.sort(key=lambda g: (order[g['status']], -g['source_centipersons']))
    assert all(x['target'] in definitions for x in migrants)
    migrant_rows = [dict(source=x['source'], target=x['target'], name=names.get(x['target'], x['target']),
                         region=x['region'], population=population[x['target']],
                         status='authorized_origin_and_region_design') for x in migrants]
    all_targets = [{'culture': c, 'name': names.get(c, c), 'population': population[c],
                    'source_members': target_sources.get(c, []), 'language': f.get('language'), 'heritage': f.get('heritage'),
                    'migrant': any(m['target'] == c for m in migrant_rows)} for c, f in sorted(definitions.items())]
    profile = read(ROOT / 'config/personal/m3_world.json')
    inactive = [{'source': s, 'target': t, 'status': 'inactive_in_current_residents_and_countries',
                 'note': '旧键未命中当前存档；需要维护但不计入本次受影响人口。'}
                for s, t in profile['culture_aliases'].items() if s not in mapping]
    counts = Counter(r['status'] for r in rows)
    summary = dict(source_cultures=len(rows), source_centipersons=sum(r['source_centipersons'] for r in rows),
        resident_base_targets=len(target_sources), effective_definitions=len(definitions),
        converted_countries=len(country_rows), source_backed_countries=sum(bool(r['source_culture']) for r in country_rows),
        installed_pop_groups=len(pops), installed_population=sum(pops.values()), installed_used_cultures=len(population),
        classification_counts=dict(counts), finding_groups=len(findings),
        finding_group_counts=dict(Counter(g['status'] for g in findings)),
        flagged_source_centipersons=sum(r['source_centipersons'] for r in rows if r['status'] in FLAGS),
        clear_mismatch_source_centipersons=sum(r['source_centipersons'] for r in rows if r['status'] == 'identity_mismatch'),
        flagged_primary_countries=sum(r['status'] in FLAGS for r in country_rows),
        clear_mismatch_primary_countries=sum(r['status'] == 'identity_mismatch' for r in country_rows),
        political_resident_disagreements=[r for r in country_rows if r['political_resident_agree'] is False
                                         and not r['authorized_migrant_region_match']],
        authorized_migrant_primary_countries=sum(r['authorized_migrant_region_match'] for r in country_rows),
        migrant_cultures=len(migrant_rows), inactive_political_aliases=len(inactive))
    out = ROOT / '.local/m5/culture-identity-audit' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    for src, dest in [(demo / 'demographics/resident_culture_crosswalk.csv', 'source_crosswalk.snapshot.csv'),
                       (political / 'conversion_report.json', 'political.snapshot.json'),
                       (package / 'package_report.json', 'package.snapshot.json')]:
        shutil.copy2(src, out / dest)
    frozen = {str(p): sha(p) for p in [Path(__file__), ROOT / 'tools/m5_identity_audit_rules.py',
               demo / 'demographics/resident_culture_crosswalk.csv', political / 'conversion_report.json', package / 'package_report.json']}
    audit = dict(schema=1, status='audit_only_not_applied', created=datetime.now().isoformat(), installation=install,
        summary=summary, rows=rows, findings=findings, countries=country_rows, migrants=migrant_rows,
        sources={k: dict(title=v[0], url=v[1], supports=v[2], accessed='2026-10-02') for k, v in SOURCES.items()},
        protected_sha256=protected, installed_sha256=before, input_sha256=frozen,
        eu5_definitions_sha256=source_hashes,
        limitations=['全量覆盖是映射风险筛查，不等于1540种文化全部历史考证完成。',
                    '源人数为校准前值；当前目标人数包含其他来源，不可跨源重复累计。',
                    '待核类不等于已证错配；同传承和合理原版大类不被自动判错。',
                    '外部语言资料不单独证明1780民族边界；设定与安装完全未改。'])
    write(out / 'audit.json', audit)
    csvwrite(out / 'all_source_mappings.csv', rows)
    csvwrite(out / 'findings.csv', findings)
    csvwrite(out / 'countries.csv', country_rows)
    csvwrite(out / 'target_cultures.csv', all_targets)
    csvwrite(out / 'migrant_cultures.csv', migrant_rows)
    write(out / 'inactive_aliases.json', inactive)
    render(out, audit)
    assert tree(mod) == before, 'Installed files changed during audit'
    assert all(sha(Path(p)) == h for p, h in protected.items()), 'Protected input changed during audit'
    validation = verify(out)
    write(ROOT / '.local/m5/culture-identity-audit-latest.json',
          {'run': str(out), 'report': str(out / 'index.html'), 'status': validation['status'], 'summary': summary})
    print(json.dumps({'run': str(out), 'summary': summary, 'validation': validation['status']}, ensure_ascii=False, indent=2))


def verify(out):
    """Re-read the emitted tables, frozen mapping, installed POPs and definitions."""
    audit = read(out / 'audit.json')
    rows = csvrows(out / 'all_source_mappings.csv')
    original = csvrows(out / 'source_crosswalk.snapshot.csv')
    a = {r['source_culture']: (r['target_culture'], int(r['source_centipersons'])) for r in rows}
    b = {r['source_culture']: (r['target_culture'], int(r['centipersons'])) for r in original}
    assert len(a) == len(rows) == len(b) == len(original) and a == b, 'Coverage or population failure'
    assert all(r['status'] in LABELS for r in rows), 'Unknown classification'
    counts = dict(Counter(r['status'] for r in rows))
    assert counts == audit['summary']['classification_counts']
    assert len({r['target_culture'] for r in rows}) == audit['summary']['resident_base_targets']
    mod = Path(audit['installation']['target'])
    assert tree(mod) == audit['installed_sha256'], 'Installed tree drift'
    for p, h in audit['protected_sha256'].items():
        assert sha(Path(p)) == h, ('Protected file changed', p)
    pops = parse_pops(mod / 'common/history/pops/00_eu5_world.txt')
    totals = Counter()
    for (_, _, c, _), n in pops.items():
        totals[c] += n
    assert sum(pops.values()) == audit['summary']['installed_population']
    assert all(int(r['current_target_population']) == totals[r['target_culture']] for r in rows)
    definitions = effective(mod, 'common/cultures')
    target_rows = csvrows(out / 'target_cultures.csv')
    assert {r['culture'] for r in target_rows} == set(definitions)
    assert sum(int(r['population']) for r in target_rows) == sum(pops.values())
    assert all(c in definitions for c in totals), 'Undefined output culture'
    cs = read(out / 'political.snapshot.json')['countries']
    country_rows = csvrows(out / 'countries.csv')
    assert len(cs) == len(country_rows) and set(cs) == {r['tag'] for r in country_rows}
    actual_countries = effective(mod, 'common/country_definitions')
    for r in country_rows:
        assert json.loads(r['installed_cultures']) == list(strings(actual_countries[r['tag']]['cultures']))
    groups = csvrows(out / 'findings.csv')
    grouped = [s for g in groups for s in json.loads(g['members'])]
    expected = {r['source_culture'] for r in rows if r['status'] in FLAGS}
    assert len(grouped) == len(set(grouped)) and set(grouped) == expected
    assert sum(int(g['source_centipersons']) for g in groups) == sum(int(r['source_centipersons']) for r in rows if r['status'] in FLAGS)
    result = {'status': 'passed', 'scope': 'mapping_audit_readback_not_historical_certification',
              'source_rows_checked': len(rows), 'country_rows_checked': len(cs),
              'source_centipersons': sum(v[1] for v in a.values()),
              'installed_population': sum(pops.values()), 'installed_pop_groups': len(pops),
              'installed_files_unchanged': len(audit['installed_sha256']),
              'reviews_and_configuration_unchanged': True, 'all_source_rows_accounted_exactly_once': True,
              'all_effective_cultures_in_target_inventory': True,
              'finding_groups_disjoint_and_complete': True, 'audit_sha256': sha(out / 'audit.json')}
    write(out / 'validation.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify), ensure_ascii=False, indent=2))
    else:
        build()
