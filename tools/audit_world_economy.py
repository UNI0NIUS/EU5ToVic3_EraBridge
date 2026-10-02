"""Coverage, source-development compliance and a local review of every country."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
from m3_world import digest
from economy_model import Target, building_rows
from pdx_text import root
from extract_m3_politics import fields


def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,o): p.write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8')

LABELS = {'agrarian_craft':'农业与基础手工业','commercial_craft':'商业手工业',
          'manufacturing':'工场制造业','industrial_frontier':'较强工业基础',
          'advanced_hand_manufacturing':'发达手工制造业'}


def audit(candidate, previous, output, game):
    if output.exists(): raise ValueError('Refusing to overwrite a world review')
    profiles = load(candidate/'development.json')['countries']
    run = load(candidate/'report.json')
    base = load(Path(run['base_package'])/'package_report.json')
    political = load(Path(base['political_run'])/'conversion_report.json')['countries']
    if set(profiles) != set(political): raise ValueError('World-country coverage mismatch')
    target = Target(game)
    from economy_development import manufacturing_kinds
    industry = manufacturing_kinds(target)
    country_history = fields(root((candidate/'overlay/common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['COUNTRIES']
    techs = {tag[2:]:{v for k,v in obj.entries() if k=='add_technology_researched'} for tag,obj in country_history.entries()}
    gross = {}
    for label, folder in (('previous_m5',previous),('candidate',candidate),('source_seed',Path(run['economy_candidate']))):
        totals = Counter()
        for row in building_rows(folder/'overlay/common/history/buildings/00_eu5_world.txt'):
            if row['building'] in industry:
                totals[row['owner']] += target.coefficients(row['building'],row['pms'],techs[row['owner']])['gross']*row['levels']
        gross[label] = totals
    capacity = load(candidate/'country_capacity.json')
    old = load(previous/'country_capacity.json')
    budgets = {r['country']:r for r in load(candidate/'bureaucracy.json')['countries']}
    fiscal = load(candidate/'living_standards_and_fiscal_screen.json')
    employment = load(candidate/'employment.json')
    infrastructure = load(candidate/'infrastructure_gaps.json')
    transport = load(candidate/'local_transportation_gaps.json')
    source_tags = {t for t,p in profiles.items() if p['scope']=='source_economy'}
    if set(capacity) != source_tags: raise ValueError('Source-country coverage mismatch')
    if set(budgets) != source_tags or set(fiscal) != source_tags: raise ValueError('Country audit coverage mismatch')
    errors, rows = [], {}
    for tag,p in sorted(profiles.items()):
        if p['scope']=='vanilla_fallback_preserved':
            rows[tag] = {**p,'review_status':'原版未殖民地区模板保留并纳入覆盖台账'}
            continue
        c,b,f = capacity[tag],budgets[tag],fiscal[tag]
        if p['manufacturing_envelope_excess']>.001: errors.append('industrial expansion exceeded source envelope '+tag)
        if c['armies']['exported_battalions'] != old[tag]['armies']['exported_battalions']: errors.append('source army changed '+tag)
        risk = []
        needs = {k:v for k,v in f['basic_need_base_value_shortfalls'].items() if v>.01}
        if needs: risk.append('基础消费品国内产能不足，需核对实际市场')
        if c['industrial_input_gaps']: risk.append('工业投入存在国内缺口')
        if b['core_demand_gap_at_planned_staffing']>.001: risk.append('行政基本需求估算缺口')
        elif b['planning_gap']>.001: risk.append('行政余量不足')
        state_infra = [r for r in infrastructure if r['country']==tag]
        local_transport = [r for r in transport if r['country']==tag]
        if state_infra or local_transport: risk.append('基础设施或地方运输不足')
        overstaffed = [r for r in employment if r['country']==tag and r['formal_job_capacity']>r['estimated_workforce']+.01]
        if overstaffed: risk.append('部分州既有军政等岗位超过预计劳动力')
        rows[tag] = {**p,'review_status':'已按源发展程度重算；动态经济待测试',
                     'manufacturing_gross_base_price_capacity':{label:values[tag] for label,values in gross.items()},
                     'before_building_levels':old[tag]['building_levels'],'building_levels':c['building_levels'],
                     'formal_jobs_by_building':c['formal_jobs_by_building'],
                     'manufacturing_jobs_as_workforce_share':p['final_manufacturing_jobs']/max(1,p['population']*.25),
                     'administration':b,'household_domestic_capacity_shortfalls':needs,
                     'industrial_domestic_gaps':c['industrial_input_gaps'],
                     'infrastructure_gaps':state_infra,'local_transport_gaps':local_transport,
                     'labor_overcapacity_states':overstaffed,
                     'public_weekly_cost_reference':f['weekly_public_cost_total'],
                     'budget_reference_is_forecast':False,'risks':risk}
    if errors: raise ValueError('World development verification failed: '+str(errors[:20]))
    counts = Counter(p['development_description'] for p in profiles.values() if p['scope']=='source_economy')
    result = {'status':'passed_source_development_static_runtime_pending','countries':rows,
              'coverage':{'all_countries':len(profiles),'source_countries_recalculated':len(source_tags),
                          'vanilla_fallback_preserved':len(profiles)-len(source_tags),'unprocessed_countries':0},
              'development_groups':dict(counts),'source_development_violations':0,'source_armies_unchanged':True,
              'core_administration_gaps':[t for t,b in budgets.items() if b['core_demand_gap_at_planned_staffing']>.001],
              'policy':'Economic/social fit first; modest fiscal deficits acceptable. No artificial full industrial supply chain for every country.',
              'candidate':str(candidate.resolve()),'previous':str(previous.resolve()),
              'input_sha256':{str((candidate/'manifest.json').resolve()):digest(candidate/'manifest.json'),
                              str(Path(__file__).resolve()):digest(Path(__file__))},
              'runtime_verified':False}
    output.mkdir(parents=True)
    write(output/'report.json',result)
    table = []
    for tag,r in rows.items():
        tag_h = html.escape(tag); name=html.escape(r['name']); description=LABELS.get(r['development_description'],'原版模板')
        details = {k:r[k] for k in ('source_employment','production_technologies','seed_manufacturing_levels')}
        for k in ('manufacturing_gross_base_price_capacity','building_levels','household_domestic_capacity_shortfalls','industrial_domestic_gaps','administration','risks'):
            if k in r: details[k]=r[k]
        searchable=html.escape(tag+' '+r['name']+' '+description,quote=True)
        tier='原版保留' if r['scope']=='vanilla_fallback_preserved' else description
        table.append(f'<tr data-search="{searchable}" data-scope="{r["scope"]}"><td><details><summary>{name} <small>{tag_h}</small></summary><pre>{html.escape(json.dumps(details,ensure_ascii=False,indent=2))}</pre></details></td><td>{tier}</td><td>{r["population"]:,}</td><td>{r["source_urban_population_share"]:.1%}</td><td>{r["source_relative_industrial_intensity"]:.3f}</td><td>{r["seed_manufacturing_jobs"]:,.0f} → {r["final_manufacturing_jobs"]:,.0f}</td><td>{len(r.get("risks",[]))}</td></tr>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>M5 全国家经济审核</title>
<style>body{font:15px system-ui;background:#f5f3ee;color:#26332e;margin:32px}h1{font-size:28px}p{max-width:1100px;line-height:1.8}input,select{padding:10px;margin:6px}table{width:100%;border-collapse:collapse;background:white}td,th{text-align:left;padding:11px;border-bottom:1px solid #ddd}th{position:sticky;top:0;background:#dce7df}small{color:#65736b}pre{max-width:650px;max-height:400px;overflow:auto;white-space:pre-wrap;font-size:12px}summary{cursor:pointer}tr[hidden]{display:none}.card{padding:14px;background:#e4ece5;border-radius:8px}</style>
<h1>M5：各国发展程度与经济结构审核</h1>
<p class="card">覆盖 {ALL} 国：{SOURCE} 国按 EU5 经济重算，{FALLBACK} 国保留原版未殖民地区模板。源工业扩建越界 0；源常备军保持。小幅赤字不作为失败条件。</p>
<p>人口和产业跟随本战役实际疆域。工业相对强度来自 EU5 实际就业、已建产能和产业阶段，1 为源工业前沿的校准点。英国只提供换算参照，不作为各国应达到的工业规模。制造业岗位为容量，非实际就业或 GDP。未满足的国内需求不等于市场必然短缺，尚需市场与贸易验证。</p>
<p>点击国名查看源证据、产业等级、行政估算与剩余风险。4 个保留模板只做覆盖登记。本页为新候选静态报告，游戏内验收待进行。</p>
<input id="q" placeholder="查国家、TAG 或发展类型" size="36"><select id="scope"><option value="">全部国家</option><option value="source_economy">EU5 源国家</option><option value="vanilla_fallback_preserved">保留原版地区</option></select><span id="count"></span>
<table><thead><tr><th>国家 / 详细证据</th><th>经济类型</th><th>人口</th><th>源城镇人口占比</th><th>源工业相对强度</th><th>源映射初始 → 本轮制造业岗位</th><th>风险类别</th></tr></thead><tbody>{ROWS}</tbody></table>
<script>const q=document.getElementById('q'),s=document.getElementById('scope');function filter(){let n=0;document.querySelectorAll('tbody tr').forEach(r=>{r.hidden=!(r.dataset.search.toLowerCase().includes(q.value.toLowerCase())&&(!s.value||r.dataset.scope===s.value));if(!r.hidden)n++});document.getElementById('count').textContent=n+' 国'}q.oninput=filter;s.onchange=filter;filter();</script></html>'''
    for key,value in {'ALL':len(rows),'SOURCE':len(source_tags),'FALLBACK':len(rows)-len(source_tags),'ROWS':''.join(table)}.items():
        page=page.replace('{'+key+'}',str(value))
    (output/'review.html').write_text(page,encoding='utf-8')
    write(output/'verification.json',{'status':'passed_static_runtime_pending','report_sha256':digest(output/'report.json'),
                                    'review_sha256':digest(output/'review.html'),'coverage':result['coverage']})
    return {k:v for k,v in result.items() if k!='countries'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('candidate','previous','output','game'): p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args(); print(json.dumps(audit(a.candidate,a.previous,a.output,a.game),ensure_ascii=False))
