"""Reviewable release notes and remaining empty state-part inventory."""
from build_fresh_1337 import *
from package_m4_population_test import parse_pops

def build():
 package=RUN/'complete';mod=package/'eu5_m5_1337_test';summary=read(package/'summary.json')
 owners=read(RUN/'political/province_owners.json');mapping=read(RUN/'political/conversion_report.json');plan=read(RUN/'terrain_plan.json')
 pops=parse_pops(mod/'common/history/pops/00_eu5_world.txt');parts=Counter();source_parts=Counter()
 for k,n in pops.items():parts[k[:2]]+=n
 for r in rows(RUN/'demographic/staging/province_population_draft.csv'):source_parts[r['target_state'],r['target_owner']]+=int(r['centipersons'])
 empty=[]
 for s,ps in sorted(owners.items()):
  for t in sorted(set(ps.values())):
   if parts[s,t]:continue
   provinces=sorted(p for p,v in ps.items() if v==t);direct=sum(plan['provinces'][p]['owner'].startswith('source:') for p in provinces)
   empty.append([s,t,mapping['countries'][t]['culture'],len(provinces),direct,source_parts[s,t],' '.join(provinces),'source-positive rounding' if source_parts[s,t] else 'source-owned empty terrain' if direct else 'ethnic continuity terrain; no local residents'])
 csvwrite(package/'empty_state_parts.csv',['state','owner','culture','provinces','source_owned_provinces','source_centipersons','province_ids','reason'],empty)
 a=read(RUN/'empty_native_attachments.json');pending=[x for r in a for x in r.get('unpopulated_state_parts',[])];corrections=[x for r in a for x in r.get('state_owner_corrections',[])]
 write(package/'empty_terrain_audit.json',dict(whole_empty_states=[],whole_empty_countries=[],empty_state_parts=len(empty),approved_template_states=read(RUN/'source_empty_templates.json'),attachments=a,state_owner_corrections=corrections,reviewed_retained_attachment_parts=pending))
 notes=f"""# 1337 开局重生成测试包

版本：0.6.2-1337-test3
启动器名称：EU5 M5 - World 1337 - Generic Rules TEST

使用 EU5 1337.4.1 的独立开局，重新生成归属、居民、政治法律、科技、产业、军队、舰队及战争。只复用已审查的映射规则与文化资源，没有复制 1780 年的人口、国界、军队或产业历史。

## 启动

在启动器启用 eu5_m5_1337_test，并停用其他 EU5 转换测试模组。新开 1836 书签游戏；世界数据取自 1337 年，书签日期没有改成 1337。旧 1780 模组保留。此次不修改启动器播放集。

## 本次结果

- test3 从生成规则修复开局内战：先读取原版战争类型为双方建立初始目标清单，镜像内战保留双方吞并目标，不再错误删除不存在的防守方羞辱目标。所有删除均检查所属方及重复删除，并带存在性条件。5场源战争及其参与国、领土候选方案不变。
- 文化与宗教配套定义改为成套生成：3,416条静态修正定义及其1,708条修正类型注册；校验检查整个依赖链。test2只补了静态定义、遗漏类型注册的问题已修复。数量随当前存档实际定义自动计算，不依赖1337文化名单。
- test2 修正 test1 的家园脚本生成错误：完整移除旧家园赋值并使用 `cu:` 文化作用域，清除1,338个截断残留，按已审查台账重写722条家园。补齐564种自定义文化所需的3,384条原版格式修正定义；这些是定义，不是额外开局加成。人口、归属、民族映射、产业与军事历史保持原测试包数据。
- {summary['countries']} 个国家；其中 {summary['native_countries']} 个按民族连片生成的部落，另外保留瑙鲁原版模板国家；阿克里已并入周边亚马逊民族部落。
- 源人口 {summary['source_population']:,} 人（由精确源台账统一取整）；原版模板补位 {summary['template_supplement_population']:,} 人；合计 {summary['total_population']:,} 人。
- 阿克里：并入周边连片亚马逊民族部落，保留此前批准的16,350人模板；瑙鲁：NRU，1,251人。母岛：采用原版注释中的小笠原26人参考，文化、宗教随本存档塞班岛映射，作为独立松散部落。补位单列，不与源人口叠加。
- {summary['used_cultures']} 种居民文化，{summary['effective_cultures']} 种有效文化定义，{summary['religions']} 种居民宗教。
- {summary['building_levels']} 级建筑，{summary['armies']} 支陆军编制、{summary['battalions']} 个营，{summary['fleets']} 支舰队，{summary['wars']} 场源战争。
- 40,717 个陆地地块全部有归属。整州无人口、整国无人口均为零；州界未改变。
- {len(a)} 个无人口部落归并到参考地点对应的有居民国家；其中 {len(corrections)} 项进一步调整到同州同民族有居民国家，避免另建空分州，不转移人口。

## 已知限制与待审查

- 仍有 {len(empty)} 个无人口的“州内国家部分”，详见 empty_state_parts.csv；这不等于 {len(empty)} 个整州无人。包括源国家本来持有的荒地、跨州民族连续地带，；3处源人口不足1人的分州已通过守恒取整修正。未因人口为零就抹除实际源归属或改成其他民族。
- 魁北克 x46467A 沿用用户已复核的因纽特参考，保留无人口岛屿归属。关东 x800111 的母岛例外已落实。原66组全部完成规则核准；保留62个真实无人荒地分州，不把它们宣称为已补人口。
- 新生成部落不再复制模板国家专属的 native_conscription 征召、训练及攻防加成；原版法律和正常动员机制保留。西伯利亚和巴西部落维持已批准的民族连片归属，未按面积任意拆国。规模与潜在兵力审查见 outputs/1337-supervised-terrain-20261002/native_colonization_audit.md。
- {summary['omitted_source_countries']} 个源小国因目标地图省份粒度没有独立领土；其居民仍完整分配，并未丢失。
- 92 个证据不足的源文化保留显式身份占位；新文化的人名与图形沿用已记录的地区模板，不视为经历史考证的中世纪名单。详细文化审查位于 outputs/01a0f510-fde4-7dd3-983c-d5b74834b7cf-culture1337。
- 主包采用 preserve 人口方案。population_reserve_15.txt 为同一原始人口生成的备选文件，未替换主包人口。
- test1、test2均在用户实测中初始化闪退。test2家园语法错误已消失，但转储显示引擎查找羞辱战争目标失败后读取空指针，与第一场内战的错误删除规则对应。test3已修规则并通过静态检查，游戏复测由用户进行，尚不能宣称闪退已经消除。test2崩溃时仍有4,866MB可用物理内存、29,706MB可用交换空间，不支持将本次归因于内存耗尽。本包用于检验规则泛用性，不代表任意存档已能无审查自动转换。

审计文件：verification.json、package_report.json、empty_terrain_audit.json。地理映射、人口分配、法律、产业均有源证据和规则记录；模板例外单列。
"""
 text(package/'README.md',notes)
 print(json.dumps(dict(empty_parts=len(empty),pending_attachment_parts=len(pending),state_owner_corrections=len(corrections))))
if __name__=='__main__':build()
