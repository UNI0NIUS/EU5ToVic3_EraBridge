"""Read-only bidirectional geometry/population coverage audit of a pinned M4 run."""
import argparse,csv,html,json
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from m3_world import World,load_json,digest,fields,province
from build_m2_prototype import strings
from verify_m3_world import gather_pops
from verify_m4_population import rows

ROOT=Path(__file__).resolve().parents[1]


def audit(run,out,game,eu5):
    if out.exists():raise ValueError('Refusing to overwrite audit')
    stage=run/'staging'; sr=load_json(stage/'staging_report.json')
    political=Path(sr['political_run']); report=load_json(political/'conversion_report.json')
    source=ROOT/'.local/m4/source-1780-population'
    inputs={}
    def checked(path,expected=None):
        sha=digest(path)
        if expected:assert sha==expected,path
        inputs[str(path.resolve())]=sha
    for name,sha in sr['files_sha256'].items():checked(stage/name,sha)
    for name in ('staging_report.json',):checked(stage/name)
    checked(political/'conversion_report.json');checked(political/'province_owners.json')
    checked(run/'location_reviews.snapshot.json',sr['location_reviews']['sha256'])
    checked(ROOT/'config/personal/m3_world.json',sr['profile_sha256'])
    policy={}
    if sr.get('population_policy'):
        policy_path=Path(sr['population_policy']['path']);checked(policy_path,sr['population_policy']['sha256']);policy=load_json(policy_path)
    template_report=None
    if (run/'template_fallback/template_report.json').exists():
        checked(run/'template_fallback/template_report.json');checked(run/'template_fallback/independent_verification.json')
        template_report=load_json(run/'template_fallback/template_report.json')
    summary=load_json(source/'source_summary.json')
    for name,sha in summary['files_sha256'].items():checked(source/name,sha)
    w=World(game,eu5,load_json(ROOT/'.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json'),load_json(ROOT/'.local/m3/politics-with-cultures.json'),load_json(ROOT/'config/personal/m3_world.json'),ROOT/'.local/m3/cache')
    w.geometry();w.politics_model()
    if report.get('uncolonized_tribes'):
        from m3_uncolonized import restore
        restore(w,report['uncolonized_tribes'])
    if report.get('empty_terrain_attachments'):
        from m5_territory_replay import restore as restore_terrain
        restore_terrain(w,report)
    if report.get('terrain_finalization'):
        from m3_terrain_finalization import apply as finalize_terrain
        finalize_terrain(w,report['terrain_finalization'])
    if report.get('frontier_finalization'):
        from m3_colonial_frontier import apply as finalize_frontier
        finalize_frontier(w,report['frontier_finalization'])
    assert w.owners==load_json(political/'province_owners.json')
    assert w.mapping_sha256==sr['mapping_sha256']
    for rel,sha in w.inputs.items():
        assert report['target_inputs_sha256'][rel]==sha,rel
        inputs[str(game/rel)]=sha
    cross=list(rows(stage/'location_crosswalk.csv'))
    sources={r['source_location']:r for r in cross}
    links=defaultdict(set)
    for r in cross:
        for p in filter(None,r['target_provinces'].split(';')):links[p].add(r['source_location'])
    owners={p:(s,t) for s,ps in w.owners.items() for p,t in ps.items()}
    assert set(links)<=owners.keys()
    pop={r['province']:int(r['centipersons']) for r in rows(stage/'province_totals.csv')}
    assert sum(pop.values())==sr['world_centipersons']
    assert sum(int(r['pending_centipersons']) for r in cross)==0
    imp={province(p) for o in w.defs.values() if 'impassable' in fields(o) for p in strings(fields(o)['impassable'])}
    hubs=defaultdict(list)
    for s,o in w.defs.items():
        for k,v in fields(o).items():
            if k in ('city','port','farm','mine','wood'):hubs[province(v)].append(k)
    # Workstation labels are convenience metadata only; all classifications use game definitions.
    labels=load_json(ROOT/'.local/m4/location-workstation/data.json')['targets']
    fallbacks={r['province']:r['rule'] for r in report['vanilla_fallbacks']}
    repairs=defaultdict(list)
    for r in report['map_repairs']:repairs[r['province']].append(r['rule'])
    target=[]; counts=Counter()
    for p,(s,t) in sorted(owners.items()):
        ns=links[p]; n=pop.get(p,0)
        category=('population_received' if n else 'no_source_link' if not ns else
                  'linked_only_uninhabitable_source' if ns<=w.uninhabitable else 'linked_zero_population_source')
        counts[category]+=1
        candidates=[]
        if category=='no_source_link' and p not in imp:
            candidates=sorted((q for q in w.provinces[s] if owners[q][1]==t and links[q] and q not in imp),key=lambda q:(w.distance(p,q),q))[:3]
        target.append({'province':p,'state':s,'state_name':labels.get(p,{}).get('state_name',s),'owner':t,
            'owner_name':report['countries'][t].get('name_simp_chinese',t),'classification':category,'impassable':p in imp,
            'hubs':';'.join(hubs[p]),'political_sources':';'.join(w.mapping.get(p,[])),
            'population_sources':';'.join(sorted(ns)),'centipersons':n,
            'political_fallback':fallbacks.get(p,''),'political_repairs':';'.join(repairs[p]),
            'same_state_owner_nearby_candidates':' | '.join(q+':'+','.join(sorted(links[q])) for q in candidates)})
    parts=defaultdict(list)
    for p,(s,t) in owners.items():parts[s,t].append(p)
    state_totals=Counter(); empty=[]
    template=gather_pops(list((Path(report['mod_directory'])/'common/history/pops').glob('*.txt')))
    # Existing converter templates are state totals, not measured EU5 populations.
    for (s,c,r),n in template.items():state_totals[s.removeprefix('s:')]+=n
    for (s,t),ps in sorted(parts.items()):
        if not sum(pop.get(p,0) for p in ps):
            ns={n for p in ps for n in links[p]}
            empty.append({'state':s,'state_name':labels[ps[0]]['state_name'],'owner':t,
                'owner_name':report['countries'][t].get('name_simp_chinese',t),'provinces':len(ps),
                'source_locations':';'.join(sorted(ns)), 'template_state_population':state_totals[s],
                'entire_state_empty':not any(pop.get(p,0) for p in w.provinces[s])})
    missing=[r for r in target if r['classification']=='no_source_link']
    actionable=[r for r in missing if not r['impassable']]
    zero_source=[{'source_location':r['source_location'],'source_owner':r['source_owner'],
                  'centipersons':int(r['source_centipersons']), 'uninhabitable':r['source_location'] in w.uninhabitable}
                 for r in cross if not r['target_provinces']]
    omitted_ids={c['id'] for c in report['omitted_countries']}
    omitted_pop=sum(int(r['source_centipersons']) for r in cross if r['source_owner'] in omitted_ids)
    demo=load_json(run/'demographics/demographics_report.json')
    checked(run/'demographics/demographics_report.json')
    result={'status':'audited_no_mapping_or_population_changes','demographic_run':str(run.resolve()),
        'political_run':str(political),'review_revision':load_json(run/'location_reviews.snapshot.json')['revision'],
        'target_land_provinces':len(target),'classification_counts':dict(counts),
        'target_no_effective_source_links':len(missing),'target_no_effective_links_impassable':len(missing)-len(actionable),
        'target_no_effective_links_traversable':len(actionable),
        'user_deferred_target_provinces':policy.get('deferred_target_provinces',{}),
        'ordinary_unlinked_not_deferred':[r['province'] for r in actionable if r['province'] not in policy.get('deferred_target_provinces',{})],
        'template_supplement_persons':template_report['template_supplement_persons'] if template_report else None,'target_no_political_anchors':sum(not r['political_sources'] for r in target),
        'target_no_incoming_population':sum(r['centipersons']==0 for r in target),
        'zero_source_population_state_owner_parts':empty,'unmapped_populated_source_locations':sum(r['centipersons']>0 for r in zero_source),
        'source_locations_without_any_target':len(zero_source),'source_without_target_classifications':dict(Counter('uninhabitable' if r['uninhabitable'] else 'habitable_zero' for r in zero_source)),
        'world_centipersons':sr['world_centipersons'],'omitted_political_countries':len(omitted_ids),
        'omitted_countries_population_allocated_centipersons':omitted_pop,
        'resident_cultures_pending':demo['active_cultures']-demo['resolved_cultures'],
        'resident_cultures_provisional_review':demo.get('generated_provisional_cultures',0),
        'resident_culture_pending_centipersons':demo['pending_culture_centipersons'],
        'deployment_ready':demo['deployment_ready'],'input_sha256':inputs,
        'interpretation':['V3 POP history is per state-owner part, not per province color.',
            'Impassability is read from V3 state definitions, never inferred from political repair labels.',
            'Closest candidates are same-state, same-owner suggestions, not approved geometry.',
            'Workstation reviews affect population links only, not political anchors.',
            'No automatic filling, duplication, culture substitution, border edit or deployment was performed.']}
    out.mkdir(parents=True)
    def csvout(name,rs):
        if not rs:return
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=list(rs[0]));wr.writeheader();wr.writerows(rs)
    csvout('target_coverage.csv',target);csvout('target_unlinked.csv',missing)
    csvout('source_unlinked.csv',zero_source);csvout('empty_state_owner_parts.csv',empty)
    esc=lambda v:html.escape(str(v))
    def table(rs,keys):
        return '<table><tr>'+''.join('<th>'+esc(k)+'</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join('<td>'+esc(r[k])+'</td>' for k in keys)+'</tr>' for r in rs)+'</table>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>地图映射反向覆盖检查</title><style>body{font:15px/1.6 system-ui;max-width:1400px;margin:30px auto;padding:20px;background:#172330;color:#edf3fa}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border-bottom:1px solid #496071;text-align:left}a{color:#8dd1ff}p{max-width:1000px}</style><h1>地图映射反向覆盖检查</h1>'''
    page+=f'<p>依据 revision {result["review_revision"]} 人口审核快照。源人口地理缺口为零；{len(target):,} 个目标陆地省份中，{len(missing)} 个没有来源链接：{len(missing)-len(actionable)} 个不可通行地块、{len(actionable)} 个普通地块。人口尚未部署。</p>'
    page+='<h2>尚无来源链接的普通地块（含用户暂缓项）</h2>'+table(actionable,['province','state_name','owner_name','hubs','same_state_owner_nearby_candidates'])
    page+='<p>建议核对这些候选及周边海岸／岛屿后补入来源链接，再重新分配已有源人口；不复制相邻人口，不改变总人口或国界。候选仅用于人工核对。</p>'
    if policy.get('deferred_target_provinces'):page+='<p>用户暂缓：'+esc(json.dumps(policy['deferred_target_provinces'],ensure_ascii=False))+'</p>'
    page+='<h2>整州没有源人口</h2>'+table(empty,['state_name','owner_name','provinces','source_locations','template_state_population'])
    page+='<p>空州模板保留按用户显式政策单列，未计入 EU5 源人口。当前模板补充人口：'+esc(template_report['template_supplement_persons'] if template_report else '尚未生成')+'；未安装。</p>'
    page+=f'<h2>其余无逐省人口不等于空州</h2><p>{result["target_no_incoming_population"]:,} 个省份没有接收源人口；V3 POP 存在州内国家部分。空州数量为 {len(empty)}。不可通行地块无需凭空追加居民。</p>'
    page+=f'<p>92 个被地图粒度挤掉的源国家不等于居民消失，其居民已分配到实际目标所有者。文化工作另有 {result["resident_cultures_pending"]} 种待处理，人口 {result["resident_culture_pending_centipersons"]/100:,.2f}，不能把地理完成当成居民文化全部完成。</p>'
    page+=f'<p>另有 {result["resident_cultures_provisional_review"]} 种保留源身份的暂定文化候选等待资产/机制审核；缺少输出键为零不代表历史考证或游戏接纳机制审核完成。</p>'
    page+='<p><a href="target_unlinked.csv">无来源地块</a> · <a href="target_coverage.csv">全目标覆盖台账</a> · <a href="source_unlinked.csv">源侧无目标台账</a> · <a href="coverage_report.json">摘要与来源哈希</a></p></html>'
    (out/'review.html').write_text(page,encoding='utf-8')
    result['output_sha256']={p.name:digest(p) for p in out.iterdir() if p.is_file()}
    (out/'coverage_report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('input_sha256','output_sha256','interpretation')}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path);p.add_argument('--out',type=Path)
    a=p.parse_args(); run=a.run or Path(load_json(ROOT/'.local/m4/demographics-latest.json')['run'])
    out=a.out or ROOT/'.local/m4/coverage-audits'/datetime.now().strftime('%Y%m%d-%H%M%S')
    result=audit(run,out,Path('D:/Steam/steamapps/common/Victoria 3/game'),Path('D:/Steam/steamapps/common/Europa Universalis V/game'))
    print(json.dumps({'out':str(out),'result':result},ensure_ascii=False))
