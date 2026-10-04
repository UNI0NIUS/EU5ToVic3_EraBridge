"""Explain how whole-state land changes affect one region's job capacity."""
from converter_i18n import Message
import math
from converter_edits import materialize
from converter_project import apportion


def advice(world,options,operations,region_id):
    preview=world.preview(options,operations)
    row=next((r for r in preview['rows'] if r['id']==region_id),None)
    if row is None:raise ValueError(Message('所选地区已变化，请重新打开编辑器'))
    view=materialize(world,operations)
    return calculate(view,options,row,[r for r in preview['rows'] if r['state']==row['state']])


def calculate(view,options,row,parts):
    if row['job_capacity'] is None:raise ValueError(Message('该地区岗位容量未知，暂不能估算所需耕地'))
    s,t=row['state'],row['country'];target=view.target
    kind=target.states[s].get('subsistence_building','building_subsistence_farm')
    methods=target.select(kind,view.techs[t],set(),view.laws[t])
    jobs=target.coefficients(kind,methods,view.techs[t])['jobs']
    if jobs<=0:raise ValueError(Message('自给农业未提供可计算岗位，添加耕地无法按此模型缓解失业'))
    weights={r['country']:r['province_count'] for r in parts};province_total=sum(weights.values())
    farms=sum(n for k,n in row['buildings'].items() if k in view.arable_kinds)
    workforce=row['population']*options['workforce_share'];formal=row['formal_jobs']*options['staffing']
    current=row['state_arable'];multiplier=options['arable_multiplier'];threshold=options['unemployment_threshold']
    def recommendation(full):
        target_jobs=workforce if full else workforce*(1-threshold)
        satisfied=row['job_capacity']>=target_jobs if full else row['job_capacity']>target_jobs or workforce==0
        if satisfied:base=current
        else:
            missing=max(0,target_jobs-formal)
            subsistence=math.ceil(missing/jobs) if full else math.floor(missing/jobs)+1
            required=farms+subsistence
            # Hamilton allocations can exhibit the Alabama paradox. Use a quota
            # whose FLOOR guarantees this part's need instead of binary-searching
            # an allocation that is not monotonic as whole-state land changes.
            total=math.ceil(required*province_total/weights[t])
            base=max(current,math.ceil(total/multiplier))
        if base>1000000:return dict(available=False,reason=Message('所需整州基础耕地超过编辑器上限 1,000,000'))
        total=math.floor(base*multiplier+.5);local=apportion(total,weights).get(t,0)
        capacity=formal+max(0,local-farms)*jobs
        unemployment=max(0,1-capacity/workforce) if workforce else 0
        return dict(available=True,state_base=base,added_base=base-current,state_effective=total,
                    region_arable=local,added_region_arable=local-row['arable'],job_capacity=capacity,
                    unemployment=unemployment,already_satisfied=satisfied)
    return dict(region=row['id'],state=s,country=t,current_state_base=current,current_region_arable=row['arable'],
                workforce=workforce,formal_jobs=formal,agriculture_levels=farms,jobs_per_arable=jobs,
                unemployment=row['estimated_unemployment'],threshold=threshold,arable_multiplier=multiplier,
                province_share=weights[t]/province_total,relief=recommendation(False),full=recommendation(True))


def plan_bulk(world,options,operations,region_ids,max_multiplier=2,mode='relief'):
    """One frozen edit per state, bounded against its current pre-batch base land."""
    from collections import defaultdict
    if isinstance(max_multiplier,bool) or not isinstance(max_multiplier,(int,float)) or not math.isfinite(max_multiplier) or not 1<max_multiplier<=100:raise ValueError(Message('倍率上限须大于 1 且不超过 100'))
    if mode not in ('relief','full'):raise ValueError(Message('未知补耕地目标'))
    preview=world.preview(options,operations);rows={r['id']:r for r in preview['rows']}
    selected=set(region_ids)
    if not selected or not selected<=rows.keys():raise ValueError(Message('请选择仍存在的地区'))
    view=materialize(world,operations);by_state=defaultdict(list)
    for row in rows.values():by_state[row['state']].append(row)
    targets={};skipped=[];limited=[];affected=[]
    for key in sorted(selected):
        row=rows[key]
        if 'unemployment' not in row['risks']:continue
        try:r=calculate(view,options,row,by_state[row['state']])[mode]
        except (ValueError,KeyError) as e:skipped.append(dict(region=key,reason=str(e)));continue
        before=row['state_arable'];cap=min(1000000,math.floor(before*max_multiplier))
        if not before:
            skipped.append(dict(region=key,reason=Message('当前整州耕地为 0，倍率上限也为 0；请先手动设置基础耕地')));continue
        desired=r.get('state_base',1000001);value=min(desired,cap)
        if desired>cap:limited.append(key)
        if value<=before:continue
        affected.append(key)
        item=targets.setdefault(row['state'],dict(state=row['state'],before=before,value=value,cap=cap))
        item['value']=max(item['value'],value)
    if not targets:raise ValueError(Message('没有可增加的耕地：所选地区可能已无严重失业、岗位未知，或倍率上限不允许增加'))
    return dict(kind='arable_bulk',mode=mode,max_multiplier=max_multiplier,targets=list(targets.values()),regions=affected,limited=limited,skipped=skipped)
