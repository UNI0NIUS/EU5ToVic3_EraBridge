"""Build a bounded, evidence-indexed demographic candidate without deployment.

The live M4 profile/latest pointer, installed M5 package, and location reviews
are read-only. Historical homeland proposals remain distinct from emitted POPs.
"""
import copy
import csv
import html
import json
import shutil
from datetime import datetime
from pathlib import Path

from m3_world import digest, load_json
from m4_demographics import build
from m4_template_population import build_templates, verify_templates
from verify_m4_demographics import verify as verify_demographics
from verify_m4_population import verify as verify_stage

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT/'config/personal/m5_culture_research.json'
GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')
EU5 = Path('D:/Steam/steamapps/common/Europa Universalis V/game')


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def candidate_profile(original, research):
    p = copy.deepcopy(original)
    assert all(item['seed'] in p['custom_resident_cultures'] for item in research['next_priority'])
    replacements = {}
    for split in research['splits']:
        seed = split['old_seed']
        members = original['custom_resident_cultures'][seed]['aggregate_members']
        assert set(split['separate']) <= set(members)
        remaining = sorted(set(members)-set(split['separate']))
        residual = split['residual_seed']
        assert (residual in remaining) if remaining else (residual is None)
        for source in split['separate']:
            p['culture_compaction'].pop(source, None)
            c = p['custom_resident_cultures'][source]
            for field in ('aggregate_members','aggregate_language','aggregate_language_labels','display_labels'):
                c.pop(field, None)
            item = research['identities'][source]
            refs = [research['sources'][key]['url'] for key in item['sources']]
            language = item['language']
            group = language['group'] or 'eu5_reviewed_language_group_'+language['key']
            c['reviewed_language'] = {'trait':'eu5_reviewed_language_'+language['key'],
                'group':group, 'labels':language['labels'], 'sources':refs, 'basis':language['basis']}
            if not language['group']:c['reviewed_language']['group_labels'] = language['labels']
            c['language_trait'] = None
            c['language_group'] = group
            c['heritage_group'] = item['heritage']['group']
            if item['heritage']['trait']:c['heritage_trait'] = item['heritage']['trait']
            c['heritage_design'] = {**item['heritage'], 'sources':refs, 'status':'documented_gameplay_design_not_historical_equivalence'}
            c['display_labels'] = item['labels']
            c['reason'] = item['identity_basis']
            # Keep the legacy provisional flag: none of these is a complete
            # historical asset certification (names/portraits remain scaffolds).
            c['review_status'] = 'generated_preservation_candidate_not_historically_reviewed'
            c['research_review'] = {'identity':'evidence_supported_split', 'language':'evidence_supported_target_override',
                'heritage':'documented_design_candidate', 'homeland':item['homeland']['status'],
                'names':'template_pending', 'appearance':'template_pending', 'fully_reviewed':False, 'sources':refs}
            c['template_limitation'] = 'Names, portraits, graphics, traditions and default religion remain inherited template scaffolds. Research supports identity separation and the explicit language override only; shared heritage is a disclosed acceptance-design candidate. Historical homelands are separately reviewed proposals, not inferred from population thresholds. Resident religion is unchanged.'
            replacements[source] = 'eu5_resident_'+source
        if remaining:
            c = copy.deepcopy(original['custom_resident_cultures'][residual])
            c.update(heritage_group=original['custom_resident_cultures'][seed]['heritage_group'],
                     aggregate_members=remaining, aggregate_language=True,
                     display_labels=split['residual_labels'],
                     aggregate_language_labels={lang:label+('诸语言（游戏合并）' if lang=='simp_chinese' else ' languages (gameplay aggregate)') for lang,label in split['residual_labels'].items()})
            c['reason'] = 'Explicit residual membership after extracting Bugis and Makassarese; no claim that remaining peoples share one identity or language. Further historical review pending.'
            c['template_limitation'] += ' Residual category remains provisional and heterogeneous.'
            p['custom_resident_cultures'][residual] = c
            p['culture_compaction'].pop(residual, None)
            for source in remaining:
                target = 'eu5_resident_'+residual
                replacements[source] = target
                if source == residual:continue
                rule = p['culture_compaction'][source]
                rule.update(target=target, target_language='eu5_aggregate_language_'+residual,
                            target_heritage='eu5_resident_heritage_'+residual,
                            reason=c['reason'])
        aggregates = p['global_culture_policy']['aggregates']
        aggregates[:] = [g for g in aggregates if g['representative'] != seed]
        aggregates.extend({'representative':s,'members':[s],'labels':research['identities'][s]['labels']} for s in split['separate'])
        if remaining:aggregates.append({'representative':residual,'members':remaining,'labels':split['residual_labels']})
    p['culture_budget']['max_used_cultures'] = 405
    p['global_culture_policy']['status'] = 'bounded_research_candidate_partial_field_reviews_not_installed'
    p['global_culture_policy']['research_policy'] = str(RESEARCH)
    p['global_culture_policy']['research_policy_sha256'] = digest(RESEARCH)
    return p, replacements


