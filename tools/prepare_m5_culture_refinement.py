"""Apply a frozen identity partition to a separate, auditable M5 candidate."""
import copy
import csv
import html
import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from build_m3_world import load_localization
from m3_world import digest, load_json
from m4_cultures import resident_language
from m4_religions import definitions
from prepare_m5_culture_research import (ROOT, GAME, EU5, candidate_profile,
    build, build_templates, verify_templates, verify_demographics, verify_stage,
    write_json, read_rows)

POLICY = ROOT/'config/personal/m5_culture_refinement.json'
FIELDS = ('aggregate_members', 'aggregate_language', 'aggregate_language_labels',
          'display_labels', 'reviewed_language', 'research_review', 'heritage_trait', 'heritage_design')


def candidate(original, plan, research):
    old_groups = [g for g in original['global_culture_policy']['aggregates'] if len(g['members']) > 1]
    expected = {s for g in old_groups for s in g['members']}
    members = [s for g in plan['partitions'] for s in g['members']]
    if Counter(members) != Counter({s:1 for s in expected}):
        raise ValueError('Refinement must partition every old catchall member exactly once')
    reviewed, _ = candidate_profile(original, research)
    p = copy.deepcopy(original)
    traits = definitions(GAME/'common/discrimination_traits')
    trait_groups = definitions(GAME/'common/discrimination_trait_groups')
    native = definitions(GAME/'common/cultures')
    scaffold_path=ROOT/plan['source_scaffold_profile']
    if digest(scaffold_path)!=plan['source_scaffold_profile_sha256']:
        raise ValueError('Frozen source scaffold changed')
    original_pool = load_json(scaffold_path)['custom_resident_cultures']
    replacements = {}
    for source in expected:
        p['culture_compaction'].pop(source, None)
        c = p['custom_resident_cultures'][source]
        for field in FIELDS:c.pop(field, None)
        # Undo only the previous catchall's synthetic language selection.
        for field in ('language_trait','language_group'):
            c[field] = original_pool[source].get(field)
        c['heritage_group'] = traits[native[c['template']]['heritage']]['trait_group']
        c['reason'] = 'Preserve the named source identity after dissolving an unrelated residual catchall; no claim of completed historical review.'
        c['template_limitation'] = original_pool[source]['template_limitation'] + ' Heritage uses the existing template broad family as a provisional gameplay scaffold; no independent heritage family is generated.'
    for item in plan['partitions']:
        target = item['target']
        if target.startswith('eu5_resident_'):
            seed = target.removeprefix('eu5_resident_')
            if seed not in item['members']:raise ValueError('Representative outside its partition')
            c = p['custom_resident_cultures'][seed]
            if seed in research['identities']:
                c = copy.deepcopy(reviewed['custom_resident_cultures'][seed])
                p['custom_resident_cultures'][seed] = c
            c['display_labels'] = item['labels']
            c['reason'] = item['basis']
            c['review_status'] = 'generated_preservation_candidate_not_historically_reviewed'
            if len(item['members']) > 1:
                c['aggregate_members'] = item['members']
            if item.get('language'):
                language = item['language'];group = language.get('group') or 'eu5_reviewed_language_group_'+language['key']
                c['language_trait'] = None;c['language_group'] = group
                c['reviewed_language'] = {'trait':'eu5_reviewed_language_'+language['key'],
                    'group':group,'labels':language['labels'],
                    'sources':item['sources'],'basis':language['basis']}
                if not language.get('group'):c['reviewed_language']['group_labels']=language['labels']
            c['research_review'] = {**c.get('research_review',{}),
                'identity':item['status'],'fully_reviewed':False,'sources':item['sources'],
                'names':'template_pending','appearance':'template_pending'}
            lang,_ = resident_language({**c,'aggregate_seed':seed},traits,trait_groups,{}, {})
            heritage = c.get('heritage_trait') or 'eu5_resident_heritage_'+seed
        else:
            seed = None
            lang,heritage = native[target]['language'],native[target]['heritage']
        for source in item['members']:
            replacements[source] = target
            if source == seed:continue
            c = p['custom_resident_cultures'][source]
            p['culture_compaction'][source] = {'target':target,
                'source_language':c['source_language'],'source_groups':c['source_groups'],
                'target_language':lang,'target_heritage':heritage,
                'rule':'explicit_named_refinement','basis':item['basis'],'reason':item['basis'],
                'sources':item['sources'],'previous_target':'eu5_resident_'+source}
    p['global_culture_policy']['aggregates'] = [g for g in original['global_culture_policy']['aggregates'] if len(g['members']) == 1]
    p['global_culture_policy']['aggregates'] += [{'representative':g['target'].removeprefix('eu5_resident_'),
        'members':g['members'],'labels':g['labels']} for g in plan['partitions'] if g['target'].startswith('eu5_resident_')]
    p['global_culture_policy'].update(status='named_identity_refinement_candidate_not_installed',
        refinement_policy=str(POLICY), refinement_policy_sha256=digest(POLICY))
    p['culture_budget'] = plan['budget']
    return p,replacements


