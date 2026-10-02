"""Audit inherited native military bonuses against installed V3 rules."""
from build_fresh_1337 import *

def build():
 mod=RUN/'base/eu5_m5_1337_test';m=read(RUN/'political/conversion_report.json');hist={k[2:]:o.text() for k,o in objects(root((mod/'common/history/countries/00_eu5_world.txt').read_text(encoding='utf-8-sig')).fields()['COUNTRIES'])}
 pop=defaultdict(Counter)
 for r in rows(RUN/'demographic/demographics/resident_population_groups.csv'):pop[r['owner']][r['state']]+=int(r['preview_integer_persons'])
 modifiers={k:fields(o) for k,o in objects(root((GAME/'common/static_modifiers/06_conscription_modifiers.txt').read_text(encoding='utf-8-sig')))}
 law=dict(objects(root((GAME/'common/laws/00_army_model.txt').read_text(encoding='utf-8-sig'))))['law_peasant_levies'].fields()['modifier'].fields();base=float(law['state_conscription_rate_add']);cap=int(law['state_building_conscription_center_max_level_add'])
 define=(GAME/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig');divisor=int(re.search(r'CONSCRIPTION_CENTER_LEVEL_POPULATION_DIVISOR\s*=\s*(\d+)',define)[1]);result=[]
 for tag,c in m['countries'].items():
  if not c.get('generated_uncolonized'):continue
  effects=re.findall(r'effect_native_conscription_(\d+)',hist[tag]);extra=sum(float(modifiers['native_conscription_'+n]['state_conscription_rate_add']) for n in effects)
  row=dict(tag=tag,culture=c['culture'],source_template=c['template'],provinces=c['provinces'],population=sum(pop[tag].values()),populated_states=sum(n>0 for n in pop[tag].values()),template_conscription_effects=effects,base_law_rate=base,inherited_bonus_rate=extra,
       before_ceiling_estimate=sum(min(cap,int(n*(base+extra)/divisor)) for n in pop[tag].values()),after_ceiling_estimate=sum(min(cap,int(n*base/divisor)) for n in pop[tag].values()),states=dict(pop[tag]))
  result.append(row)
 result.sort(key=lambda r:-r['provinces'])
 report=dict(status='static_risk_audit_not_runtime_battalion_count',game_version='1.13.11',affected_generated_countries=sum(bool(r['template_conscription_effects']) for r in result),countries=result,rule='Remove inherited country-specific native_conscription effects only for generated source-unowned tribes; retain ordinary laws, original country boundaries, population and vanilla explicit-template countries.',estimate_limit='All residents treated as potentially eligible civilian population. Peasant eligibility, runtime workforce, modifiers, recruitment and equipment can lower actual field strength. Per-state floors and law caps are a static estimate, not an engine readback.',broad_culture_warning='Siberian and Amazonian are reviewed broad game categories containing multiple source identities. Connected country grouping preserves the requested mapped-culture rule; it must not be presented as historical political unity.')
 out=ROOT/'outputs/1337-supervised-terrain-20261002';write(out/'native_colonization_audit.json',report)
 text(out/'native_colonization_audit.md','# 1337 松散部落与殖民机制审查\n\n本机 V3 1.13.11。地图面积不会直接变成征召兵；全国动员可汇集各州人口。殖民速度另受殖民者制度、当地人口和州省份数量等规则影响。小于10省的部落还会获得更高的紧张度增长，因此机械拆小并不一定让殖民更容易。\n\n发现 '+str(report['affected_generated_countries'])+' 个新生成部落继承了模板国家专属征召加成。该加成没有源军事证据，予以排除；不调整原版全局数值、不凭地图面积强拆民族国家。\n\n| 原候选 TAG | 文化宽类 | 人口 | 地块 | 旧额外征召率 | 修正前潜在营估算 | 修正后潜在营估算 |\n|---|---|---:|---:|---:|---:|---:|\n'+''.join(f"| {r['tag']} | {r['culture']} | {r['population']:,} | {r['provinces']} | {r['inherited_bonus_rate']:.0%} | {r['before_ceiling_estimate']} | {r['after_ceiling_estimate']} |\n" for r in result if r['tag'] in ['UOY','UE8','UTY'])+'\n以上是按原版人口除数1000、农民征召制4%和每州25级上限计算的静态估算，不能当成实机兵力。额外加成原先还包含+50%进攻、+150%防御和训练率加成。\n\n西伯利亚、亚马逊为已审查的游戏宽文化类别，并不等于所有源民族是一支历史上的统一国家。本轮保留既定“映射民族连片合并”规则，先消除无源证据的模板军事加成；若实测仍过强，应单独审议按源民族政治身份分组，不宜靠任意面积阈值切块。\n\n依据：游戏 common/country_types/00_country_types.txt、common/defines/00_defines.txt、common/static_modifiers/06_conscription_modifiers.txt、common/laws/00_army_model.txt。[官方关于殖民宣称与原住民战争的说明](https://www.paradoxinteractive.com/games/victoria-3/news/dev-diary-75-diplomatic-improvements-in-1-2)。当前数值以本机1.13.11文件为准。\n')
 print(json.dumps(dict(affected=report['affected_generated_countries'],examples=[r for r in result if r['tag'] in ['UOY','UE8','UTY']]),ensure_ascii=False))
if __name__=='__main__':build()