def make_register(out, baseline, research):
    records = []
    for row in read_rows(out/'template_fallback/candidate_culture_catalog.csv'):
        seed = row['culture'].removeprefix('eu5_resident_')
        item = research['identities'].get(seed)
        records.append({**row,
            'identity_status':'本批已有拆分依据' if item else '尚未逐项历史审核',
            'language_status':'有依据的目标覆盖' if item else '现有转换配置，待考证',
            'heritage_status':'有说明的玩法候选' if item else '现有传承，待考证',
            'historical_core':item['homeland']['region'] if item else '',
            'homeland_status':item['homeland']['status'] if item else 'legacy_policy_not_historical_certification',
            'candidate_homeland_states':'|'.join(item['homeland']['states']) if item else '',
            'names_appearance_status':'模板待审' if row['culture'].startswith('eu5_') else '原版资产；转换对应仍待审',
            'fully_historically_reviewed':False,
            'evidence_urls':'|'.join(research['sources'][s]['url'] for s in item['sources']) if item else '',
            'limitations':item['homeland']['limitation'] if item else '列入清单不表示审核完成；本批保留现有映射。'})
    write_json(out/'culture_research_register.json', records)
    with (out/'culture_research_register.csv').open('w', encoding='utf-8-sig', newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    e=lambda value:html.escape(str(value),quote=True)
    body=[]
    for row in records:
        refs=' '.join('<a href="'+e(u)+'" target="_blank" rel="noreferrer">来源'+str(i+1)+'</a>' for i,u in enumerate(filter(None,row['evidence_urls'].split('|'))))
        body.append('<tr data-reviewed="'+str(bool(row['evidence_urls'])).lower()+'"><td>'+e(row['name'])+'<small>'+e(row['culture'])+'</small></td><td>'+f'{int(row["centipersons"])/100:,.2f}'+'</td><td>'+e(row['source_identity_count'])+'</td><td>'+e(row['identity_status'])+'<small>'+e(row['language_status'])+' / '+e(row['heritage_status'])+'</small></td><td>'+e(row['historical_core'])+'<small>'+e(row['homeland_status'])+' '+e(row['candidate_homeland_states'])+'</small></td><td>'+refs+'<small>'+e(row['limitations'])+'</small></td></tr>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 文化考证候选</title><style>body{font:16px/1.6 system-ui;margin:32px;color:#20332e;background:#f6f7f4}h1{margin-bottom:8px}p{max-width:1100px}input,select{padding:10px;margin:8px;border:1px solid #9ab2a7;border-radius:6px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;text-align:left;border-bottom:1px solid #d7e1da;vertical-align:top}th{position:sticky;top:0;background:#deeee5}small{display:block;color:#5c6f65;font-size:12px;overflow-wrap:anywhere}a{color:#16735a}tr[data-reviewed=true]{background:#eff9f3}</style><h1>M5 文化逐项考证 · 第一批候选</h1><p>这是研究与人口转换候选，尚未部署。全部 405 个输出类别列在下面，其中 7 项已有身份拆分和语言依据；传承仍是明确标注的玩法设计，姓名与外观未完成审核。普通文化本土改为历史核心逐项核对：本批 4 项有候选州，3 项仍待历史时段或地图核对。其他项目保留旧转换状态，不冒充历史审核通过。</p><p>20% 聚居自动本土规则仅是旧版转换器实现；新方案不将它当作历史结论。移民文化继续采用用户指定的全州严格超过 50% 规则。人口所在地不会因为本土考证而被移动。</p><input id="query" placeholder="搜索文化、源键、本土或状态"><select id="filter"><option value="all">全部类别</option><option value="true">本批有依据的 7 项</option><option value="false">尚未逐项考证</option></select><span id="count"></span><table><thead><tr><th>文化</th><th>候选人口</th><th>源身份数</th><th>审核状态</th><th>历史核心与候选州</th><th>依据与限制</th></tr></thead><tbody>'''+''.join(body)+'''</tbody></table><script>const q=document.querySelector('#query'),f=document.querySelector('#filter'),rs=[...document.querySelectorAll('tbody tr')];function apply(){let n=0;for(const r of rs){const ok=r.textContent.toLowerCase().includes(q.value.toLowerCase())&&(f.value==='all'||r.dataset.reviewed===f.value);r.hidden=!ok;if(ok)n++;}document.querySelector('#count').textContent=n+' 项';}q.addEventListener('input',apply);f.addEventListener('change',apply);apply();</script></html>'''
    (out/'culture_research.html').write_text(page,encoding='utf-8')
    return records


def main():
    baseline=Path(load_json(ROOT/'.local/m4/demographics-latest.json')['run'])
    installed=load_json(ROOT/'.local/m5/installation-latest.json')
    protected=[ROOT/'.local/m4/location-workstation/location_reviews.json', ROOT/'.local/m4/demographics-latest.json',
               ROOT/'config/personal/m4_demographics.json', ROOT/'config/personal/m5_culture_geography.json',
               ROOT/'.local/m5/installation-latest.json']
    before={str(p):digest(p) for p in protected}
    research=load_json(RESEARCH)
    original=load_json(ROOT/'config/personal/m4_demographics.json')
    assert digest(ROOT/'config/personal/m4_demographics.json')==digest(baseline/'demographics_profile.snapshot.json'), 'Live profile advanced; rebase research before proceeding'
    profile,replacements=candidate_profile(original,research)
    out=ROOT/'.local/m5/culture-research'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    write_json(out/'research.snapshot.json',research)
    write_json(out/'demographics_profile.snapshot.json',profile)
    write_json(out/'explicit_source_replacements.json',replacements)
    shutil.copy2(baseline/'location_reviews.snapshot.json',out/'location_reviews.snapshot.json')
    shutil.copy2(baseline/'population_policy.snapshot.json',out/'population_policy.snapshot.json')
    shutil.copytree(baseline/'staging',out/'staging')
    source=ROOT/'.local/m4/source-1780-population'
    verify_stage(source,out/'staging')
    build(out/'staging',source,out/'demographics',GAME,EU5,out/'demographics_profile.snapshot.json',ROOT/'config/personal/m3_world.json')
    verify_demographics(source,out/'demographics')
    build_templates(out,GAME,out/'population_policy.snapshot.json')
    verify_templates(out,GAME)
    make_register(out,baseline,research)
    code={str(p):digest(p) for p in (Path(__file__),ROOT/'tools/verify_m5_culture_research.py',ROOT/'tools/m4_cultures.py',ROOT/'tools/verify_m4_culture_assets.py')}
    manifest={'status':'verified_demographic_research_candidate_not_installed', 'run':str(out), 'baseline':str(baseline),
        'installed_baseline':installed, 'protected_sha256':before,
        'code_sha256':code,
        'research_config_sha256':digest(RESEARCH), 'fully_historically_reviewed':False,
        'homelands_emitted':False, 'literacy_rebuilt_for_installation':False,
        'limitations':['Demographic/assets candidate only; no installed M5 files or pointers changed.',
            'Before integration, recalculate literacy selectors and colors, finish homeland state review, and preserve M5 economy/flag fixes.']}
    assert all(digest(Path(p))==sha for p,sha in before.items()), 'Protected input changed while building'
    write_json(out/'research_manifest.json',manifest)
    from verify_m5_culture_research import verify
    verification=verify(out)
    write_json(ROOT/'.local/m5/culture-research-latest.json',{'run':str(out),'status':verification['status']})
    shutil.copy2(out/'culture_research.html',out.parent/'index.html')
    print(json.dumps({'run':str(out),**verification},ensure_ascii=True))


if __name__=='__main__':main()
