"""Read-only M5 heritage inventory and explicit, non-applied design proposal."""
from __future__ import annotations

import collections
import csv
import hashlib
import html
import json
from datetime import datetime
from pathlib import Path

from build_m2_prototype import objects
from build_m3_world import load_localization
from m3_world import fields
from package_m4_population_test import GAME, effective, parse_pops
from pdx_text import root

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'config/personal/m5_heritage_reuse_proposal.json'
INSTALL = ROOT / '.local/m5/installation-latest.json'
REVIEWS = ROOT / '.local/m4/location-workstation/location_reviews.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree(path):
    return {p.relative_to(path).as_posix(): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def main():
    protected = {str(p): sha(p) for p in (INSTALL, REVIEWS, POLICY)}
    installation = json.loads(INSTALL.read_text(encoding='utf-8-sig'))
    mod = Path(installation['target'])
    before = tree(mod)
    policy = json.loads(POLICY.read_text(encoding='utf-8'))
    history = json.loads((ROOT / 'config/personal/m5_historical_homelands.json').read_text(encoding='utf-8'))
    history_entries = {e['culture']: e for e in history['entries']}
    cultures = effective(mod, 'common/cultures')
    traits = effective(mod, 'common/discrimination_traits')
    native_cultures, native_traits = {}, {}
    for directory, target in [('common/cultures', native_cultures), ('common/discrimination_traits', native_traits)]:
        for path in sorted((GAME / directory).glob('*.txt')):
            for key, node in objects(root(path.read_text(encoding='utf-8-sig'))):
                target[key] = fields(node)
    names = load_localization(GAME / 'localization/simp_chinese')
    names.update(load_localization(mod / 'localization/simp_chinese'))
    # Religious traits also have type=heritage. Inventory only the fixed game's
    # cultural-heritage catalog, including cultural traits not used by any culture.
    cultural_heritage_keys = {key for key, _ in objects(root(
        (GAME / 'common/discrimination_traits/00_cultural_heritages.txt').read_text(encoding='utf-8-sig')))}
    native = {h: {'name': names.get(h, h), 'group': t['trait_group'],
                  'cultures': {c: names.get(c, c) for c, f in native_cultures.items() if f.get('heritage') == h}}
              for h, t in native_traits.items() if t.get('type') == 'heritage' and h in cultural_heritage_keys}
    population = collections.Counter()
    proposed_traits = policy.get('new_shared_heritages', {})
    valid_groups = {t['group'] for t in native.values()}
    for key, value in proposed_traits.items():
        assert key.startswith('eu5_shared_heritage_') and key not in traits
        assert value['type'] == 'heritage' and value['group'] in valid_groups
        assert value['basis'] and value['sources']
        names[key] = value['name']
    target_catalog = dict(native)
    target_catalog.update({k: dict(v, cultures={}) for k, v in proposed_traits.items()})
    pops = parse_pops(mod / 'common/history/pops/00_eu5_world.txt')
    for (_, _, culture, _), size in pops.items():
        population[culture] += size
    proposals = {}
    for group in policy['groups']:
        assert group['status'] in ('recommended', 'review')
        assert group['target'] in target_catalog, group['target']
        if group['target'] in native:
            assert traits[group['target']]['type'] == 'heritage'
            assert traits[group['target']]['trait_group'] == native[group['target']]['group']
        for culture in group['members']:
            assert culture in cultures and culture.startswith('eu5_'), culture
            assert culture not in proposals, culture
            proposals[culture] = group
    rows = []
    for culture, definition in cultures.items():
        if not culture.startswith('eu5_'):
            continue
        current = definition['heritage']
        group = proposals.get(culture)
        target = group['target'] if group else current
        status = group['status'] if group else ('already_native' if current in native else 'retain_pending')
        reason = group['basis'] if group else policy['retain_reasons'].get(culture,
            '本轮未找到足够明确的原版归属；暂保留，仍待专门研究，不代表必须永久独立。')
        if current in native and not group:
            reason = '已经共用原版传承，维持现状。'
        if culture in policy['retain_reasons'] and not group:
            status = 'retain_reasoned'
        if culture.removeprefix('eu5_resident_') in {'bantoid','benue','otomanguean_culture','gonga_culture','omo_culture','south_cushitic_culture','barbakoan_culture'}:
            reason += ' 源标签内部成员仍未完全厘清；大传承归属不等于身份或本土审核完成。'
        old_group = traits[current]['trait_group']
        new_group = target_catalog[target]['group'] if target in target_catalog else traits[target]['trait_group']
        group_change = old_group != new_group
        if status == 'recommended' and group_change:
            assert group.get('group_change_rationale'), culture
            reason += ' 大组变化说明：' + group['group_change_rationale']
        assert not group or target != current, culture
        historic = history_entries.get(culture, {})
        historical_context = [history['sources'][s] for s in historic.get('sources', [])]
        refs = [policy['sources'][s] for s in group.get('sources', [])] if group else []
        rows.append({'culture': culture, 'name': names.get(culture, culture), 'population': population[culture],
            'current': current, 'current_name': names.get(current, current), 'target': target,
            'target_name': names.get(target, target), 'current_group': old_group, 'target_group': new_group,
            'group_change': group_change, 'language_unchanged': definition['language'], 'status': status,
            'target_kind': 'new_shared' if target in proposed_traits else ('vanilla' if target in native else 'retained_custom'),
            'basis': reason, 'native_examples': native.get(target, {}).get('cultures', {}), 'sources': refs,
            'historical_context': historical_context, 'historical_core_context': historic.get('core', ''),
            'historical_context_limit': '原有本土考证仅提供历史地域与身份背景，不单独证明传承归并。',
            'full_historical_review_complete': False})
    rows.sort(key=lambda r: (list(LABELS).index(r['status']), -r['population'], r['culture']))
    assert len(rows) == sum(c.startswith('eu5_') for c in cultures)
    old = {r['current'] for r in rows if r['current'].startswith('eu5_')}
    after_recommended = {r['target'] if r['status'] == 'recommended' else r['current'] for r in rows}
    after_all = {r['target'] for r in rows}
    budget = policy.get('budget', {})
    assert len(proposed_traits) <= budget.get('max_new_shared_heritages', len(proposed_traits))
    assert sum(t.startswith('eu5_') for t in after_recommended) <= budget.get('max_remaining_active_custom_heritages', len(after_recommended))
    assert all(v['group'] in valid_groups for v in proposed_traits.values())
    if policy.get('schema', 1) >= 2:
        assert all(r['status'] != 'retain_pending' for r in rows), 'Every retained exception needs an explicit rationale.'
    stats = {'custom_cultures': len(rows), 'current_active_custom_heritage_traits': len(old),
        'status_counts': dict(collections.Counter(r['status'] for r in rows)),
        'active_custom_traits_if_recommended_applied': sum(t.startswith('eu5_') for t in after_recommended),
        'active_custom_traits_if_all_proposals_applied': sum(t.startswith('eu5_') for t in after_all),
        'recommended_population': sum(r['population'] for r in rows if r['status'] == 'recommended'),
        'effective_culture_definitions': len(cultures), 'used_pop_cultures': len(population),
        'pop_groups': len(pops), 'population': sum(population.values()),
        'cross_group_proposals': [r['culture'] for r in rows if r['group_change']],
        'recommended_cross_group_changes': sum(r['status'] == 'recommended' and r['group_change'] for r in rows),
        'proposed_new_shared_traits': len(proposed_traits),
        'recommended_vanilla_reuse': sum(r['status'] == 'recommended' and r['target_kind'] == 'vanilla' for r in rows),
        'recommended_new_shared_members': sum(r['status'] == 'recommended' and r['target_kind'] == 'new_shared' for r in rows),
        'defined_but_unused_vanilla_heritages': [k for k, v in native.items() if not v['cultures']],
        'applied_changes': 0}
    out = ROOT / '.local/m5/heritage-reuse' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    report = {'status': 'review_proposal_not_applied', 'baseline': installation, 'stats': stats,
        'policy': policy, 'native_heritages': native, 'rows': rows,
        'installed_manifest_sha256': before,
        'fixed_game_inputs': {str(p): sha(p) for d in ['common/cultures', 'common/discrimination_traits']
                              for p in sorted((GAME / d).glob('*.txt'))}}
    (out / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'policy.snapshot.json').write_bytes(POLICY.read_bytes())
    with (out / 'cultures.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        columns = ['culture','name','population','status','current','current_name','target','target_name','target_kind',
                   'current_group','target_group','group_change','language_unchanged','basis']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    render(out, report)
    assert before == tree(mod), 'Installed mod changed during read-only audit; rerun against fresh baseline.'
    assert protected == {str(p): sha(p) for p in (INSTALL, REVIEWS, POLICY)}, 'Protected input changed.'
    validation = {'passed': True, 'installed_files_byte_identical': len(before), 'installation_pointer_unchanged': True,
        'user_reviews_unchanged': True, 'vanilla_targets_exist_in_fixed_game': True,
        'new_shared_traits_have_valid_existing_groups': len(proposed_traits),
        'all_cross_group_changes_have_explicit_rationale': True, 'complete_custom_culture_inventory': len(rows),
        'explicit_retained_exceptions': sum(r['status'] == 'retain_reasoned' for r in rows),
        'design_budgets_passed': True,
        'duplicate_proposal_members': 0, 'all_proposals_are_unapplied': True,
        'stats': stats, 'report_sha256': sha(out / 'audit.json')}
    (out / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / '.local/m5/heritage-reuse-latest.json').write_text(json.dumps({'report': str(out), 'stats': stats},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(out), 'validation': validation}, ensure_ascii=True))


