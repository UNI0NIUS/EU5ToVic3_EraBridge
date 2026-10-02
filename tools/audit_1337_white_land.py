"""Compare actual 1337 unowned source locations with the final campaign map.

This audits the installed campaign against an independent opening-save import;
it is not a claim to have converted a second campaign end to end.
"""
from pathlib import Path
from collections import Counter, defaultdict
import csv, json, argparse
from m3_world import World, digest
from package_m5_uncolonized import ROOT, GAME, read
from package_m4_population_test import rows


def audit(package, out):
    package, out = Path(package), Path(out)
    pr = read(package/'package_report.json')
    report = read(Path(pr['political_run'])/'conversion_report.json')
    owners = read(Path(pr['political_run'])/'province_owners.json')
    stage = Path(pr['demographic_run'])/'staging'
    opening_path = ROOT/'.local/m1/start-report/import_report.json'
    opening = read(opening_path)
    assert opening['date'] == '1337.4.1' and not opening['errors']
    source_path = ROOT/'.local/m1/runs/20260930-092431-main-c1d8df65/report/import_report.json'
    current = read(source_path)
    w = World(GAME,Path('D:/Steam/steamapps/common/Europa Universalis V/game'),current,
              read(ROOT/'.local/m3/politics-with-cultures.json'),read(ROOT/'config/personal/m3_world.json'),ROOT/'.local/m3/cache')
    w.geometry()
    white = {r['name']:r for r in opening['locations'] if not r['owner']}
    assert white.keys() <= w.locations.keys()
    flat = {p:(s,t) for s,ps in owners.items() for p,t in ps.items()}
    assert set(flat) == set(w.province_state) and all(t in report['countries'] for s,t in flat.values())
    cross = {r['source_location']:r for r in rows(stage/'location_crosswalk.csv')}
    province_pop = defaultdict(Counter)
    for r in rows(stage/'province_population_draft.csv'):
        province_pop[r['target_province']][r['source_owner']] += int(r['centipersons'])
    settled = {r['location'] for r in report.get('frontier_finalization',{}).get('classifications',[])
               if r['classification']=='settler_majority_active_charter'}
    source_rows = []
    for n, old in sorted(white.items()):
        now = w.locations[n]
        kind = ('water_or_nonownable' if n in w.uninhabitable else
                'now_formally_owned' if now['owner'] else
                'active_settler_majority_charter' if n in settled else
                'still_unowned_populated' if float(now['population_persons']) else 'still_unowned_empty')
        links = [p for p in cross[n]['target_provinces'].split(';') if p]
        source_rows.append({'location':n,'classification':kind,'owner_1337':old['owner'],
                            'owner_current_source':now['owner'],'source_persons':now['population_persons'],
                            'target_provinces':';'.join(links),'target_owners':';'.join(sorted({flat[p][1] for p in links}))})
    missing = []
    for r in report['vanilla_fallbacks']:
        p,s = r['province'],r['state'];t = owners[s][p]
        if r['rule'] != 'uncolonized_vanilla' or report['countries'][t].get('generated_uncolonized'):
            continue
        names = w.mapping.get(p,[])
        if any(n in settled for n in names):
            continue
        if province_pop[p] and set(province_pop[p]) == {'0'}:
            missing.append(dict(r, current_owner=t, reason='populated_source_unowned_still_using_nontribal_fallback'))
    fallback_counts = Counter(r['state'] for r in report['vanilla_fallbacks'] if r['rule']=='unmapped_vanilla')
    linked = {p for r in cross.values() for p in r['target_provinces'].split(';') if p}
    from build_m2_prototype import strings
    from m3_world import fields, province
    impassable = {province(p) for d in w.defs.values() if 'impassable' in fields(d) for p in strings(fields(d)['impassable'])}
    unlinked = [{'province':p,'state':flat[p][0],'owner':flat[p][1],'impassable':p in impassable}
                for p in sorted(set(flat)-linked)]
    result = {'status':'passed_with_documented_template_and_mapping_exceptions' if not missing else 'review_required',
              'opening_date':opening['date'],'current_source_date':current['date'],
              'source_white_locations':len(white),'habitable_white_locations':sum(n not in w.uninhabitable for n in white),
              'classification_counts':dict(Counter(r['classification'] for r in source_rows)),
              'target_land_provinces':len(flat),'target_ownership_holes':0,
              'unresolved_populated_native_fallbacks':missing,
              'whole_state_original_fallbacks':dict(fallback_counts),
              'template_exceptions':'ACRE and NAURU retain previously user-approved empty-source templates; not newly inferred ownership.',
              'target_without_population_links':len(unlinked),
              'ordinary_unlinked_targets':[r for r in unlinked if not r['impassable']],
              'all_populated_source_locations_allocated':all(int(r['pending_centipersons'])==0 for r in cross.values()),
              'yakutsk_remaining_russian_provinces':[p for p,t in owners['STATE_YAKUTSK'].items() if t=='RUS'],
              'island_reviews':report.get('frontier_finalization',{}).get('reviewed_islands',[]),
              'limitations':['1337 white land is a baseline for comparison, not evidence of 1780 sovereignty.',
                            'Inherited empty terrain without direct source evidence remains inference; this does not verify every border or a generic second-save conversion.'],
              'input_sha256':{str(p):digest(p) for p in [opening_path,source_path,Path(pr['political_run'])/'province_owners.json',stage/'province_population_draft.csv',stage/'location_crosswalk.csv',Path(__file__)]}}
    out.mkdir(parents=True,exist_ok=True)
    for name,data in [('source_white_locations.csv',source_rows),('target_unlinked.csv',unlinked)]:
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]) if data else []);writer.writeheader();writer.writerows(data)
    (out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=audit(a.package,a.out);print(json.dumps({k:v for k,v in r.items() if k not in ['input_sha256','island_reviews']},ensure_ascii=False,indent=2))
