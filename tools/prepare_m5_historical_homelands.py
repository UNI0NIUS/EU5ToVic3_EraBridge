"""Build an additive, uninstalled historical-core candidate from installed M5.

The research configuration is curated: source population and language proximity
never choose homelands. The current installed package supplies every other file.
"""
import argparse
import csv
import html
import json
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from build_m2_prototype import objects, patch, replace_body
from pdx_text import root
from m3_world import digest
from package_m5_culture_refinement import read, write, files, homeland_pairs, STATE

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'config/personal/m5_historical_homelands.json'


def demographic_provenance(base):
    """Follow package inheritance, refusing an undocumented population change."""
    paths, seen = [], set()
    current = read(base / 'package_report.json')
    population_sha = current['output_sha256']['common/history/pops/00_eu5_world.txt']
    while True:
        base = base.resolve()
        if base in seen:
            raise ValueError('Cycle in M5 package ancestry')
        seen.add(base)
        path = base / 'package_report.json'
        report = read(path)
        paths.append(path)
        if report['output_sha256']['common/history/pops/00_eu5_world.txt'] != population_sha:
            raise ValueError('Population changed without demographic provenance')
        if report.get('demographic_run'):
            return Path(report['demographic_run']), paths
        base = Path(report['prior_package'])


def build():
    pointer = ROOT / '.local/m5/installation-latest.json'
    review = ROOT / '.local/m4/location-workstation/location_reviews.json'
    guards = {str(p): digest(p) for p in (pointer, review)}
    installed = read(pointer)
    base = Path(installed['package'])
    report = read(base / 'package_report.json')
    source = Path(report['mod_directory'])
    baseline = files(source)
    if baseline != report['output_sha256'] or files(Path(installed['target'])) != baseline:
        raise ValueError('Installed files do not match the recorded M5 baseline')
    demographic, provenance = demographic_provenance(base)
    policy = read(POLICY)
    keys = [e['culture'] for e in policy['entries']]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate culture in historical research plan')
    links = defaultdict(set)
    with (demographic / 'staging/province_population_draft.csv').open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            links[row['source_location']].add(row['target_state'])
    additions = set()
    for e in policy['entries']:
        if e['status'] != 'candidate_core':
            continue
        if not e['sources'] or not e['period'] or not e['limitation']:
            raise ValueError('Unexplained homeland proposal')
        for loc, states in e['anchors'].items():
            if links[loc] != set(states):
                raise ValueError(f'Location link changed: {loc}')
        for s in e['sources']:
            if s not in policy['sources']:
                raise ValueError(f'Missing source: {s}')
        additions.update((s, e['culture']) for s in e['states'])
    output = ROOT / '.local/m5/historical-homelands' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    output.mkdir(parents=True, exist_ok=False)
    mod = output / 'candidate_mod'
    shutil.copytree(source, mod)
    oldtext = (source / STATE).read_text(encoding='utf-8-sig')
    oldpairs = homeland_pairs(oldtext)
    edits = []
    for scope, obj in objects(root(oldtext).fields()['STATES']):
        state = scope.removeprefix('s:')
        new = sorted(c for s, c in additions - oldpairs if s == state)
        if new:
            edits.append(replace_body(obj, obj.text() + ''.join('\nadd_homeland = cu:' + c + '\n' for c in new)))
    (mod / STATE).write_text(patch(oldtext, edits), encoding='utf-8-sig')
    write(output / 'policy.snapshot.json', policy)
    write(output / 'installation.snapshot.json', installed)
    inputs = [POLICY, Path(__file__), ROOT / 'tools/verify_m5_historical_homelands.py',
              *provenance, demographic / 'refinement_policy.snapshot.json',
              demographic / 'template_fallback/candidate_culture_catalog.csv',
              demographic / 'staging/province_population_draft.csv']
    if policy.get('full_survey'):
        survey = policy['full_survey']
        inputs.extend(ROOT / survey[k] for k in ('new_batch_table', 'reference_table', 'source_identity_index'))
        inputs.extend(sorted((ROOT / '.local/m5/historical-homelands').glob('research-*.json')))
        inputs.extend(sorted({Path(d['file']) for e in policy['entries'] for d in e.get('source_identity_definitions', {}).values()}))
    manifest = {
        'status': 'research_candidate_not_installed', 'baseline_version': installed['version'],
        'baseline_package': str(base), 'baseline_mod': str(source), 'candidate_mod': str(mod),
        'demographic_run': str(demographic), 'created': datetime.now().isoformat(),
        'demographic_provenance_reports': [str(p) for p in provenance],
        'input_sha256': {str(p): digest(p) for p in inputs}, 'baseline_sha256': baseline,
        'output_sha256': files(mod), 'observed_protected_sha256': guards,
        'added_pairs': sorted(additions - oldpairs), 'removed_pairs': [],
        'installation_allowed': False, 'all_historical_assets_reviewed': False,
        'note': 'Research overlay only. A future installation must rebase and verify against the then-current M5 package.'
    }
    write(output / 'manifest.json', manifest)
    from verify_m5_historical_homelands import verify
    evidence = verify(output)
    write(output / 'independent_verification.json', evidence)
    render(output, policy, evidence, demographic, oldpairs)
    if {p: digest(Path(p)) for p in guards} != guards:
        raise ValueError('Installation pointer or user reviews changed while preparing candidate; retry against fresh inputs')
    write(ROOT / '.local/m5/historical-homelands-latest.json', {
        'candidate': str(output), 'status': manifest['status'], 'baseline_version': installed['version'],
        'core_designs': evidence['newly_covered_cultures'], 'remaining_without_any_homeland': evidence['candidate_pending_count'],
        'design_decisions': evidence['design_decisions'], 'unprocessed_designs': evidence['unprocessed_designs'],
        'withheld_count': evidence['withheld_count']})
    landing = output.parent / 'index.html'
    landing.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=' + output.name + '/index.html">', encoding='utf-8')
    return output, evidence