LABELS = {'recommended': '建议整合', 'review': '候选待核对', 'retain_reasoned': '有理由保留',
          'retain_pending': '暂保留／未定', 'already_native': '已用原版'}


def render(out, report):
    e = lambda value: html.escape(str(value), quote=True)
    stats = report['stats']
    table = []
    for row in report['rows']:
        sources = ''.join(f'<li><a href="{e(s["url"])}" target="_blank" rel="noreferrer">{e(s.get("title", s.get("finding", s["url"])))}</a></li>'
                          for s in row['sources'] + row['historical_context'])
        table.append(f'<tr data-status="{row["status"]}" data-groupchange="{int(row["group_change"])}">'
            f'<td><b>{e(row["name"])}</b><small>{e(row["culture"])}</small></td><td>{row["population"]:,}</td>'
            f'<td><span class="tag {row["status"]}">{LABELS[row["status"]]}</span></td>'
            f'<td>{e(row["current_name"])}<small>{e(row["current"])}</small></td>'
            f'<td><b>{e(row["target_name"])}</b><small>{e(row["target"])}</small>'
            f'<small>{"新增共享大传承" if row["target_kind"] == "new_shared" else "原版示例：" + e("、".join(row["native_examples"].values()) or "无")}</small></td>'
            f'<td>{"⚠ 大组将变更" if row["group_change"] else "大组不变"}<small>{e(row["current_group"])} → {e(row["target_group"])}</small></td>'
            f'<td>{e(row["basis"])}<details><summary>资料与原有考证背景</summary><p>{e(row["historical_core_context"])}</p>'
            f'<p>{e(row["historical_context_limit"])}</p><ul>{sources or "<li>本项主要依据本机原版类别和游戏设计；未声称新增历史证据。</li>"}</ul></details></td></tr>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M5 · 原版传承复用审查</title><style>
body{margin:0;background:#f5f3ed;color:#203036;font:15px/1.6 system-ui,"Microsoft YaHei",sans-serif}header,main{padding:26px 3vw}header{background:#153c3d;color:#f4f1e7}h1{margin:0;font-size:30px}p{max-width:1250px}.stats{display:flex;flex-wrap:wrap;gap:16px}.card{background:#ffffff14;border:1px solid #ffffff30;padding:12px 22px;border-radius:8px}.card strong{display:block;font-size:28px}nav{position:sticky;top:0;padding:12px;background:#f5f3ed;border-bottom:1px solid #c5ceca;display:flex;gap:12px;align-items:center;z-index:2;flex-wrap:wrap}input,select{padding:10px;font:inherit;border:1px solid #b8c5bf;border-radius:5px}input[type=search]{width:min(420px,80vw)}.scroll{overflow:auto}table{border-collapse:collapse;min-width:1400px;width:100%;background:white}th,td{padding:13px;text-align:left;vertical-align:top;border-bottom:1px solid #dce4de}th{background:#dfe8e0}td:nth-child(7){min-width:340px}small{display:block;font-size:11px;color:#607574;overflow-wrap:anywhere;max-width:210px}.tag{display:inline-block;white-space:nowrap;border-radius:20px;padding:3px 9px;background:#e9e9e9}.recommended{background:#d0e8dc}.review{background:#fae6bb}.already_native{background:#dce8ef}details{font-size:13px;margin-top:10px}a{color:#207677}summary{cursor:pointer}footer{padding:30px;color:#516564}li{margin:6px 0}</style>
<header><h1>文化可以独立，传承可以共用</h1><p>原版传承复用审查 · BASELINE · 仅提案，未改游戏设定</p>
<div class="stats">CARDS</div><p>保留文化键、语言、人口、宗教及本土。建议项是符合原版粒度的游戏设计，不是把多个民族认定为同一民族，也不等于全部历史审核完成。降低传承碎片会改变文化接纳与整合关系；文化数量和POP分组不减少，尚无运行速度提升的实测结论。</p></header>
<main><p><b>按原版尺度整合：</b>泰传承采用壮侗文化圈，苗传承采用苗瑶相关圈；伊朗、刚果、几内亚、东部高地等按原版已有的跨语言、跨民族范围设计。原先模板的大组不是否决条件，变更必须明确列出。文化区是游戏接纳设计，不是血缘、语言或领土分类。</p><p>DESIGN_SUMMARY</p>SHARED_TABLE
<p>EXCEPTIONS</p><p><a href="cultures.csv">下载全表 CSV</a> · <a href="audit.json">完整依据与固定版本快照</a> · <a href="validation.json">只读验证</a></p>
<nav><input id="q" type="search" placeholder="搜索文化、传承、依据或游戏键"><select id="status"><option value="">全部状态</option>OPTIONS</select><label><input id="cross" type="checkbox">仅大组变更</label><span id="count"></span></nav>
<div class="scroll"><table><thead><tr><th>文化（保留）</th><th>当前人口</th><th>处理状态</th><th>当前传承</th><th>提议传承及原版例子</th><th>接纳大组影响</th><th>理由与资料</th></tr></thead><tbody id="culture-rows">ROWS</tbody></table></div></main>
<footer>统计是本机安装版本的静态回读。传承数指这些自定义文化引用的不同自定义传承键；不是传承大组数，也不是文件中全部定义数。未定项只是本轮保留，不是永久排除。</footer>
<script>const rows=[...document.querySelectorAll('#culture-rows tr')],q=document.querySelector('#q'),status=document.querySelector('#status'),cross=document.querySelector('#cross');function filter(){const needle=q.value.toLowerCase();let n=0;for(const row of rows){const show=(!status.value||row.dataset.status===status.value)&&(!cross.checked||row.dataset.groupchange==='1')&&row.textContent.toLowerCase().includes(needle);row.hidden=!show;if(show)n++}document.querySelector('#count').textContent=`显示 ${n} / ${rows.length} 种文化`}q.addEventListener('input',filter);status.addEventListener('change',filter);cross.addEventListener('change',filter);filter();</script></html>'''
    cards = [('自定义文化', stats['custom_cultures']), ('当前自定义传承', stats['current_active_custom_heritage_traits']),
             ('建议整合的文化', stats['status_counts'].get('recommended', 0)),
             ('仅采纳建议后／自定义传承', stats['active_custom_traits_if_recommended_applied']),
             ('新增共享大传承', stats['proposed_new_shared_traits'])]
    shared_table = '<h2>少量新增共享传承</h2><table style="min-width:0"><tr><th>传承</th><th>文化数</th><th>成员</th></tr>'
    for key, definition in report['policy'].get('new_shared_heritages', {}).items():
        members = [r['name'] for r in report['rows'] if r['target'] == key]
        shared_table += f'<tr><td>{e(definition["name"])}</td><td>{len(members)}</td><td>{e("、".join(members))}</td></tr>'
    shared_table += '</table>'
    replacements = {'BASELINE': e(report['baseline']['version']),
        'DESIGN_SUMMARY': f'建议{stats["recommended_vanilla_reuse"]}种文化复用原版传承；{stats["recommended_new_shared_members"]}种进入{stats["proposed_new_shared_traits"]}个新增共享传承。保留少量有具体理由的例外。逐行保留游戏键、目标、原版示例及大组变化说明。',
        'SHARED_TABLE': shared_table,
        'CARDS': ''.join(f'<div class="card">{e(label)}<strong>{value}</strong></div>' for label, value in cards),
        'EXCEPTIONS': e(report['policy']['native_exceptions']),
        'OPTIONS': ''.join(f'<option value="{k}">{v}</option>' for k, v in LABELS.items()), 'ROWS': ''.join(table)}
    for key, value in replacements.items():
        page = page.replace(key, value)
    (out / 'index.html').write_text(page, encoding='utf-8')


if __name__ == '__main__':
    main()
