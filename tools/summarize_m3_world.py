"""Produce a local, searchable country/subject/ruler audit and testing instructions."""
import argparse
from collections import Counter
import html
from pathlib import Path
from m3_world import load_json


def write_summary(run):
    r = load_json(run / 'conversion_report.json'); cs = r['countries']
    rulers = {p['tag']: p for p in r['rulers']}
    flags = {p['tag']: p for p in r.get('flags', [])}
    flag_labels = {'existing_v3_identity_flag': 'V3 原版旗', 'imported_eu5_definition': 'EU5 纹章定义',
                   'generated_identity_flag': '生成识别旗（非原旗还原）'}
    edges = {e['target_subject']: e for e in r['subjects'] + r['vanilla_fallback_subjects']}
    governments = {'law_monarchy': '君主制／部落君主制', 'law_presidential_republic': '总统共和制',
                   'law_theocracy': '神权制', 'law_colonial_administration': '殖民行政'}
    types = {'colonial': '殖民政府', 'recognized': '受承认国家', 'unrecognized': '未受承认国家',
             'decentralized': '分散政权（可殖民）', 'company': '贸易公司'}
    relations = {'colony': '殖民地', 'puppet': '傀儡国', 'vassal': '附庸国', 'tributary': '朝贡国',
                 'protectorate': '保护国', 'personal_union': '联合统治', 'chartered_company': '特许公司', 'dominion': '自治领'}
    name = lambda t: cs[t].get('name_simp_chinese', t)
    rows = []
    for tag, c in sorted(cs.items(), key=lambda pair: (pair[0] != 'ITA', pair[0])):
        ruler = rulers.get(tag, {})
        person = ' '.join(filter(None, (ruler.get('first_name'), ruler.get('last_name')))) or '原版模板／分散政权'
        if ruler.get('regent_used'): person += '（源存档摄政者）'
        edge = edges.get(tag)
        relation = f'{name(edge["target_overlord"])} · {relations[edge["target_type"]]}' if edge else '独立'
        if edge and edge['target_type'] == 'personal_union': person += '；在 V3 共用宗主元首'
        vals = [name(tag), tag, c.get('source_tag', '原版留存'), types[c['country_type']],
                governments.get(c.get('government_law'), '原版模板'), person, relation,
                str(c['provinces']), c['capital'], c.get('source_capital', '—') or '—',
                c.get('culture', '—'), c.get('religion', '—'),
                flag_labels.get(flags.get(tag, {}).get('mode'), '原版留存／旧版占位')]
        rows.append('<tr>' + ''.join('<td>' + html.escape(v) + '</td>' for v in vals) + '</tr>')
    omitted = ''.join('<tr>' + ''.join('<td>' + html.escape(str(c[k])) + '</td>' for k in ('tag', 'id', 'owned_locations', 'population')) + '</tr>' for c in r['omitted_countries'])
    counts = Counter(e['target_type'] for e in r['subjects'])
    text = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>EU5 M3 世界映射核对</title>