def render(output, policy, evidence, demographic, before):
    with (demographic / 'template_fallback/candidate_culture_catalog.csv').open(encoding='utf-8-sig', newline='') as f:
        catalog = {r['culture']: r for r in csv.DictReader(f)}
    entries = {e['culture']: e for e in policy['entries']}
    records = []
    for culture in evidence['baseline_pending_cultures']:
        item = entries.get(culture)
        ready = item is not None and item['status'] == 'candidate_core'
        records.append({
            'culture': culture, 'name': catalog[culture]['name'],
            'source_identities': catalog[culture]['source_identities'],
            'research_batch': item.get('batch', '2026-10-02-01') if item else '',
            'centipersons': int(catalog[culture]['centipersons']),
            'status': 'candidate_core_partial_review' if ready else (item['status'] if item else 'pending_research'),
            'evidence_grade': item.get('evidence_grade', 'earlier_batch_documented_core') if item else '',
            'candidate_states': '|'.join(item['states']) if item else '',
            'historical_core': item['core'] if item else '',
            'period': item['period'] if item else '',
            'limitation': item['limitation'] if item else '尚未完成本土考证；不得继承旧兜底文化范围。',
            'sources': '|'.join(policy['sources'][s]['url'] for s in item['sources']) if item else ''})
    records.sort(key=lambda r: (-r['centipersons'], r['culture']))
    with (output / 'homeland_register.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    esc = html.escape
    body = []
    for r in records:
        item = entries.get(r['culture'])
        ready = r['status'] == 'candidate_core_partial_review'
        detail = ''
        if item:
            sources = ''.join('<li><a href="' + esc(policy['sources'][s]['url'], quote=True) + '">' + esc(policy['sources'][s]['title']) + '</a> — ' + esc(policy['sources'][s]['finding']) + '</li>' for s in item['sources'])
            detail = '<details><summary>依据、地图对应与边界限制</summary><p>' + esc(r['period']) + '</p><p>落州方式：' + esc(item['translation']) + '</p><pre>' + esc(json.dumps(item['anchors'], ensure_ascii=False, indent=2)) + '</pre><p>' + esc(r['limitation']) + '</p><ul>' + sources + '</ul></details>'
        status = 'core' if ready else ('deferred' if item else 'pending')
        labels = {'withheld_label_scope':'已决定暂不授予·标签成员不清', 'withheld_mobile_identity':'已决定暂不授予·流动群体', 'withheld_map_resolution':'已决定暂不授予·岛屿落州不足'}
        label = '核心候选·证据限制见详情' if ready else (labels.get(item['status'], '补证中·尚未授予本土') if item else '待考证')
        grade_labels = {'historical_core':'历史记载核心', 'ethnographic_backcast':'后世民族志回推', 'composite_member_cores':'合并成员核心', 'archaeological_survival':'考古身份存续设计', 'earlier_batch_documented_core':'前两批逐项证据'}
        label += '<br><small>' + esc(grade_labels.get(r['evidence_grade'], r['evidence_grade'])) + '</small>'
        body.append('<tr data-status="' + status + '"><td><b>' + esc(r['name']) + '</b><br><small>' + esc(r['culture']) + '<br>' + esc(r['source_identities']) + '</small></td><td>' + f"{r['centipersons']/100:,.2f}" + '</td><td>' + label + '<br><small>' + esc(r['research_batch']) + '</small></td><td>' + esc(r['historical_core']) + '<br><code>' + esc(r['candidate_states']) + '</code>' + detail + '</td></tr>')
    summary = f"{evidence['baseline_pending_count']} 项中已作设计决定 {evidence['design_decisions']} 项，未处理 {evidence['unprocessed_designs']} 项；{evidence['newly_covered_cultures']} 种核心候选 / {evidence['added_homeland_pairs']} 个文化—州配对，{evidence['withheld_count']} 项明确暂不授予（原因逐项公开）。候选仍有 {evidence['candidate_pending_count']} 种没有本土。"
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 历史本土考证</title>
<style>body{font:16px/1.65 system-ui;background:#f5f3ed;color:#242d2a;margin:32px auto;max-width:1500px;padding:0 24px}h1{margin-bottom:4px}header{background:#fff;padding:24px;border-left:6px solid #417862;margin-bottom:20px}input,select{font:inherit;padding:9px;margin:6px}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:14px;border-bottom:1px solid #ddd;vertical-align:top}th{background:#e1e8e1;position:sticky;top:0}td:first-child{width:25%}td:nth-child(2){white-space:nowrap}small,code{font-size:12px;overflow-wrap:anywhere}details{margin-top:12px;max-width:750px}summary{cursor:pointer;color:#25634c}pre{font-size:12px;white-space:pre-wrap}a{color:#1c5b75}.notice{color:#864a14}tr[hidden]{display:none}</style>
<header><h1>M5 · 历史本土考证</h1><p>SUMMARY</p><p class="notice">独立设计候选，未安装。全量设计决定不等于全部历史问题已有定论；暂不授予项仍是公开的历史或地图缺口。语言、传承、姓名与外观未因本轮自动成为“已审核”。</p><p>普通文化按历史聚居核心与州相交；不用20%人口阈值。移民保留全州严格超过50%的原政策。现代州名不能直接替代游戏州界。后世民族志回推及早期考古文化均单列，不能当作1780年精确边界。</p><p>累计已设计核心文化的全部原始源人口约 POP 人；这不是新增人口、本土内人数或当前安装版校准后人口。</p><p><a href="homeland_register.csv">下载全量登记表 CSV</a> · <a href="policy.snapshot.json">考证方案 JSON</a> · <a href="independent_verification.json">独立回读验证</a></p></header>
<label>搜索<input id="q" placeholder="文化、源身份、州、依据"></label><label>状态<select id="status"><option value="">全部</option><option value="core">核心候选</option><option value="deferred">未授予本土·查看原因</option><option value="pending">未处理</option></select></label><span id="count"></span>
<table><thead><tr><th>文化 / 源身份</th><th>源人口</th><th>本土状态</th><th>历史核心与对应州</th></tr></thead><tbody>ROWS</tbody></table>
<script>const q=document.querySelector('#q'),s=document.querySelector('#status'),rs=[...document.querySelectorAll('tbody tr')];function filter(){let n=0;for(const r of rs){r.hidden=!(r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(!s.value||r.dataset.status===s.value));if(!r.hidden)n++}document.querySelector('#count').textContent=n+' 种文化'}q.oninput=filter;s.onchange=filter;filter();</script></html>'''
    page = page.replace('SUMMARY', esc(summary)).replace('POP', f"{evidence['newly_covered_centipersons']/100:,.2f}").replace('ROWS', ''.join(body))
    (output / 'index.html').write_text(page, encoding='utf-8')


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    output, evidence = build()
    print(json.dumps({'candidate': str(output), 'verification': {k: v for k, v in evidence.items() if not k.endswith('_cultures')}}, ensure_ascii=True, indent=2))
