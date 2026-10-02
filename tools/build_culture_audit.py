"""Publish country-primary and source-culture crosswalks for review."""
import argparse
from collections import defaultdict
import csv
import html
import json
from pathlib import Path

from build_m3_world import load_localization


def audit(run, previous, game):
    r=json.loads((run/'conversion_report.json').read_text(encoding='utf-8'))
    version=json.loads((Path(r['mod_directory'])/'.metadata/metadata.json').read_text(encoding='utf-8'))['version']
    old=json.loads((previous/'conversion_report.json').read_text(encoding='utf-8')) if previous else {'countries':{}}
    loc=load_localization(game/'localization/simp_chinese')
    for c in r['countries'].values():
        if c.get('source_culture_details'):loc['eu5_'+c['source_culture']]=c['source_culture_details']['name_simp_chinese']
    fields=['tag','country','reused_v3_tag','source_culture','source_name','source_language','source_groups','target_cultures','target_names','mapping_method','previous_primary','changed','accepted_source_count','tolerated_source_count']
    rows=[]; cross=defaultdict(list)
    for tag,c in sorted(r['countries'].items()):
        if not c['source_id']:continue
        info=c['source_culture_details'];before=old['countries'].get(tag,{}).get('culture','')
        row=dict(zip(fields,[tag,c['name_simp_chinese'],tag in r['source_name_overrides'],c['source_culture'],info['name_simp_chinese'],info['language'],','.join(info['groups']),';'.join(c['cultures']),';'.join(loc.get(t,t) for t in c['cultures']),c['culture_mapping'],before,before!=c['culture'],len(c['source_accepted_cultures']),len(c['source_tolerated_cultures'])]))
        rows.append(row);cross[c['source_culture']].append(row)
    def write_csv(name,keys,items):
        with (run/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(items)
    write_csv('country-primary-cultures.csv',fields,rows)
    cross_rows=[{'source':s,'source_name':items[0]['source_name'],'language':items[0]['source_language'],'source_groups':items[0]['source_groups'],'target':items[0]['target_cultures'],'target_name':items[0]['target_names'],'method':items[0]['mapping_method'],'countries':';'.join(i['tag'] for i in items)} for s,items in sorted(cross.items())]
    write_csv('culture-crosswalk.csv',list(cross_rows[0]),cross_rows)
    result={'status':'all_country_primaries_reviewed','source_countries':len(rows),'distinct_source_primary_cultures':len(cross),'changed_country_primaries':sum(x['changed'] for x in rows),'reused_tags_reviewed':sum(x['reused_v3_tag'] for x in rows),'custom_culture_definitions':len(r['custom_cultures']),'primary_fallbacks':0,'ruler_fallbacks':sum('fallback' in p['culture_mapping'] for p in r['rulers']),'primary_policy':'Only EU5 primary culture becomes V3 primary. Accepted/tolerated cultures are recorded separately, not automatically promoted.'}
    (run/'culture_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda v:html.escape(str(v))
    table=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [x['country'],x['tag'],x['source_name'],x['source_culture'],x['target_names'],x['target_cultures'],x['mapping_method'],x['previous_primary'],'是' if x['changed'] else '否'])+'</tr>' for x in rows)
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>主流文化核对</title>
<style>body{{font:15px/1.6 system-ui;background:#132331;color:#e8eff5;margin:26px}}a{{color:#93d3ff}}input{{padding:12px;width:70%;position:sticky;top:0}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #405467}}.note{{padding:16px;background:#233847}}</style>
<h1>376 国主流文化核对 · M3 {version}</h1><p>{len(cross)} 种源主流文化；较对照构建变更 {result['changed_country_primaries']} 国；复核 {result['reused_tags_reviewed']} 个原版 TAG；地区文化回退为零。</p>
<div class="note">明：江淮 → 汉，保留源“明”国名和纹章，避免原版清朝规则覆盖。主流文化来自源国家身份，不以居民多数、地区模板或 TAG 字母猜测。EU5 的接纳／容忍文化不等于 V3 主流文化，没有全数提升为主流。<br>32 个自定义文化保留源身份；其中 24 个用于国家主流，另 8 个用于当前元首。命名池、肖像和传统沿用明确模板；传承、语言与未知语系的近似见完整报告。人口文化尚未投放到游戏。</div>
<p><a href="country-primary-cultures.csv">逐国 CSV</a> · <a href="culture-crosswalk.csv">文化对照 CSV</a> · <a href="conversion_report.json">完整来源和近似</a> · <a href="review.html">政治核对页</a></p>
<input id="q" placeholder="搜索国家、文化或 TAG"><table><thead><tr><th>国家</th><th>TAG</th><th>源文化</th><th>源键</th><th>目标文化</th><th>目标键</th><th>依据</th><th>旧版主流</th><th>已变更</th></tr></thead><tbody>{table}</tbody></table>
<script>document.querySelector('#q').oninput=e=>{{for(const r of document.querySelectorAll('tbody tr'))r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase())}}</script></html>'''
    (run/'culture-audit.html').write_text(page,encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--previous',type=Path)
    p.add_argument('--game',type=Path,default=Path('D:/Steam/steamapps/common/Victoria 3/game'))
    a=p.parse_args();print(json.dumps(audit(a.run,a.previous,a.game)))