def make_register(out, baseline, plan):
    old = {r['source_culture']:r['target_culture'] for r in read_rows(baseline/'demographics/resident_culture_crosswalk.csv')}
    old_names = {r['culture']:r['name'] for r in read_rows(baseline/'template_fallback/candidate_culture_catalog.csv')}
    by_target = {g['target']:g for g in plan['partitions']}
    records = []
    for row in read_rows(out/'template_fallback/candidate_culture_catalog.csv'):
        item = by_target.get(row['culture'])
        records.append({**row,'change_status':item['status'] if item else 'unchanged',
            'old_categories':'|'.join(sorted({old_names.get(old[s],old[s]) for s in item['members']})) if item else '',
            'basis':item['basis'] if item else '保留原配置；不表示已完成历史审核。',
            'evidence_urls':'|'.join(item['sources']) if item else '',
            'fully_historically_reviewed':False})
    write_json(out/'culture_refinement_register.json', records)
    with (out/'culture_refinement_register.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    labels = load_localization(EU5/'main_menu/localization/simp_chinese')
    cross = []
    for item in plan['partitions']:
        for source in item['members']:
            cross.append({'source':source,'source_name':labels[source],'old':old_names[old[source]],
                'target':item['target'],'name':item['labels']['simp_chinese'],'status':item['status'],'basis':item['basis']})
    write_json(out/'source_refinement_crosswalk.json',cross)
    with (out/'source_refinement_crosswalk.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(cross[0]));w.writeheader();w.writerows(cross)
    e=lambda v:html.escape(str(v),quote=True)
    body=[]
    for r in records:
        links=' '.join('<a href="'+e(u)+'" target="_blank" rel="noreferrer">依据</a>' for u in r['evidence_urls'].split('|') if u)
        body.append('<tr data-status="'+e(r['change_status'])+'"><td>'+e(r['name'])+'<small>'+e(r['culture'])+'</small></td><td>'+f'{int(r["centipersons"])/100:,.2f}'+'</td><td>'+e(r['old_categories'])+'</td><td>'+e(r['source_identity_count'])+'<small>'+e(r['source_identities'])+'</small></td><td>'+e(r['change_status'])+'<small>'+e(r['basis'])+'</small>'+links+'</td></tr>')
    summary=[]
    for group in plan['old_catchalls']:
        targets=sorted({r['name'] for r in cross if r['source'] in group['members']})
        summary.append('<tr><td>'+e(group['labels']['simp_chinese'])+'</td><td>'+e(len(group['members']))+'</td><td>'+e('、'.join(targets))+'</td></tr>')
    report=load_json(out/'demographics/demographics_report.json')
    counts=report['culture_budget']['counts']
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 文化拆分与小文化合并</title><style>body{font:16px/1.65 system-ui;margin:30px;color:#213b35;background:#f3f6f3}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;border-bottom:1px solid #d8e2dd;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#d9ece1}small{display:block;overflow-wrap:anywhere;color:#52665e;font-size:12px}input,select{padding:9px;margin:8px}p{max-width:1100px}a{color:#12614c}details{margin:20px 0}</style><h1>M5 文化拆分与小文化合并 · 本地候选</h1><p>保留原版美拉尼西亚、西伯利亚、亚马孙等大类；移除36个新增兜底集合，246条源身份均有明确去向。范围有限的合称明确列出成员，不采用剩余地区或“其他”兜底。源游戏本身过粗的标签仍保留，并单列资料限制。</p><p>当前候选共有 '''+str(len(records))+''' 种使用文化，自定义居民资产 '''+str(counts['resident_assets'])+''' 个。下表可按名称、源键、原集合、依据检索。本次完成分类结构清理，不代表所有条目的历史传承、本土、姓名和外观审核完成。尚未部署；当前安装版不变。</p><p><a href="culture_refinement_register.csv">全量文化表 CSV</a> · <a href="source_refinement_crosswalk.csv">246条源身份去向 CSV</a> · <a href="independent_refinement_verification.json">独立人口验证</a></p><details><summary>36个原集合的完整去向</summary><table><thead><tr><th>原集合</th><th>源身份数</th><th>新输出</th></tr></thead><tbody>'''+''.join(summary)+'''</tbody></table></details><input id="q" placeholder="搜索文化、源身份、原集合"><select id="f"><option value="all">全部文化</option><option value="changed">本次调整</option><option value="named_composite_gameplay_design">明确成员的小文化合称</option><option value="source_label_broad_pending">源标签过粗，仍待考证</option></select><span id="count"></span><table><thead><tr><th>输出文化</th><th>人口</th><th>原集合</th><th>源身份数及键</th><th>设计与审核状态</th></tr></thead><tbody id="rows">'''+''.join(body)+'''</tbody></table><script>const q=document.querySelector('#q'),f=document.querySelector('#f'),rs=[...document.querySelectorAll('#rows tr')];function apply(){let n=0;for(const r of rs){const ok=r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(f.value==='all'||(f.value==='changed'?r.dataset.status!=='unchanged':r.dataset.status===f.value));r.hidden=!ok;if(ok)n++;}document.querySelector('#count').textContent=n+' 项';}q.oninput=apply;f.onchange=apply;apply();</script></html>'''
    (out/'index.html').write_text(page,encoding='utf-8')
    return records


def main():
    plan=load_json(POLICY);original=load_json(ROOT/'config/personal/m4_demographics.json')
    baseline=Path(load_json(ROOT/'.local/m4/demographics-latest.json')['run'])
    if digest(ROOT/'config/personal/m4_demographics.json') != plan['baseline_profile_sha256']:
        raise ValueError('Live culture policy advanced; rebase the frozen partition')
    protected=[ROOT/'config/personal/m4_demographics.json',ROOT/'.local/m4/demographics-latest.json',
        ROOT/'.local/m4/location-workstation/location_reviews.json',ROOT/'.local/m5/installation-latest.json',
        ROOT/'config/personal/m5_culture_geography.json',ROOT/'config/personal/m3_world.json']
    before={str(p):digest(p) for p in protected}
    research=load_json(ROOT/'config/personal/m5_culture_research.json')
    profile,replacements=candidate(original,plan,research)
    out=ROOT/'.local/m5/culture-refinement'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    for name,data in [('refinement_policy.snapshot.json',plan),('demographics_profile.snapshot.json',profile),
        ('explicit_source_replacements.json',replacements),('research.snapshot.json',research)]:write_json(out/name,data)
    for name in ('location_reviews.snapshot.json','population_policy.snapshot.json'):shutil.copy2(baseline/name,out/name)
    shutil.copytree(baseline/'staging',out/'staging')
    source=ROOT/'.local/m4/source-1780-population'
    verify_stage(source,out/'staging')
    build(out/'staging',source,out/'demographics',GAME,EU5,out/'demographics_profile.snapshot.json',ROOT/'config/personal/m3_world.json')
    verify_demographics(source,out/'demographics')
    build_templates(out,GAME,out/'population_policy.snapshot.json');verify_templates(out,GAME)
    make_register(out,baseline,plan)
    write_json(out/'refinement_manifest.json',{'run':str(out),'baseline':str(baseline),
        'protected_sha256':before,'installed_baseline':json.loads((ROOT/'.local/m5/installation-latest.json').read_text(encoding='utf-8-sig')),
        'homelands_emitted':False,'literacy_rebuilt_for_installation':False,'deployment_ready':False,
        'fully_historically_reviewed':False,'policy_sha256':digest(POLICY),
        'code_sha256':{str(p):digest(p) for p in (Path(__file__),ROOT/'tools/verify_m5_culture_refinement.py',ROOT/'tools/m4_culture_budget.py',ROOT/'tools/verify_m4_demographics.py')}})
    from verify_m5_culture_refinement import verify
    result=verify(out)
    assert all(digest(Path(p))==sha for p,sha in before.items()), 'Protected input changed'
    write_json(ROOT/'.local/m5/culture-refinement-latest.json',{'run':str(out),'status':result['status']})
    # Landing page is a link, so CSV / verification URLs keep their run directory.
    landing=out.parent/'index.html'
    landing.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+out.name+'/index.html"><a href="'+out.name+'/index.html">打开最新文化候选表</a>',encoding='utf-8')
    print(json.dumps({'run':str(out),**result},ensure_ascii=True))


if __name__=='__main__':main()
