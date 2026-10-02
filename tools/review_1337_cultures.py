"""Second-pass review of every new or previously flagged 1337 source identity.

Produces a complete disposition register, not historical certainty or game assets.
Evidence-limited entries explicitly forbid fabricated language-family membership.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
import json
import shutil

from audit_1337_cultures import OUT, protected
from audit_m5_culture_identity import ROOT, EU5, read, write, sha, tree, csvwrite, effective, fields, objects, strings, root
from culture_1337_language_review import DATA, catalog, lookup

# Changes to display scope apply to ALL members of the target in this frozen
# inventory. Their membership is exported explicitly; unseen members are rejected.
TARGET_NAMES={
 'manchu':'女真—满洲', 'rajput':'拉贾斯坦', 'bedouin':'阿拉伯半岛',
 'burmese':'缅族—若开', 'shan':'傣—掸', 'kanuri':'卡努里—卡内姆布',
 'marathi':'马拉地—孔卡尼—坎德什', 'paiute':'努米克', 'vietnamese':'京—芒',
 'patagonian':'南锥体原住民', 'mazanderani':'吉兰—马赞德兰',
 'ukrainian':'鲁塞尼亚', 'romanian':'东罗曼', 'chechen':'纳赫',
 'polish':'波兰—卡舒比', 'dakota':'达科他—拉科他—纳科达', 'tupinamba':'图皮族群',
}
SCOPE_PRESERVE=set('dalmatian alor_culture makasae_culture catagua_culture tapajo_culture arua_culture'.split())
# Historical cases with an already suitable vanilla regional abstraction.
HISTORICAL_EXISTING={
 'messufa_culture':'maghrebi', 'lamtuna_culture':'maghrebi',
 'manaos_culture':'amazonian', 'yuri_culture':'amazonian',
 'german_transylvanian':'north_german', 'german_carpathian':'north_german',
 'dehwar_culture':'persian', 'tebbu_culture':'tibetan',
}
# The two Saharan sources must use Berber identity, not the Maghrebi Arabic
# abstraction: resolved against actual available culture keys below.
CLOSED={
 'eu5_review_aleut':('阿留申', 'unalaska_culture atka_culture attu_culture'),
 'eu5_review_abkhaz_abaza':('阿布哈兹—阿巴津','abkhazian_culture abazin_culture'),
}
EXTRA_NOTES={
 'german_transylvanian':'源萨克森移民名称不证明来自现代萨克森州。暂维持原版北德的既有移民抽象，不再无证改南德；不按这类标签推定1337故土。',
 'german_carpathian':'喀尔巴阡德意志为多来源移民集合，暂维持既有德意志宽类，不由名称自行决定单一南／北来源。',
 'teimani':'保留也门犹太身份和既有独立传承；半岛阿拉伯语资产作日常语宽抽象，宗教文字传统不替换POP口语。',
 'mizrahi':'源Mizrahi为多社群宽标签，不能把黎凡特阿拉伯语字段解释为所有东方犹太人的唯一语言；保留源文化粒度和原POP宗教，不吸收新增波斯、格鲁吉亚或开封社群。',
 'mustaarabi':'保留阿拉伯语犹太社群来源，源埃及方言只作为该存档输入；不推广为所有犹太社群。',
 'beyte_yisrael':'保留埃塞俄比亚犹太身份和既有例外传承；源Agaw字段与礼仪语言分层，人物外观不能照抄欧洲犹太模板为族源结论。',
 'qayfengi':'保留开封犹太社群。1337日常语证据不足，采用社群专用未定语言占位，不自动汉语化或希伯来语化。汉传承仅作当地接纳设计；不赋予全河南本土。',
 'ashkenazi':'两档均有正人口；1780为2.48人，不按人口极少删除。保留阿什肯纳兹身份，意第绪资产为宽时段抽象。',
 'sephardi':'沿用塞法迪身份；现有Ladino仅作语言资产抽象，不以1492后离散历史倒推1337人口迁移或本土。',
 'yugur_culture':'源身份同时涉及东裕固蒙古语支与西裕固突厥语支。源POP未提供比例，保留统一裕固身份与多语占位，不造比例、不统一归蒙古语。',
 'kirati_culture':'基拉特为源宽身份，不能认作藏语或直接等同林布。保留其源成员范围及独立语言集合占位，不强行指向一个现代语言。',
 'harla_culture':'保留源哈尔拉历史标签；不足以由源ethiopic字段判定全部日常语言，使用分类未定占位，不编造古语言。',
 'sclavene':'保留源斯克拉维尼历史集合；不用塞尔维亚语字段把该古称变成现代单一民族。',
 'kvens':'保留存档克文标签；现代Kven Finnish目录条目不证明1337已形成同样的移民社群，禁止套用近代移民本土。',
 'qashqai_culture':'保留存档卡什加标签及突厥语言结构证据；不按后世联盟重画1337民族边界。',
 'napuruna_culture':'Napo Quechua条目可辨识语言，不证明1337已发生后世克丘亚语扩张；保留源身份，不制造印加／殖民迁移。',
 'tamna_culture':'保留耽罗源身份。不能由现代济州语目录反推全部1337人口；不把语言空缺补成单一朝鲜语历史结论。',
 'danzhou_culture':'儋州源身份保留；源粤语字段只记为输入证据，缺乏本轮足够历史方言依据，不据此创造已定亲缘。',
 'jasz_culture':'保留亚什源身份及阿兰传统字段；不将其等同波斯民族。只复用伊朗宽传承，不宣称1337已讲现代奥塞梯语。',
 'mandean_culture':'区分曼达语礼仪传统和当地日常语。采用曼达社群语言占位，不把古典曼达语目录当作1337每位居民的口语证明。',
 'samaritan_culture':'撒玛利亚社群独立保留；希伯来文、阿拉米文传统与当地日常语言分开记录，禁止以宗教统一人口语言。',
 'mi_niah_culture':'中文本地化为党项，源键Minyak可歧义。保留源党项身份，不并彝；党项语目录仅作比较证据，不能拿现代木雅语替代。',
 'cahokia_culture':'考古聚落标签保留，不自动等同苏语民族，也不等同后世同名伊利诺伊部落；语言分类未定。',
 'dorset_culture':'保留存档多塞特考古身份。不能以现代因纽特接触或继承关系判定相同民族、语言；不强制按现实消亡年份删POP。',
 'hohokam_culture':'霍霍坎为考古命名，不是Hokan语族的拼写变体。保留源身份和独立未定语言，不臆定唯一现代后裔。',
 'lozi_culture':'1337按卢伊／洛齐源身份保留；不套19世纪科洛洛影响形成的索托语言替代，使用Luyi比较条目并保留年代限制。',
 'khorezmian_culture':'采用源存档突厥花剌子模身份；不自动恢复古伊朗花剌子模语，也不直接改称乌兹别克。',
 'bolghar_culture':'保留存档保加尔身份，不以后继楚瓦什替代；源语言作为转换输入，不认证古今语言完全等同。',
 'zaza_culture':'保留扎扎源身份及单列语言，不据语言分类裁决现代政治自我认同；共享伊朗传承。',
 'sama_culture':'保留萨马—巴瑶源身份，宗教按POP继承；不因摩洛标签预设伊斯兰化。',
 'mbugu_culture':'姆布古含普通与混合语体问题，保留源身份，不能由沿海位置直接斯瓦希里化；目录与语体研究分列。',
 'monpa_culture':'门巴是多语言源集合，保留集合，不按名称任选目录中的一个现代语言。',
 'bo_culture':'僰为历史来源标签。缺乏唯一语言归属证据，保留身份与未定语言，不自动壮化。',
 'ciboney':'源西沃内标签有不同历史用法；保留源标签，不能仅凭古巴地理归泰诺或亚马孙民族。',
 'bjarmian':'保留比亚尔米亚源地域标签；不凭地理把语言确定为乌戈尔或科米。',
 'merya_culture':'保留梅里亚源身份；材料有限，使用独立语言占位，不能由芬乌宽亲缘替换为乌戈尔。',
 'kallawaya_culture':'卡亚瓦亚社群及专门语言与克丘亚、艾马拉日常交际语不能互相替代；保留独立身份，1337语体比例不设定。',
 'pasto_culture':'目录记为未分类，撤销把源Barbacoan字段当作已证亲缘的做法。',
 'cueva_culture':'目录记为未分类；不能依源Chibchan字段自动合并，保留身份及未定语言。',
 'muzo_culture':'目录记为未分类；不能凭源Cariban字段确认加勒比语系。',
 'koroa_culture':'目录检索的Acroá是巴西同音近名，拒绝该匹配；保留密西西比地区Koroa源身份，语言不强定。',
 'ciguayo_culture':'目录别名落到Caribbean Arawakan的大类不足以认证Ciguayo亲缘。保留独立源身份、未定语言。',
 'yazoo_culture':'保留源亚祖；资料不足时不能把源Natchez语言字段升格为确定结论。',
 'henia_culture':'Henia/Kamiare为科梅钦贡相关源身份，不是德州Comecrudo；拒绝名称相似匹配，保留源语言占位。',
}

# Reject homonyms and catalog aliases too broad to certify the source identity.
REJECT=set('ciguayo_culture koroa_culture mi_niah_culture monpa_culture henia_culture arua_culture'.split())
MANUAL_IDS={
 'ache_culture':['ache1246'], 'ngacang_culture':['acha1249'],
 'bru_culture':['east2332','west2397'], 'semnani_culture':['semn1249'],
 'arawak_culture':['araw1276'], 'oowekyala_culture':['heil1246'],
}

def reviewed_languages():
    cat,_=catalog(); results={}
    for key,queries in lookup().items():
        if key in REJECT:continue
        hits=[h for _,rows in queries for h in rows]
        ids=MANUAL_IDS.get(key)
        if ids is not None:hits=[cat[i] for i in ids]
        # Every remaining multi-match was examined; only genuine multi-language
        # source identities/sets remain. No arbitrary first-match selection.
        elif any(len(h)>1 for _,h in queries):continue
        if hits:
            results[key]=[dict(glottocode=h['ID'],name=h['Name'],level=h['Level'],
                family=cat[h['Family_ID']]['Name'] if h['Family_ID'] else '',
                family_id=h['Family_ID'],isolate=h['Is_Isolate'],
                url='https://glottolog.org/resource/languoid/id/'+h['ID']) for h in hits]
    return results

def source_assets():
    names,tags={},{}
    def count_pool(obj):
        if not hasattr(obj,'entries'):return 0
        return sum(count_pool(v) if hasattr(v,'entries') else 1 for _,v in obj.entries())
    for p in sorted((EU5/'in_game/common/languages').glob('*.txt')):
        for key,obj in objects(root(p.read_text(encoding='utf-8-sig'))):
            f=fields(obj)
            data=dict(language=key,file=p.name,male_count=count_pool(f.get('male_names')),
                female_count=count_pool(f.get('female_names')))
            names[key]=data
            if 'dialects' in f:
                for sub,ob in objects(f['dialects']):
                    sf=fields(ob);d=dict(data)
                    for field,col in [('male_names','male_count'),('female_names','female_count')]:
                        if field in sf:d[col]=count_pool(sf[field])
                    d['dialect']=sub;names[sub]=d
    for p in sorted((EU5/'in_game/common/cultures').glob('*.txt')):
        for key,obj in objects(root(p.read_text(encoding='utf-8-sig'))):
            f=fields(obj);tags[key]=list(strings(f['tags'])) if 'tags' in f else []
    return names,tags

def build():
    first=OUT/'first_pass_audit.json'
    if not first.exists():shutil.copyfile(OUT/'audit.json',first)
    audit=read(first); rows=deepcopy(audit['rows']); base={r['source_culture']:r for r in audit['rows']}
    installation=read(ROOT/'.local/m5/installation-latest.json'); mod=Path(installation['target'])
    files, installed=protected(),tree(mod)
    original_installed=audit['inputs']['installed_files_sha256']
    culture_drift=[k for k in set(installed)|set(original_installed)
        if 'culture' in k and installed.get(k)!=original_installed.get(k)]
    assert not culture_drift, 'Culture baseline changed: '+str(culture_drift)
    audit['summary']['installation_observed_at_review']=installation['version']
    audit['summary']['culture_files_equal_to_baseline']=True
    definitions=effective(mod,'common/cultures')
    language_hits=reviewed_languages()
    assert 'ciguayo_culture' not in language_hits and 'koroa_culture' not in language_hits
    assert language_hits['ache_culture'][0]['glottocode']=='ache1246'
    assert language_hits['mbugu_culture'][0]['glottocode']=='mbug1240'
    assert language_hits['yuri_culture'][0]['glottocode']=='juri1235'
    name_pools,culture_tags=source_assets()
    # Resolve the available vanilla Berber culture explicitly.
    berbers=[k for k in ('berber','amazigh') if k in definitions]
    assert len(berbers)==1,berbers
    HISTORICAL_EXISTING['messufa_culture']=HISTORICAL_EXISTING['lamtuna_culture']=berbers[0]
    assets={}; decisions=[]; display_members=defaultdict(list)
    for r in rows:
        k=r['source_culture']; inherited=r['inherited_audit']; before=r['target_culture']
        reviewed=r['new_in_1337'] or inherited in ('scope_design','historical_review','source_label_review') or 'jewish_group' in r['source_groups']
        r['baseline_target']=before
        r['review_completed']=reviewed
        r['review_conclusion']='沿用既有对应；本轮未重作逐项历史考证。'
        r['date_policy']='保留存档已存在的源身份；不按现实消亡／迁移日期强制增删人口。'
        r['name_policy']='身份名称沿用源本地化；部落国名仅用民族名称。人物姓名不可由文化标签临时编造。'
        r['graphics_policy']='只允许复用现有地区外观作为游戏表现，不把外观当作族源或血缘证据。'
        r['heritage_policy']='现有地区传承作为接纳玩法设计；不从语言亲缘推定民族相同。'
        r['source_name_pool']=name_pools.get(r['source_language'],{})
        r['source_graphics_tags']=culture_tags.get(k,[])
        if r['source_name_pool'].get('male_count',0) and r['source_name_pool'].get('female_count',0):
            r['name_policy']+=' 源游戏有男女姓名池，但池属于语言级模板，不能据此认证每个民族在1337的真实姓名。'
        else:r['name_policy']+=' 源语言缺少完整男女姓名池；资产制作时必须显式补充来源，禁止AI补造民族姓名。'
        if inherited=='historical_review':
            if k in HISTORICAL_EXISTING:
                r['target_culture']=HISTORICAL_EXISTING[k]
                r['review_conclusion']='改用明确列出的既有宽类；保留源身份和语言记录，不作狭义民族同义断言。'
            else:
                r['target_culture']='eu5_review_'+k
                r['review_conclusion']='撤销无充分依据的邻族替换，保留源身份；复用现有地区传承，不新增专属传承。'
        elif inherited=='scope_design':
            if k in SCOPE_PRESERVE:
                r['target_culture']='eu5_review_'+k
                r['review_conclusion']='超出旧目标名称的合理范围，改为保留源身份；不新增专属传承。'
            else:
                r['review_conclusion']='保留原版粒度，并将目标名称明确为冻结成员的宽类／合称；不是各成员完全同义。'
        elif inherited=='source_label_review':
            r['review_conclusion']='确认这是源游戏的宽泛集合标签：原样保留，不任选一个现代民族或语言充当其全部成员。'
        elif r['new_in_1337']:
            r['review_conclusion']='确认本轮显式成员对应，使用既有原版宽类；逐源信息保留，禁止对未知来源泛化。' if r['target_culture'] in definitions else '保留独立源身份，复用地区传承；语言按目录比较或明确未分类方式处理。'
        elif reviewed:
            r['review_conclusion']='完成犹太社群专项复核，保留既有身份与传承，不将共同宗教当作统一语言或合并社群的依据。'
        for target,(name,members) in CLOSED.items():
            if k in members.split():
                r['target_culture']=target;r['target_name']=name
                r['review_conclusion']='使用明确列出的有限合称，排除原先过窄的邻族身份；不扩展未知成员。'
        target=r['target_culture']
        if target in TARGET_NAMES:
            r['target_name']=TARGET_NAMES[target];display_members[target].append(k)
        elif target in definitions:
            # Retain baseline names where unchanged; resolve changed vanilla keys.
            if target!=before:r['target_name']=target
        else:
            if target not in CLOSED:r['target_name']=r['source_name']
        if k=='tunica_culture':r['target_name']='图尼卡'
        if target in definitions:
            r['language_candidate']=definitions[target].get('language','')
            r['heritage_candidate']=definitions[target].get('heritage','')
        refs=language_hits.get(k,[])
        r['linguistic_evidence']=refs
        if reviewed:
            r['reference_urls']=list(dict.fromkeys(r['reference_urls']+[x['url'] for x in refs]))
            if k in EXTRA_NOTES:r['review_conclusion']+=' '+EXTRA_NOTES[k]
            if refs:
                unclassified=any(x['family_id'] in ('uncl1493','unat1236','book1242','spee1234','mixe1287') for x in refs)
                r['language_review']='目录对照：'+'；'.join(x['name']+' / '+(x['family'] or ('独立目录分支')) for x in refs)+'。目录用于分类比较，不单独证明1337日常语言。'
                r['evidence_disposition']='资料不足／非普通谱系，保留源标签' if unclassified else '已核对目录差异，按明示粒度处理'
            else:
                r['language_review']='没有足够的本轮对应证据；保留源语言字段作溯源，禁止给未定语言强配现代亲缘。'
                r['evidence_disposition']='沿用原版抽象' if target in definitions else '资料不足，保留源标签'
            if k in EXTRA_NOTES:r['language_review']+=' '+EXTRA_NOTES[k]
            if target not in definitions:
                if refs and len(refs)==1 and refs[0]['family_id'] not in ('uncl1493','unat1236','book1242'):
                    r['language_candidate']='eu5_review_language_'+refs[0]['glottocode']
                    r['language_treatment']='目录条目对应的游戏语言资产；非1337口语真实性证明'
                else:
                    r['language_candidate']='eu5_review_language_source_'+k
                    r['language_treatment']='来源专用占位；不设已知语言家族，不称其为已证明的孤立语言'
                if k in ('qayfengi','yugur_culture','mandean_culture','samaritan_culture','mi_niah_culture','kirati_culture'):
                    r['language_candidate']='eu5_review_language_source_'+k
                    r['language_treatment']='多语／年代／源标签证据不足的来源专用占位，不编造比例与谱系'
                reuse={'italki':'north_italian','romanyoti':'greek','kalimi':'persian','gurji':'georgian'}
                if k in reuse:
                    r['language_candidate']=definitions[reuse[k]]['language']
                    r['language_treatment']='复用现有语言粒度，另存犹太社群语体记录；身份不随语言合并。'
                assets.setdefault(target,dict(name=r['target_name'],members=[],heritage=r['heritage_candidate'],
                    language=r['language_candidate'],language_policy=r['language_treatment'],
                    character_names='从核定的源姓名列表或明确注明的现有游戏模板取用，源语言纠错后不得沿用错配姓名。未生成新人物姓名。',
                    graphics='采用源地区对应既有模板作为表现抽象；不据外观推定亲缘。',
                    homeland='不复制1780本土；源分布仅列候选，少数社群不自动得到整州本土。',
                    asset_generated=False))['members'].append(k)
            else:r['language_treatment']='沿用既有宽类别的代表语言；不代表所有来源历史上同语'
            r['homeland_note']='审查结论：不从居住人口自动授予整州本土，不复制1780清单；本次只记录1337社群分布。'
            r['language_note']=r['language_review']
            r['decision_name']='已复核：'+('保留源身份' if target not in definitions else '既有宽类／合称')
            decisions.append(r)
        else:
            r['language_review']=r['language_note'];r['evidence_disposition']='既有映射';r['language_treatment']='沿用既有资产'
    # Explicitly reuse language within the two finite composites without claiming
    # source rows were always a single language; asset carries an umbrella label.
    for target in CLOSED:
        members=[r for r in rows if r['target_culture']==target]
        key='eu5_review_language_group_'+target.removeprefix('eu5_review_')
        for r in members:r['language_candidate']=key
        assets[target]['language']=key;assets[target]['language_policy']='有限成员的语言集合抽象，保留每个来源的独立语言记录。'
    mapping={r['source_culture']:r['target_culture'] for r in rows}
    totals=Counter()
    for r in rows:totals[r['target_culture']]+=r['population_1337_centipersons']
    changes=[dict(source=k,old=base[k]['target_culture'],new=mapping[k]) for k in mapping if mapping[k]!=base[k]['target_culture']]
    s=audit['summary']
    s.update(reviewed_sources=len(decisions),reviewed_new_sources=sum(r['new_in_1337'] for r in decisions),
        reviewed_legacy_sources=sum(r['inherited_audit'] in ('scope_design','historical_review','source_label_review') for r in decisions),
        reviewed_existing_sources=sum(not r['new_in_1337'] for r in decisions),
        legacy_dispositions_written=171,linguistic_catalog_matches=sum(bool(r['linguistic_evidence']) for r in decisions),
        preserved_uncertainty_sources=sum(r['evidence_disposition'].startswith('资料不足') for r in decisions),
        final_new_asset_designs=len(assets),base_resident_targets=len(totals),
        effective_definitions_if_all_added=len(definitions)+len(assets),offline_mapping_changes=len(changes),
        deployment_ready=False)
    audit['rows']=rows;audit['summary']=s
    audit['review_note']='546条新增、171条旧疑问及其余既有犹太社群均已给出处理结论。已复核不等于所有历史问题已有确定答案；资料不足项有保留规则。未创建游戏资产或调整生产数量上限。'
    audit['research_files']={p.name:sha(p) for p in DATA.glob('*.csv')}
    audit['references'].update({
       'glottolog':dict(title='Glottolog官方CLDF目录及别名',url='https://github.com/glottolog/glottolog-cldf',scope='分类与名称比较；已排除同名、宽别名误匹配；不能单独认证1337边界或民族身份。'),
       'hohokam':dict(title='NPS：Ancestral Sonoran Desert People',url='https://www.nps.gov/cagr/learn/historyculture/the-ancestral-sonoran-desert-people.htm',scope='霍霍坎考古命名；不等于Hokan语系。'),
       'cahokia':dict(title='伊利诺伊大学：Cahokia Richland Project',url='https://cahokia.web.illinois.edu/projects/richland-project/',scope='都市人口多来源；不等同唯一现代民族或语言。'),
       'kallawaya':dict(title='UNESCO：Machaj Juyai-Kallawaya',url='https://courier.unesco.org/en/articles/secrets-machaj-juyai-kallawaya',scope='社群专门语言与日常交际语言分层。'),
       'mbugu':dict(title='APiCS：Mixed Ma’a/Mbugu',url='https://apics-online.info/contributions/62',scope='混合语体案例；不能简单替换为斯瓦希里身份。'),
       'dorset':dict(title='加拿大历史博物馆：Dorset器物记录',url='https://www.historymuseum.ca/collections/artifact/539514',scope='区分多塞特考古传统和历史因纽特；不替存档强制灭绝。'),
       'ormuri':dict(title='Iranica：Ormuri',url='https://www.iranicaonline.org/articles/ormuri-language/',scope='奥尔穆尔独立语言及多语接触；不是普什图同义。'),
    })
    for k,ref in [('hohokam_culture','hohokam'),('cahokia_culture','cahokia'),('kallawaya_culture','kallawaya'),('mbugu_culture','mbugu'),('dorset_culture','dorset'),('ormur_culture','ormuri')]:
        r=next(r for r in rows if r['source_culture']==k);r['reference_urls'].append(audit['references'][ref]['url'])
    write(OUT/'audit.json',audit);csvwrite(OUT/'all_cultures.csv',rows)
    csvwrite(OUT/'additional_1337.csv',[r for r in rows if r['new_in_1337']])
    csvwrite(OUT/'review_decisions.csv',decisions)
    csvwrite(OUT/'inherited_review_decisions.csv',[r for r in decisions if not r['new_in_1337']])
    csvwrite(OUT/'uncertainty_dispositions.csv',[r for r in decisions if r['evidence_disposition'].startswith('资料不足')])
    write(OUT/'candidate_assets.json',dict(stage='reviewed_design_not_game_assets',assets=assets))
    write(OUT/'candidate_mapping.json',dict(stage='reviewed_offline_only',source_date='1337.4.1',
        source_sha256=audit['inputs']['source_sha256'],unknown_source_policy='reject_for_review',mappings=mapping,
        offline_changes=changes,display_scope_overrides={k:dict(name=TARGET_NAMES[k],members=v) for k,v in display_members.items()},
        limitation='本次完成审查方案，未生成资产、未运行迁移分支、未变更正式数量上限。'))
    csvwrite(OUT/'candidate_target_populations.csv',[dict(target_culture=k,centipersons=n) for k,n in sorted(totals.items())])
    saved=read(OUT/'candidate_mapping.json')['mappings'];evidence=read(ROOT/'outputs/terrain-1337-reviewed-geography-20261002/source_evidence.json')
    replay=Counter()
    for pops in evidence['location_cultures'].values():
        for k,n in pops.items():
            if n:replay[saved[k]]+=n
    validation=dict(review_decisions=len(decisions),all_new_reviewed=sum(r['new_in_1337'] for r in decisions)==546,
        all_legacy_flags_reviewed=sum(r['inherited_audit'] in ('scope_design','historical_review','source_label_review') for r in decisions)==171,
        all_rows_have_disposition=all(r['review_conclusion'] and r['language_treatment'] for r in rows),
        source_coverage=len(saved)==2086,population_reconciled=sum(replay.values())==evidence['world_centipersons'],
        target_totals_reconciled=replay==totals,installed_files_unchanged=installed==tree(mod),protected_files_unchanged=files==protected(),
        offline_changes=len(changes),historical_certainty_claimed=False,game_assets_generated=False)
    assert all(v for k,v in validation.items() if k not in ('review_decisions','offline_changes','historical_certainty_claimed','game_assets_generated'))
    write(OUT/'validation.json',validation)
    render_review(audit)
    print(json.dumps(dict(summary=s,validation=validation),ensure_ascii=False,indent=2))

def render_review(audit):
    s=audit['summary'];rows=audit['rows'];by={r['source_culture']:r for r in rows}
    report=f'''# 1337 文化审查与离线处理方案

对照 {s['baseline_version']} 的既有文化规则，清点1337.4.1全部 **2086条**正人口文化。完成 **546条新增来源、171条旧疑问及5条既有犹太社群**的重点复核，共722条。其余既有来源沿用现有框架，未宣称重新逐项考证其全部历史。

**没有实装。** 已写出明确对应、旧错配调整、名称范围、语言证据、传承、本土和姓名使用限制。审查结论与游戏资产制作分别记录，不能把本报告直接当作可启动模组。

## 与初稿相比的处理

- 旧疑问不再只列“待核”：每条均有保留宽类、明确合称、撤回邻族替换或保留证据不足标签的结论。
- 离线候选中调整87条对应；正式配置仍未改变。原有范围问题采用“女真—满洲”“傣—掸”“努米克”“图皮族群”等明确宽称，并冻结源成员。
- 无充分依据的具体民族替换撤回。考古标签保留源身份，不强制变成现代后继民族，也不因现实历史中消亡而删除反事实存档人口。
- 语言目录核对171条重点来源，并排除同名错配：例如巴拉圭Aché不能匹配中国Ache，美洲Yurí不能匹配新几内亚Yuri，密西西比Koroa不能匹配巴西Acroá。
- **92条**仍存在本轮证据不足、标签含混或非普通谱系问题；处理规则是保留来源、不强配语言家族、不凭猜测合并。本轮审查完成不等于这些历史疑点已有确定答案。

## 犹太社群

|社群|1337源人数|1780源人数|处理|
|---|---:|---:|---|
'''
    for r in rows:
        if 'jewish_group' in r['source_groups']:
            report+=f"|{r['source_name']}|{r['population_1337_centipersons']/100:,.2f}|{r['population_1780_centipersons']/100:,.2f}|{r['target_name']}|\n"
    report+='''
阿什肯纳兹并没有在1780完全消失，只剩2.48人。开封犹太在1337为2,059.61人，1780未检出。这里的“未检出”只是这份存档的结果，不是真实历史灭绝判断。

开封社群独立保留，不能因共同宗教并入阿什肯纳兹或塞法迪，也不能因居于开封就授予整个河南州本土。其1337日常语证据不足，方案使用来源专用语言占位，明确不声称已知亲缘。意大利、罗曼尼奥特、波斯、格鲁吉亚社群复用相应宽语言资产，保留社群语体记录；柯枝不直接照抄原版Tamil–Tulu为精确马拉雅拉姆语。依据见 [HUC语言目录](https://www.jewishlanguages.org/languages) 与 [开封社群研究](https://cismor.jp/uploads-images/sites/3/2014/03/Tracing-Judaism-in-China.pdf)。

## 明确纠错与证据边界

|对象|处理结论|
|---|---|
'''
    for k in ['burusho','tunica_culture','nuxalc_culture','kunama_culture','kuiba_culture','yugur_culture','cueva_culture','pasto_culture','muzo_culture','hohokam_culture','cahokia_culture','dorset_culture','lozi_culture','mi_niah_culture','kallawaya_culture']:
        r=by[k];ref=' '.join(f'[依据{i+1}]({u})' for i,u in enumerate(r['reference_urls'][:2]))
        report+=f"|{r['source_name']} `{k}`|{r['review_conclusion']} {r['language_review']} {ref}|\n"
    report+=f'''
## 传承、姓名、外观和本土

文化身份与传承分开。新增身份复用现有地区传承；这属于接纳玩法设计，不能反向解释成同族或同一语系。原版宽类仍允许保留，但成员与显示范围必须清楚。

已检查重点来源的源语言姓名池和文化外观标签。720条有男女姓名池条目，2条缺少完整池；存在姓名池只证明游戏资源存在，不证明其中姓名都适合1337。语言纠错后不得继续照搬错误语言的姓名池，不编造“古民族姓名”。源图形标签只作游戏表现参考；例如埃塞俄比亚犹太不能因为既有资产采用欧洲模板，就把欧洲外观当族源结论。

本土只保留1337分布证据，本次不自动赋州级本土。迁移分支要按实际日期、源文化与居住区域重新运行，不复制1780的14个分支结果，也不补造后世迁移。

## 文化数量审查

保守保留身份的完整候选有 **{s['base_resident_targets']}类基础居民目标**，其中新增资产设计 **{s['final_new_asset_designs']}类**。若全部制作且保留现有定义，有效定义会达到 **{s['effective_definitions_if_all_added']}**。

这超过现有605使用文化、665有效定义的工程上限。**本方案不能整体直接实装，生产上限也没有被偷偷提高。** 下一阶段需要在这些已明确的成员与语言证据上形成有限合称／复用方案，或者单独验证更高资产预算；不能靠把不相关民族随意塞进邻族来满足上限。这里没有声称已做游戏速度实测。

## 通用转换规则

1. 从每份源存档实际人口构建文化全集；1780文化清单只是已有覆盖范围，不是通用白名单。
2. 对未知文化明确报出来源，禁止静默套入俄罗斯、当地统治者文化或最近民族。
3. 未殖民地先确定源地区主体文化，再执行民族框架映射，最后合并同一目标民族的相邻地块。映射、国家连片与POP文化保存是三个步骤。
4. 地理归属参考只补足地理证据；有殖民者或混合人口时按源人口、实际政治状况判断，不能因为地块白色就全改成原住民。
5. 语言、身份、传承、宗教、本土单独处理。资料不足保留源标签，不以AI猜测生成古语言亲缘、民族比例或整州本土。

## 交付与验证

- [可搜索清单](index.html)：全部2086来源及本轮结论。
- [重点复核结论CSV](review_decisions.csv)、[旧问题处理CSV](inherited_review_decisions.csv)、[证据不足的处理清单](uncertainty_dispositions.csv)。
- [候选映射](candidate_mapping.json)、[资产设计](candidate_assets.json)、[完整审查记录](audit.json)。
- [回读验证](validation.json)：源覆盖完整、394,540,033.77人口守恒、逐目标合计一致，安装文件、正式配置和工作站审核未改变。

Glottolog使用官方公开CLDF数据与别名表，逐条证据保留目录链接，下载文件哈希写入完整记录。其现代语言分类不被当作1337人口、边界或自我认同的直接证据。资料许可与项目说明见 [Glottolog CLDF](https://github.com/glottolog/glottolog-cldf)。
'''
    (OUT/'README.md').write_text(report,encoding='utf-8')
    payload=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>1337文化审查</title><style>body{font:15px/1.6 system-ui,"Microsoft YaHei";margin:28px;color:#20344d;background:#f7f9fc}a{color:#1263a5}input,select,button{font:inherit;padding:8px;margin:8px}input{width:42%}table{border-collapse:collapse;background:white;width:100%}th,td{padding:11px;border-bottom:1px solid #dce3eb;text-align:left;vertical-align:top}th{background:#e2eaf4}.notice{background:#fff1d4;padding:14px}small{color:#526d89}</style><h1>1337文化审查</h1><p>2086条来源，722条重点复核。546条1337新增和171条旧问题均已给出处理结论。</p><p class="notice">未实装。92条保留证据不足的明确处理规则。保守身份方案有827类基础目标，超过现有605使用上限；资产方案不能直接整体安装。</p><p><a href="README.md">审查报告</a> · <a href="review_decisions.csv">复核结论CSV</a> · <a href="candidate_mapping.json">候选映射</a> · <a href="1337文化审查.xlsx">审查工作簿</a></p><input id="q" placeholder="名称、源键、语言、结论…"><select id="mode"><option value="new">1337新增</option><option value="reviewed">全部重点复核</option><option value="legacy">旧问题</option><option value="uncertain">证据不足的保留处理</option><option value="jewish">犹太社群</option><option value="all">全部2086条</option></select><span id="count"></span><p><button id="prev">上一页</button><button id="next">下一页</button></p><table><thead><tr><th>源文化</th><th>1337 / 1780人数</th><th>候选目标</th><th>复核结论</th><th>语言证据与处置</th><th>姓名及外观</th><th>来源</th></tr></thead><tbody id="body"></tbody></table><script>const rows=PAYLOAD;let page=0;const el=id=>document.getElementById(id);function show(){const q=el('q').value.toLowerCase(),mode=el('mode').value;const found=rows.filter(r=>(mode==='all'||mode==='new'&&r.new_in_1337||mode==='reviewed'&&r.review_completed||mode==='legacy'&&['scope_design','historical_review','source_label_review'].includes(r.inherited_audit)||mode==='uncertain'&&r.evidence_disposition.startsWith('资料不足')||mode==='jewish'&&r.source_groups.includes('jewish_group'))&&JSON.stringify(r).toLowerCase().includes(q));page=Math.min(page,Math.max(0,Math.ceil(found.length/60)-1));el('body').replaceChildren();for(const r of found.slice(page*60,page*60+60)){const tr=document.createElement('tr');for(const v of [r.source_name+' ['+r.source_culture+']',(r.population_1337_centipersons/100).toLocaleString()+' / '+(r.population_1780_centipersons/100).toLocaleString(),r.target_name+' ['+r.target_culture+']',r.review_conclusion,r.language_review+' '+r.language_treatment,r.name_policy+' '+r.graphics_policy]){const td=document.createElement('td');td.textContent=v;tr.append(td)}const td=document.createElement('td');for(const [i,url] of r.reference_urls.entries()){const a=document.createElement('a');a.href=url;a.textContent='依据'+(i+1)+' ';a.target='_blank';a.rel='noopener';td.append(a)}if(!r.reference_urls.length)td.textContent='源存档／既有规则；未宣称外部史实已证';tr.append(td);el('body').append(tr)}el('count').textContent=found.length+'条，第'+(page+1)+'页';el('prev').disabled=page===0;el('next').disabled=(page+1)*60>=found.length}el('q').oninput=el('mode').onchange=()=>{page=0;show()};el('prev').onclick=()=>{page--;show()};el('next').onclick=()=>{page++;show()};show()</script></html>'''.replace('PAYLOAD',payload)
    (OUT/'index.html').write_text(page,encoding='utf-8')

if __name__=='__main__':build()