<style>body{font:15px/1.65 system-ui,"Microsoft YaHei";background:#142330;color:#e4edf3;margin:28px}h1{font-size:27px}a{color:#95d4ff}img{width:100%;border-radius:10px}input{padding:12px;width:min(650px,90%);background:#233849;border:1px solid #789;color:white;font:inherit;border-radius:6px;position:sticky;top:10px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px;border-bottom:1px solid #38505f;text-align:left;vertical-align:top}th{color:#a6d3e7}tr:hover{background:#233849}.panel{background:#213545;padding:20px;border-radius:10px;margin:20px 0}.muted{color:#b3c1cd}code{color:#eecb93}</style>
<h1>EU5 1780.7.4 → V3 1.13.11：全世界政治映射</h1>
<p>离线检查通过；本版尚待实际加载、推进一年和重载验收。地图采用各国独立颜色，游戏中的附庸可能显示宗主颜色。</p>
<div class="panel">__COUNTS__</div><img src="world-map.png" alt="导出的世界国界预览">
<div class="panel"><b>此次转换边界</b><ul>
<li>国界、在任元首、政体、殖民政府、普通附属和可表达的联合统治按 EU5 存档设置。</li>
<li>人口、经济、产业、财富、识字率和军队仍用 V3 1836 地区模板。国家和当前元首文化采用显式对应或保留源身份的自定义文化，不再回退为地区模板文化；逐国依据见 <a href="culture-audit.html">文化核对页</a>。居民文化与人口另有审计草稿，尚未投放游戏。</li>
<li>意大利采用总统共和制 + 专制权力分配，对应存档的绝对总统权／王朝统治政策。元首年龄与 EU5 快照一致，不额外老化 55 年。</li>
<li>殖民政府同时具有 colonial 类型、colony 附属关系和殖民行政法律。可殖民分散政权逐国列于下表；南美无主区域采用亚马逊原住民近似。</li>
<li>92 个有领土的小国因目标地图粒度没有独立省份，不强行创造领土。多重宗主冲突保留正式附庸，联合君主仅保留源人物信息；无明确主导方的平等共主邦不虚构宗主。</li>
<li>为保留多层附庸树，本模组允许傀儡国继续拥有附庸。神罗等组织近似为势力集团，源同盟近似为共同防御条约；详细规则和遗漏见下方。未转换组织内部的完整宪制、在进行的战争、事件链和完整摄政继承流程。</li>
<li>国家宗教按源信仰显式映射：合性派对应东方正统教会，三教合流近似儒教，藏传佛教近似格鲁派，原生信仰近似泛灵论。人口宗教仍是地区模板。生成旗采用原版纹章素材，不能视为动态 EU5 原旗还原。</li></ul>
<a href="conversion_report.json">完整机器报告</a> · <a href="independent_verification.json">独立回读检查</a> · <a href="europe-map.png">欧洲放大图</a></div>
<h2>国家、政体、元首与宗主</h2><input id="search" placeholder="筛选名称、标签、殖民政府、宗主（例如：意大利）" aria-label="筛选国家"><p id="visible" class="muted"></p>
<table id="countries"><thead><tr><th>国家</th><th>V3 标签</th><th>EU5 标签</th><th>国家类型</th><th>政体法律</th><th>元首／摄政者</th><th>宗主关系</th><th>省份</th><th>V3 首都州</th><th>EU5 首都地点</th><th>主流文化</th><th>宗教</th><th>国旗来源</th></tr></thead><tbody>__ROWS__</tbody></table>
<h2>没有独立目标领土的源国家</h2><p>这些国家的地点并未变成无主洞；其对应的 V3 省份按省份级归属取舍。完全没有对应目标省份的源地点另见完整报告。</p>
<table><thead><tr><th>EU5 标签</th><th>源国家 ID</th><th>源地点数</th><th>源人口</th></tr></thead><tbody>__OMITTED__</tbody></table>
<script>const rows=[...document.querySelectorAll('#countries tbody tr')];function filter(){const q=document.querySelector('#search').value.toLocaleLowerCase();let n=0;for(const row of rows){row.hidden=!row.textContent.toLocaleLowerCase().includes(q);if(!row.hidden)n++}document.querySelector('#visible').textContent=`显示 ${n} / ${rows.length} 个国家`}document.querySelector('#search').addEventListener('input',filter);filter();</script></html>'''
    counts_text = f'覆盖 <b>{r["validation"]["land_provinces"]:,}</b> 个陆地省份、<b>{r["validation"]["land_states"]}</b> 个州；保留 <b>{r["validation"]["represented_source_countries"]}</b> 个源国家，另有 <b>{sum(not c["source_id"] for c in cs.values())}</b> 个未殖民区域留存／近似政权。<br>殖民地关系 <b>{counts["colony"]}</b> 条；联合统治 <b>{counts["personal_union"]}</b> 条；源外交关系总计 <b>{len(r["subjects"])}</b> 条，原版留存关系 <b>{len(r["vanilla_fallback_subjects"])}</b> 条。'
    text = text.replace('__COUNTS__', counts_text).replace('__ROWS__', ''.join(rows)).replace('__OMITTED__', omitted)
    if 'organizations' in r:
        esc = html.escape
        orgs = r['organizations']; ts = r['treaties']
        bloc_rows = ''.join('<tr>' + ''.join('<td>' + esc(str(v)) + '</td>' for v in
            (b['name_simp_chinese'], name(b['leader']),
             {'identity_eu5_hre_empire':'至高帝国／附庸 I（战争退出）','identity_religious':'宗教大会／神圣公民 I','identity_trade_league':'贸易同盟／内部贸易 I','identity_sovereign_empire':'至高帝国／附庸 I'}[b['identity']],
             len(b['members']),len(b['additional_subject_members']),len(b['excluded_members']))) + '</tr>'
            for b in orgs['power_blocs'])
        missing = '；'.join(name(b['leader']) + '：首领为' + name(b['overlord']) + '的属国'
                           for b in orgs['omitted_organizations'] if b['reason']=='leader_is_subject')
        treaty_rows = ''.join('<tr><td>'+esc(name(t['target_first']))+'</td><td>'+esc(name(t['target_second']))+'</td></tr>' for t in ts['created'])
        section = f'''<h2>势力集团与共同防御</h2><div class="panel">
<p>伊尔汗国仅在源组织有首领时建立，本存档处于权力真空，未建立伊尔汗集团。神罗采用至高帝国与附庸 I，直接和平退团被禁用，退出须对皇帝发起退出集团外交博弈。每国只能加入一个势力集团；优先保留宗主链，独立教会首领预留自己的集团。成员数包括会随宗主自动加入的属国，不等于源组织成员数。</p>
<table><thead><tr><th>集团</th><th>首领</th><th>类型与初始原则</th><th>预计成员</th><th>额外随宗主加入</th><th>源成员冲突遗漏</th></tr></thead><tbody>{bloc_rows}</tbody></table>
<p>未独立建立的宗教大会：{esc(missing)}。未解除这些属国关系，源教会成员清单保留于报告。</p>
<p>已生成 {len(ts['created'])} 份共同防御条约，绑定 1 个月，1836.2.1 后允许退出，不自动到期。141 条源同盟涉及无目标领土国家；另 2 条涉及可殖民分散政权，不能建立普通条约。</p>
<p>条约双方初始关系设为 50，补齐“国际关系”科技。宗教大会首领若模板宗教法律不兼容，调整为信仰自由；保留已有国教或信仰自由法律。势力集团要求相应 DLC 功能。所有引擎内效果仍需新开局验证。</p>
<details><summary>查看全部共同防御条约</summary><table><thead><tr><th>第一方</th><th>第二方</th></tr></thead><tbody>{treaty_rows}</tbody></table></details></div>
<h2>生成旗帜设计预览</h2><p>这是按原版材质绘制的近似图；灰色角标在游戏内替换为宗主旗。<a href="flag-catalogue.png">全部生成旗目录</a></p><img src="flag-preview.png" alt="旗帜构图预览">
'''
        text = text.replace('<h2>国家、政体、元首与宗主</h2>', section+'<h2>国家、政体、元首与宗主</h2>')
    if any(b.get('stability') for b in r.get('organizations', {}).get('power_blocs', [])):
        text = text.replace('<h2>国家、政体、元首与宗主</h2>', '<p>神罗至高帝国：规模固定惩罚 10，宪制凝聚力 +25；独立皇帝免除领导等级门槛和弱集团等级惩罚。不能直接和平退出或自愿解散；退出须对皇帝提出退出集团战争目标，皇帝退让可避免实际交战。仅转换神罗适用。需要新开局验证。</p><h2>国家、政体、元首与宗主</h2>')
    (run / 'review.html').write_text(text, encoding='utf-8')
    (run / 'INSTALL.txt').write_text('''本包只适用于 Victoria 3 1.13.11。全世界政治映射测试，尚未游戏内验收。

1. 退出游戏，重启 Paradox 启动器，让它重新扫描本地模组。
2. 新建测试播放集，只启用「EU5 M3 - World 1780 - Political Map TEST」。关闭 M2 测试模组及其他改图、国家、开局历史模组。
3. 新开 1836 年沙盒，选择意大利。不能用旧 V3 存档检验这个开局。
4. 开局暂停，核对：意大利为共和国；元首安布罗斯·阿尔忒米俄斯（89 岁）；皮埃蒙特以外的意大利、北非等领土；意大利 68 个殖民附属国和殖民行政法律。
5. 核对西班牙—葡萄牙、法兰西—挪威联合统治，以及殖民地自己的总督；多层附庸不应被压平成全部直属意大利。
   核对神罗（波希米亚）为至高帝国／附庸 I（战争退出规则），天朝（明）为至高帝国／附庸 I；本档没有伊尔汗集团。格鲁吉亚正教会、俄罗斯正教会保持宗教大会及神圣公民 I；奇里乞亚为东方正统教会。
   核对明的名称为“明”、主流文化为“汉”、旗帜来自 EU5 的明纹章；查看 culture-audit.html 逐国对照主流文化。
   在外交条约中核对共同防御条约：1 月仍受绑定，2 月允许发起退出，但条约不会自动终止。属国旗角标应显示宗主旗。
6. 保存 M3_start。核对神罗成员约 156 国；推进至 1836.1.10、1836.2.1 和 1837.1.1，记录集团首领、成员数、凝聚力，保存 M3_year1，退出到菜单并重载。直接和平退团应不可用；退出集团外交博弈须以皇帝为目标；不要用旧存档检验初始化修复。
7. 把失败阶段或异常国家名称告知开发任务，保留这次游戏会话的 error.log。随后可以依据日志修正；不需要你自己排查脚本。

人口、经济、建筑、军队、科技均为 V3 初始化模板。本轮不应拿人口总数或产业布局与 EU5 对账。
原版未殖民区域按授权保留；小国取舍和政体／元首／宗主清单见同目录 review.html。
禁用这个播放集即可停用 M3；旧 M2 模组与原存档均保留。
''', encoding='utf-8-sig')
    return run / 'review.html'


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('run', type=Path)
    print(write_summary(p.parse_args().run))
