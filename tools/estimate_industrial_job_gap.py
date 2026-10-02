"""Read-only, state-local factory-equivalent scenarios on calibrated population."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from economy_development import manufacturing_kinds
from economy_model import Target, building_rows
from m3_world import digest

ROOT = Path(__file__).resolve().parents[1]
GAME = Path('D:/Steam/steamapps/common/Victoria 3/game')
# Geographic reporting slice, not a rule granting industry to every Italian state.
ITALIAN_PENINSULA_ISLANDS = {'STATE_'+s for s in (
    'ABRUZZO APULIA CALABRIA CAMPANIA EMILIA LAZIO LOMBARDY PIEDMONT ROMAGNA '
    'SARDINIA SICILY TUSCANY UMBRIA VENETIA').split()}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def estimate(package, output):
    manifest = read(package/'package_report.json')
    assert manifest.get('population_calibrated')
    mod = Path(manifest['mod_directory'])
    building_path = mod/'common/history/buildings/00_eu5_world.txt'
    assert digest(building_path) == manifest['output_sha256']['common/history/buildings/00_eu5_world.txt']
    employment_path = package/'employment.json'
    calibration_path = package/'population_calibration.json'
    profile_path = ROOT/'.local/economy/geography-007-ownership-reference/development.json'
    profiles = read(profile_path)['countries']
    calibrated = {(r['state'], r['country']): r for r in read(calibration_path)['states']}
    target = Target(GAME)
    kinds = manufacturing_kinds(target)
    local = defaultdict(Counter)
    national = defaultdict(Counter)
    for r in building_rows(building_path):
        if r['building'] not in kinds:
            continue
        # Employment is a PM level/workforce modifier; technology throughput does
        # not multiply employment (see Target.coefficients).
        per_level = target.coefficients(r['building'], r['pms'], set())['jobs']
        for count in (local[r['state'], r['owner']], national[r['owner']]):
            count['levels'] += r['levels']
            count['jobs'] += per_level*r['levels']
    states = []
    for r in read(employment_path):
        s, t = r['state'], r['country']
        a = calibrated[s,t]
        stock = national[t]
        # Countries with no factories get only a clearly marked comparison unit.
        per_level = stock['jobs']/stock['levels'] if stock['jobs'] > 0 else 5000
        capacity = a['planning_worker_capacity']
        workforce = r['population']*.25
        # Zero-unemployment scenario is intentionally distinct from the approved
        # 15% development reserve, where capacity need only reach workforce/1.15.
        reserve_gap = max(0, workforce/1.15-capacity)
        full_gap = r['capacity_gap_full_staffing']
        safety_gap = r['capacity_gap_safety_staffing']
        row = {'state':s, 'country':t, 'population':r['population'],
               'existing_manufacturing_levels':local[s,t]['levels'],
               'equivalent_jobs_per_factory_level':per_level,
               'coefficient_basis':'current_national_manufacturing_mix' if stock['jobs'] else '5000_job_comparison_unit_only',
               'full_staffing_worker_gap':full_gap, 'planning_worker_gap':safety_gap,
               'extra_levels_full_staffing':math.ceil(full_gap/per_level),
               'extra_levels_75_percent_staffing':math.ceil(safety_gap/(per_level*.75)),
               'extra_levels_75_percent_keep_15_percent_reserve':math.ceil(reserve_gap/(per_level*.75)),
               'source_development':r.get('commercial_agriculture_policy',{}).get('population_weighted_development'),
               'italian_peninsula_and_main_islands':t=='ITA' and s in ITALIAN_PENINSULA_ISLANDS}
        states.append(row)
    summed = ['population','existing_manufacturing_levels','full_staffing_worker_gap','planning_worker_gap',
              'extra_levels_full_staffing','extra_levels_75_percent_staffing','extra_levels_75_percent_keep_15_percent_reserve']
    def aggregate(rows):
        return {k:sum(r[k] for r in rows) for k in summed}
    countries = {}
    for t in sorted({r['country'] for r in states}):
        p = profiles.get(t,{})
        countries[t] = {**aggregate([r for r in states if r['country']==t]),
            'name':p.get('name',t), 'source_relative_industrial_intensity':p.get('source_relative_industrial_intensity'),
            'source_development_description':p.get('development_description'), 'source_scope':p.get('scope')}
    italy = {'peninsula_and_main_islands':aggregate([r for r in states if r['italian_peninsula_and_main_islands']]),
             'other_italian_territories':aggregate([r for r in states if r['country']=='ITA' and not r['italian_peninsula_and_main_islands']])}
    result = {'package':str(package), 'version':manifest['version'],
        'method':{'workforce_share':.25,'planning_staffing':.75,'reserve_over_capacity':.15,
            'rounding':'ceil within every state-country part, then sum; no inter-state relocation',
            'unit':'additional manufacturing building levels, not building stacks',
            'limitations':['Static opening capacity estimate, not observed unemployment or profitability.',
                'No supply-chain, railway, port, urban-center, owner-building or construction jobs added.',
                'No consumption/price/qualification/market-access simulation; not an executable investment plan.',
                'High country source intensity is screening evidence only, not permission to industrialize every local desert or colony.',
                'Technology-dependent active PM employment is used; productivity/throughput alone does not increase hiring.']},
        'input_sha256':{str(p):digest(p) for p in [building_path,employment_path,calibration_path,profile_path]},
        'countries':countries,'italy_geographic_slices':italy,'states':states}
    output.mkdir(parents=True,exist_ok=True)
    (output/'estimate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    selected = ['ITA','BOH','SWE','SPA','E8G','E4O','E4P','ENG','AUS']
    lines = ['工业就业缺口估算（人口校准后；所有数量均为工厂等级）',
             '按州分别向上取整再汇总；当前上述国家的实际制造业生产方式均为每级5000岗位。',
             '国家 | 已有制造业等级 | 满员补足 | 75%就业补足 | 75%就业且保留15%余量',
             *[f"{countries[t]['name']} ({t}) | "+' | '.join(str(countries[t][k]) for k in summed if k in (
                'existing_manufacturing_levels','extra_levels_full_staffing','extra_levels_75_percent_staffing','extra_levels_75_percent_keep_15_percent_reserve')) for t in selected],
             '', '意大利地理拆分：',json.dumps(italy,ensure_ascii=False,indent=2),
             '', '只估算厂内直接就业。配套矿山、铁路、港口和城市服务既提供岗位也消耗资源；本表没有假定额外比例。',
             '满员与75%两栏同时改变现有正规建筑和新增工厂就业率，因此不是仅将工厂数量除以0.75。',
             '国家汇总不能消除跨州错配。意大利其他领地包含欧洲其他地区与海外领地，不能统一当成殖民地。',
             '保留15%余量指劳动力=岗位容量×1.15，对应失业率约13.0%，不是总劳动力的15%。',
             '这是岗位容量情景，不保证市场能消化新增产品，也不等于已经批准或实装这些工厂。']
    (output/'简表.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'countries':{t:countries[t] for t in selected},'italy':italy},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    estimate(args.package,args.output)
