"""Build a version-pinned EU5/V3 identity crosswalk; never match by tag alone."""
import argparse
from collections import defaultdict, Counter
import csv
import html
import json
from pathlib import Path
import re
import unicodedata

from build_m3_world import Exporter, load_localization
from build_m2_prototype import objects, strings
from pdx_text import root
from m3_world import digest, fields, load_json

ROOT = Path(__file__).resolve().parents[1]


def normalized(value):
    value = unicodedata.normalize('NFKD', value).casefold()
    return ''.join(c for c in value if c.isalnum())


def name_candidates(names, index):
    result = set()
    for name in names:
        if name:
            result.update(index.get(normalized(name), ()))
    return sorted(result)


def build(a):
    audit, politics, report = load_json(a.audit), load_json(a.politics), load_json(a.report)
    reviews = load_json(a.reviews) if a.reviews.exists() else {'matches': {}, 'reject': {}}
    localizer = Exporter.__new__(Exporter)
    localizer.source_loc = {lang: load_localization(a.eu5 / 'main_menu/localization' / lang)
                            for lang in ('english', 'simp_chinese')}
    target_loc = {lang: load_localization(a.game / 'localization' / lang) for lang in localizer.source_loc}
    catalog, inputs = {}, {}
    for path in sorted((a.game / 'common/country_definitions').glob('*.txt')):
        inputs[path.relative_to(a.game).as_posix()] = digest(path)
        for tag, obj in objects(root(path.read_text(encoding='utf-8-sig'))):
            f = fields(obj)
            catalog[tag] = {'tag': tag, 'name_en': target_loc['english'].get(tag, tag),
                            'name_zh': target_loc['simp_chinese'].get(tag, tag),
                            'country_type': f.get('country_type', ''), 'capital': f.get('capital', ''),
                            'cultures': ','.join(strings(f['cultures'])) if 'cultures' in f else '',
                            'definition_file': path.relative_to(a.game).as_posix()}
    index = defaultdict(set)
    for tag, row in catalog.items():
        for field in ('name_en', 'name_zh'):
            if row[field] != tag:
                index[normalized(row[field])].add(tag)
    represented = {c['source_id']: c for c in report['countries'].values() if c['source_id']}
    reserved = {c['tag'] for c in report['countries'].values() if not c['source_id']}
    dependencies = {e['subject']: e['type'] for e in politics['subjects']}
    rows = []
    for country in audit['countries']:
        if not country['owned_locations']: continue
        sid, stag = str(country['id']), country['tag']
        src, exported = politics['countries'][sid], represented.get(str(country['id']))
        names = {}
        for lang in localizer.source_loc:
            if exported:
                names[lang] = exported['name_' + lang]
            else:
                raw = src['name']; data = dict(raw) if isinstance(raw, list) else {'name': raw}
                custom = dict(data.get('key', [])).get('Custom_Name')
                names[lang] = custom or localizer.localize(data.get('name') or stag, lang)
        candidates = name_candidates(names.values(), index)
        row = {'source_id': sid, 'eu5_tag': stag, 'eu5_definition': src['definition'],
               'name_zh': names['simp_chinese'], 'name_en': names['english'],
               'current_v3_tag': exported['tag'] if exported else '',
               'represented': bool(exported), 'subject_type': dependencies.get(sid, ''),
               'target_tag': '', 'target_name_en': '', 'target_name_zh': '',
               'status': 'custom_no_exact_identity', 'evidence': '', 'candidates': ','.join(candidates),
               'same_tag_v3_name': catalog.get(stag, {}).get('name_en', '')}
        reviewed = reviews['matches'].get(stag)
        if stag in reviews.get('reject', {}):
            row.update(status='custom_reviewed', evidence=reviews['reject'][stag])
        elif reviewed:
            row.update(target_tag=reviewed['target'], status='reviewed', evidence=reviewed['reason'])
        elif row['subject_type'] in ('colonial_nation', 'trade_company', 'state_bank'):
            row.update(status='custom_dynamic_subject', evidence='Dynamic subject: geographical name alone does not establish historical country identity.')
        elif len(candidates) == 1:
            row.update(target_tag=candidates[0], status='exact_localized_name', evidence='Unique exact English or Chinese identity in installed game localization.')
        elif candidates:
            row.update(status='review_multiple_candidates', evidence='Name resolves to more than one V3 country.')
        if row['target_tag']:
            tag = row['target_tag']
            if tag not in catalog: raise ValueError('Reviewed target not defined in installed V3: ' + tag)
            row.update(target_name_en=catalog[tag]['name_en'], target_name_zh=catalog[tag]['name_zh'])
            if tag in reserved:
                row.update(status='review_reserved_vanilla_country', evidence='Target is already retained for uncolonized vanilla territory.', target_tag='')
        rows.append(row)
    assigned = defaultdict(list)
    for row in rows:
        if row['target_tag'] and row['represented']: assigned[row['target_tag']].append(row)
    for tag, claims in assigned.items():
        if len(claims) > 1:
            for row in claims:
                row.update(status='review_target_collision', evidence='Multiple surviving source countries claim ' + tag, target_tag='')
    rows.sort(key=lambda r: int(r['source_id']))
    a.out.mkdir(parents=True, exist_ok=True)
    data = {'source_sha256': politics['source_sha256'], 'target_version': '1.13.11',
            'wiki': {'url': 'https://vic3.paradoxwikis.com/Countries', 'retrieval': 'HTTP 401; not used as data'},
            'authority': 'Installed V3 1.13.11 definitions and both games English/Chinese localization',
            'target_definition_sha256': inputs, 'rows': rows}
    (a.out / 'eu5_v3_crosswalk.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    if a.write_config:
        mapping = {'source_sha256': politics['source_sha256'], 'target_version': '1.13.11',
                   'matches': {r['source_id']: {'source_tag': r['eu5_tag'], 'target_tag': r['target_tag'],
                                                'status': r['status'], 'evidence': r['evidence']}
                               for r in rows if r['target_tag']}}
        (ROOT / 'config/personal/country_tag_mappings.json').write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding='utf-8')
    for filename, values in (('eu5_v3_crosswalk.csv', rows), ('v3_1.13.11_catalog.csv', sorted(catalog.values(), key=lambda c: c['tag']))):
        with (a.out / filename).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(values[0])); writer.writeheader(); writer.writerows(values)
    columns = [('source_id', 'EU5 ID'), ('name_zh', 'EU5 国家'), ('name_en', '英文名'), ('eu5_tag', 'EU5 当前 TAG'),
               ('eu5_definition', '原始定义'), ('current_v3_tag', '此前 TAG'), ('target_tag', '对应 V3 TAG'),
               ('target_name_en', 'V3 名称'), ('represented', '有目标领土'), ('status', '判定'), ('evidence', '依据'), ('same_tag_v3_name', 'V3 同码名称')]
    table = ''.join('<tr>' + ''.join('<td>' + html.escape(str(r[k])) + '</td>' for k, _ in columns) + '</tr>' for r in rows)
    page = '<!doctype html><meta charset="utf-8"><title>EU5 → V3 国家 TAG 对照表</title><style>body{font:15px system-ui;margin:24px;color:#203040}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd4dd;padding:8px;text-align:left}th{position:sticky;top:0;background:#e8eef4}input{padding:12px;width:65%}tr:nth-child(even){background:#f5f7fa}</style>'
    page += '<h1>EU5 1.3.11 → V3 1.13.11 国家 TAG 对照表</h1><p>按本机版本校验。当前 TAG 优先于原始定义；同码不等于同一国家。无目标领土（False）的条目仅供查阅；动态殖民国家与存在歧义的条目保留自定义 TAG。</p><p>exact_localized_name＝名称唯一匹配；reviewed＝人工核对；custom_reviewed＝已排除错误对应；custom_dynamic_subject＝动态殖民／公司政权；custom_no_exact_identity＝暂无精确对应。复用 TAG 不表示继承原版政体或君主。</p><p><a href="eu5_v3_crosswalk.csv">下载对照 CSV</a> · <a href="v3_1.13.11_catalog.csv">完整 V3 TAG 库</a> · <a href="README.md">规则和限制</a></p><input id="q" placeholder="搜索国家、TAG 或判定"><p id="count"></p><table><thead><tr>'
    page += ''.join('<th>' + v + '</th>' for _, v in columns) + '</tr></thead><tbody>' + table + '</tbody></table>'
    page += '<script>const rows=[...document.querySelectorAll("tbody tr")];function filter(){let n=0;for(const r of rows){r.hidden=!r.textContent.toLowerCase().includes(document.querySelector("#q").value.toLowerCase());if(!r.hidden)n++}document.querySelector("#count").textContent=`显示 ${n} / ${rows.length} 个国家`}document.querySelector("#q").addEventListener("input",filter);filter()</script>'
    (a.out / 'index.html').write_text(page, encoding='utf-8')
    print(json.dumps({'source_rows': len(rows), 'target_catalog': len(catalog), 'status': Counter(r['status'] for r in rows),
                      'represented_matches': sum(bool(r['target_tag']) and r['represented'] for r in rows)}, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--audit', type=Path, default=ROOT / '.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json')
    p.add_argument('--politics', type=Path, default=ROOT / '.local/m3/politics-final.json')
    p.add_argument('--report', type=Path, default=ROOT / '.local/m3/runs/20260930-145836-93933c04/conversion_report.json')
    p.add_argument('--game', type=Path, default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    p.add_argument('--eu5', type=Path, default=Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    p.add_argument('--reviews', type=Path, default=ROOT / 'config/personal/country_tag_reviews.json')
    p.add_argument('--out', type=Path, default=ROOT / 'docs/country_tags')
    p.add_argument('--write-config', action='store_true')
    build(p.parse_args())
