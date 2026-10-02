"""Small, post-edit building proposals for one selected province's estimated needs."""
import math
from collections import Counter
from converter_edits import materialize
from converter_project import apportion
from economy_geography import fixed_resource_kinds
from extract_m3_politics import fields,sequence


def proposal(world,options,operations,province,building,goal='food',maximum=100):
    if goal not in ('food','unemployment'):raise ValueError('未知补建目标')
    if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=1000:raise ValueError('单次补建上限须为 1–1000 的整数')
    before=world.preview(options,operations)
    row=next((r for r in before['rows'] if province in r['provinces']),None)
    if row is None:raise ValueError('所选地块已不存在，请重新选择')
    view=materialize(world,operations);target=view.target;s,t=row['state'],row['country']
    definition=target.buildings.get(building)
    if definition is None or building.startswith('building_subsistence'):raise ValueError('请选择可补建的生产建筑')
    if not set(sequence(definition.get('unlocking_technologies')))<=view.techs[t]:raise ValueError('所属国家尚未解锁该建筑')
    for condition in ('potential','possible','allow'):
        if condition not in definition:continue
        if fields(definition[condition])=={'is_sea_adjacent':'yes'}:
            if not set(row['provinces']) & view.coastal_provinces:raise ValueError('该建筑需要所属地区有沿海地块')
        else:raise ValueError('该建筑还有特殊建造条件，请手动核对后调整')
    methods=target.select(building,view.techs[t],set(),view.laws[t])
    existing=[b for b in view.buildings if (b['state'],b['owner'],b['building'])==(s,t,building)]
    if any(b.get('guards') for b in existing):raise ValueError('条件建筑不能自动补建')
    if existing:methods=target.complete_methods(building,existing[0]['pms'],methods)
    coeff=target.coefficients(building,methods,view.techs[t])
    if not coeff['outputs'] or coeff['jobs']<=0:raise ValueError('补建计算仅支持有商品产出和岗位的生产建筑')
    n=row['province_count'];current=row['buildings'].get(building,0)
    room=min(maximum,100000-current)
    # A province has no stored population in V3; use its share of this region.
    workforce=row['population']*options['workforce_share']
    staffed=coeff['jobs']*options['staffing']
    if staffed<=0:raise ValueError('招聘比例为零，不能估算补建')
    room=min(room,max(0,math.floor((workforce-row['formal_jobs']*options['staffing'])/staffed)))
    if building in view.arable_kinds:
        if building not in sequence(target.states[s].get('arable_resources')):raise ValueError('本州不适合该农业建筑')
        room=min(room,max(0,row['arable']-sum(v for k,v in row['buildings'].items() if k in view.arable_kinds)))
    elif building in fixed_resource_kinds(target):
        weights=Counter(view.owners[s].values())
        limit=apportion(int(fields(target.states[s].get('capped_resources')).get(building,0)),weights).get(t,0)
        room=min(room,max(0,limit-current))
    else:
        group=definition.get('building_group');seen=set()
        while group and group not in seen:
            seen.add(group);group=target.building_groups.get(group,{}).get('parent_group')
        if 'bg_manufacturing' not in seen or definition.get('buildable')=='no':
            raise ValueError('自动估算支持农业、固定资源与制造业；该建筑的特殊条件请手动调整')
    if room<1:raise ValueError('当前劳动力、耕地或资源容量不足，不能建议新增一级该建筑')
    def deficit(r):
        if goal=='food':return None if r['food_shortfall'] is None else r['food_demand']*r['food_shortfall']
        return None if r['job_capacity'] is None else max(0,r['population']*options['workforce_share']-r['job_capacity'])
    initial=deficit(row)
    if initial is None:raise ValueError('需求数据未知，不能自动计算补建')
    if initial<=1e-9:raise ValueError('当前地区在所选指标上没有缺口')
    def preview_added(levels):
        op=dict(kind='building',state=s,country=t,levels={building:current+levels},supplement_province=province)
        preview=world.preview(options,operations+[op]);r=next(r for r in preview['rows'] if r['id']==row['id'])
        return op,r
    _,trial=preview_added(1);after_one=deficit(trial)
    improvement=initial-after_one if after_one is not None else 0
    if improvement<=1e-9:raise ValueError('新增一级未改善所选缺口（已计入自给农业占地、市场及基础设施影响）；请换一种建筑或调整生产方式')
    wanted=max(1,math.ceil(initial/n/improvement));added=min(room,wanted)
    op,after=preview_added(added)
    final=deficit(after)
    if final is None or final>=initial:raise ValueError('补建后的重新计算未改善缺口，未生成修改；请减少数量或换一种建筑')
    return dict(operation=op,province=province,building=building,goal=goal,added=added,wanted=wanted,
        limited=added<wanted,population_share=row['population']/n,need_share=initial/n,
        regional_before=initial,regional_after=final,before=row,after=after,
        notes=['按整合后地区的人口与缺口均分到地块估算，不是历史地块人口。',
               '用新增一级的边际改善估算数量，再重新计算整个市场；这不是完整供应链或盈利保证。',
               '建筑最终记入所选地块当前所属地区；重复计算会使用最新数据。'])
