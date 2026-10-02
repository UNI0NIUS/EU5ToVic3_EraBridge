"""Read installed M5 colonial institutions and evidence; never change game setup."""
from collections import Counter, defaultdict
from datetime import datetime
import csv
import html
import json
from pathlib import Path
from types import SimpleNamespace

from pdx_text import root, Object
from extract_m3_politics import fields, sequence
from deploy_political_rules import countries
from complete_economy import active_laws
from economy_model import definitions
from m3_world import digest
from package_m4_population_test import parse_pops, GAME

ROOT = Path(__file__).resolve().parents[1]
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    pointer = ROOT/'.local/m5/installation-latest.json'
    install = read(pointer)
    package = Path(install['package'])
    mod = Path(install['target'])
    manifest = read(package/'package_report.json')
    # Hash all installed assets before and after this read-only audit.
    expected = manifest['output_sha256']
    before = {rel: digest(mod/rel) for rel in expected}
    assert before == expected, 'Installed baseline differs from package'
    political = read(Path(manifest['political_run'])/'conversion_report.json')
    owners = read(Path(manifest['political_run'])/'province_owners.json')
    source_path = ROOT/'.local/m3/politics.json'
    source = read(source_path)
    assert source['source_sha256'] == political['source_sha256']
    review_path = ROOT/'.local/politics/review-20261001-v02-release/report.json'
    review = read(review_path)
    assert review['source_sha256'] == source['source_sha256']
    cache_path = ROOT/'.local/m3/cache/tribal_land_edges.json'
    cache = read(cache_path)
    map_paths = [GAME/'map_data'/n for n in ['provinces.png','adjacencies.csv','default.map']]
    assert cache['sha256'] == [digest(p) for p in map_paths]
    edges = [(a[0]+a[1:].upper(),b[0]+b[1:].upper()) for a,b in cache['edges']]
    sea = set()
    with map_paths[1].open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f, delimiter=';'):
            if r['Type']=='sea': sea.add(tuple(sorted(('x'+r['From'][1:].upper(),'x'+r['To'][1:].upper()))))
    edges = [(a,b) for a,b in edges if tuple(sorted((a,b))) not in sea]
    flat = {p:(s,t) for s,ps in owners.items() for p,t in ps.items()}
    countries_info = political['countries']
    decentralized = {t for t,c in countries_info.items() if c['country_type']=='decentralized'}
    neighbours = defaultdict(set)
    frontier_states = defaultdict(set)
    passable_neighbours = defaultdict(set)
    blocked = {p for f in definitions(GAME/'map_data/state_regions').values() for p in sequence(f.get('impassable'))}
    for a,b in edges:
        if a not in flat or b not in flat: continue
        for p,q in ((a,b),(b,a)):
            s,t = flat[p]; ss,tt = flat[q]
            if t != tt and tt in decentralized:
                neighbours[t].add(tt); frontier_states[t].add(s)
                if p not in blocked and q not in blocked: passable_neighbours[t].add(tt)
    state_bodies = fields(root((mod/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['STATES']
    homeland = defaultdict(set); incorporation = {}; parsed_owners = {}
    for name,body in state_bodies.entries():
        if not isinstance(body,Object): continue
        state = name.removeprefix('s:')
        for k,v in body.entries():
            if k=='add_homeland': homeland[state].add(v.removeprefix('cu:'))
            elif k=='create_state':
                f=fields(v); tag=f['country'].removeprefix('c:')
                incorporation[state,tag]=f.get('state_type')
                for province in sequence(f['owned_provinces']): parsed_owners[province]=(state,tag)
    assert parsed_owners == flat, 'Political owner ledger differs from installed state history'
    population=Counter(); unincorporated=Counter()
    for (s,t,c,r),n in parse_pops(mod/'common/history/pops/00_eu5_world.txt').items():
        population[t]+=n
        if incorporation[s,t]=='unincorporated': unincorporated[t]+=n
    subjects={r['target_subject']:r for r in political['subjects']}
    children=defaultdict(list)
    for r in political['subjects']:
        if r['type'] in ('colonial_nation','trade_company'): children[r['target_overlord']].append(r['target_subject'])
    target=SimpleNamespace(game=GAME)
    lawdefs=definitions(GAME/'common/laws')
    bodies=countries((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig'))
    rows=[]
    for tag,body in sorted(bodies.items()):
        info=countries_info[tag]
        laws=active_laws(body,target,info)
        by_group={lawdefs[l]['group']:l for l in laws}
        law=by_group.get('lawgroup_colonization','template_unspecified')
        active=law not in ('law_no_colonial_affairs','template_unspecified')
        institutions={fields(v)['institution']:int(fields(v)['level']) for k,v in body.entries() if k=='set_institution_investment_level'}
        techs={v for k,v in body.entries() if k=='add_technology_researched'}
        policies={k:dict(v).get('object') for k,v in source['countries'].get(info.get('source_id'),{}).get('laws',[])}
        entry=review['countries'].get(tag,{}).get('laws',{}).get('lawgroup_colonization',{})
        source_colonies=[s for s in source['subjects'] if s['overlord']==info.get('source_id') and s['type'] in ('colonial_nation','trade_company')]
        building_companies=[s['subject'] for s in source_colonies if source['countries'].get(s['subject'],{}).get('type')=='building']
        homes=[s for s in frontier_states[tag] if homeland[s].intersection(info.get('cultures',[info.get('culture')]))]
        flags=[]
        if law=='law_frontier_colonization':
            if not neighbours[tag]: flags.append('no_direct_land_frontier_screen')
            elif not passable_neighbours[tag]: flags.append('impassable_only_frontier_screen')
            if info['country_type'] not in ('colonial','company') and not homes: flags.append('homeland_frontier_not_confirmed')
        if law=='law_colonial_exploitation' and policies.get('colonial_policy')=='trade_colonies': flags.append('trade_policy_not_exploitation_equivalence')
        if active and source_colonies and not children[tag] and len(building_companies)==len(source_colonies): flags.append('overlord_evidence_building_companies_only')
        if info['country_type']=='colonial' and by_group.get('lawgroup_migration')=='law_closed_borders': flags.append('closed_migration')
        if active and not institutions.get('institution_colonial_affairs'): flags.append('missing_explicit_institution')
        if active and 'colonization' not in techs: flags.append('missing_explicit_colonization_tech')
        if info['country_type']=='decentralized' and active: flags.append('decentralized_active_colonization')
        rows.append(dict(tag=tag,name=info.get('name_simp_chinese',tag),country_type=info['country_type'],
            capital=info['capital'],law=law,institution_level=institutions.get('institution_colonial_affairs',0),
            governance=by_group.get('lawgroup_governance_principles'),migration=by_group.get('lawgroup_migration'),
            overlord=subjects.get(tag,{}).get('target_overlord'),colonial_subjects=children[tag],
            source_building_companies=building_companies,
            population=population[tag],unincorporated_population=unincorporated[tag],
            source_colonial_policy=policies.get('colonial_policy'),source_native_policy=policies.get('native_policy'),
            source_basis=entry.get('reason','original uncolonized template'),
            direct_land_decentralized_neighbours=sorted(neighbours[tag]),
            passable_land_decentralized_neighbours=sorted(passable_neighbours[tag]),
            homeland_frontier_states_screen=sorted(homes),flags=flags))
    assert len(rows)==len(countries_info)
    summary=dict(countries=len(rows),population=sum(population.values()),
        laws=dict(Counter(r['law'] for r in rows)),
        colonial_laws=dict(Counter(r['law'] for r in rows if r['country_type']=='colonial')),
        institutions=dict(Counter(r['institution_level'] for r in rows if r['law'] not in ('law_no_colonial_affairs','template_unspecified'))),
        flags=dict(Counter(f for r in rows for f in r['flags'])),
        colonial_source_policies=dict(Counter(str(r['source_colonial_policy']) for r in rows if r['country_type']=='colonial')))
    out=ROOT/'.local/m5/colonial-law-audit'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    evidence_paths=[pointer,source_path,review_path,cache_path,*map_paths,
        GAME/'common/laws/01_colonial_affairs.txt',GAME/'common/laws/00_governance_principles.txt',
        GAME/'common/institutions/00_institutions.txt',GAME/'common/defines/00_defines.txt',
        GAME/'localization/english/interfaces_l_english.yml',
        Path('D:/Steam/steamapps/common/Europa Universalis V/game/in_game/common/laws/01_common.txt')]
    after={rel:digest(mod/rel) for rel in expected}
    assert before==after and read(pointer)==install, 'Baseline changed during audit'
    report=dict(status='read_only_design_audit',version=install['version'],package=str(package),summary=summary,
        limitations=['Direct province land adjacency is a screening measure, not evaluation of engine can_enact or can_colonize.',
            'Straits and the engine limited sea path are excluded; no-neighbour does not prove inability to colonize.',
            'Homeland screen uses current province border states, not a complete engine state-neighbour evaluator.',
            'Existing enactment need not satisfy new-enactment triggers after a frontier closes.',
            'No runtime interest/claims/charters/malaria/capital connectivity or bureaucracy budget simulated.',
            'No setup, source policy, population, homeland or installed files changed.'],
        input_sha256={str(p):digest(p) for p in evidence_paths},installed_files_verified=len(after),countries=rows)
    dump(out/'audit.json',report)
    with (out/'countries.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in r.items()} for r in rows)
    columns=['tag','name','country_type','law','institution_level','overlord','source_colonial_policy','source_native_policy','population','unincorporated_population','direct_land_decentralized_neighbours','flags']
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(r[k] if r[k] is not None else ''))+'</td>' for k in columns)+'</tr>' for r in rows)
    page='''<!doctype html><meta charset="utf-8"><title>M5 殖民法律检查</title>
<style>body{font:16px system-ui;background:#10202d;color:#edf2f7;margin:28px}a{color:#9cd}td,th{padding:9px;border-bottom:1px solid #435361;text-align:left}table{border-collapse:collapse}input{padding:12px;width:70%}pre{white-space:pre-wrap}</style>
<h1>M5 殖民法律检查 · 仅审计与设计</h1><p>本机固定版本 V3 1.13.11；当前安装 test25。未修改任何游戏设定。</p>
<p>殖民行政政体、殖民事务法律、附属关系与州整合状态分开判断。陆地邻接只是筛查，排除了海峡，不能据此宣布游戏内必定能／不能殖民。殖民剥削会影响本国未整合州的生产与工资。</p>
<p><a href="../../../../docs/M5_COLONIAL_LAW_DESIGN.md">设计建议与限制</a> · <a href="countries.csv">逐国 CSV</a> · <a href="audit.json">证据 JSON</a></p><pre>'''+html.escape(json.dumps(summary,ensure_ascii=False,indent=2))+'''</pre>
<input aria-label="筛选国家" placeholder="搜索 TAG、国家、法律、标记" oninput="document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(this.value.toLowerCase()))">
<table><thead><tr>'''+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr></thead><tbody>'+table+'</tbody></table>'
    (out/'index.html').write_text(page,encoding='utf-8')
    dump(ROOT/'.local/m5/colonial-law-audit-latest.json',dict(run=str(out),summary=summary,status=report['status']))
    print(json.dumps(dict(run=str(out),summary=summary),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
