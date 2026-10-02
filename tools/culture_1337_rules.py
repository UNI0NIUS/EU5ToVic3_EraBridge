"""Review-draft decisions for the frozen 1337 inventory; not production policy.

The report freezes every selected member explicitly. Group selectors below are
authoring aids for this audit only, never converter fallbacks for unseen cultures.
"""
REFS = {
 'australia':('AIATSIS：澳洲原住民地图及适用边界','https://aiatsis.gov.au/explore/map-indigenous-australia','群体多样性；现代资料不证明1337精确边界。'),
 'torres':('AIATSIS：澳洲原住民族与托雷斯海峡岛民','https://aiatsis.gov.au/explore/first-peoples-australia','区分岛民与大陆原住民族；不按Papuan标签直接并入新几内亚。'),
 'melanesia':('ANU：岛屿美拉尼西亚考古','https://press.anu.edu.au/publications/series/terra-australis/archaeologies-island-melanesia','新几内亚至所罗门、瓦努阿图和新喀里多尼亚的区域尺度；不是单一民族。'),
 'oceanic':('ANU：大洋洲语言的分化','https://press.anu.edu.au/downloads/press/p69411/mobile/ch03s03.html','区分新喀里多尼亚、瓦努阿图、密克罗尼西亚和波利尼西亚支系。'),
 'timor':('Timor–Alor–Pantar语言研究','https://brill.com/view/journals/ldc/12/2/article-p274_3.pdf','Bunak、Fataluku位于帝汶；Papuan不等于地理上的美拉尼西亚。'),
 'kaifeng':('徐新：Tracing Judaism in China','https://cismor.jp/uploads-images/sites/3/2014/03/Tracing-Judaism-in-China.pdf','开封社群及碑刻传统；不能据此确认1337全部日常语言。'),
 'jewish':('HUC Jewish Language Project：语言目录','https://www.jewishlanguages.org/languages','犹太社群语言多样性；宗教共同不代表只有一种族群或口语。'),
 'romaniote':('HUC：Judeo-Greek','https://www.jewishlanguages.org/judeo-greek','罗曼尼奥特希腊语传统，不能提前套用后来的塞法迪语言替代。'),
 'italki':('HUC：Judeo-Italian','https://www.jewishlanguages.org/judeo-italian','犹太意大利语传统；不是一律意第绪语。'),
 'kochini':('HUC：Jewish Malayalam','https://www.jewishlanguages.org/jewish-malayalam','柯枝社群语言传统；现代描述不单独认证1337具体方言。'),
 'kalimi':('HUC：Judeo-Persian','https://www.jewishlanguages.org/judeo-persian','犹太波斯语传统；不套用黎凡特阿拉伯语。'),
 'burusho':('Iranica：Burushaski','https://www.iranicaonline.org/articles/burushaski-language-spoken-in-hunza-karakorum-north-pakista/','布鲁绍语言未证实与其他语系有亲缘关系；反对克什米尔语替代。'),
 'tunica':('Tunica-Biloxi / American Philosophical Society：Tunica语言','https://tunica-biloxi.amphilsoc.org/additional-resources/insights/','图尼卡为孤立语言；不能照抄乔克托语言组。'),
 'northwest':('First Peoples Cultural Council：语言目录','https://maps.fpcc.ca/languages','努哈尔克属萨利希语系；瓦卡什诸语言和海达另列。'),
 'nakoda':('A Grammar of Nakoda (Assiniboine)','https://www.jstor.org/stable/jj.29722263','Nakoda属苏语系；不能因源分组而套入阿拉帕霍语言。'),
 'mandean':('Iranica：Mandaic Language','https://www.iranicaonline.org/articles/mandaeans/mandaeans-v-mandaic-language/','曼达语的阿拉米语传统；不把伊拉克阿拉伯方言字段当作全部历史语言。'),
 'kunama':('Glottolog：Kunama','https://glottolog.org/resource/languoid/id/kuna1268','独立Kunama语言条目；反对埃及阿拉伯语替代。'),
 'qashqai':('Iranica：Qashqai历史','https://www.iranicaonline.org/articles/qasqai-tribal-confederacy-i/','后世联盟的多来源性质；1337标签不能直接认证后世政治、迁移与边界。'),
 'taino':('Smithsonian：加勒比原住民遗产与身份','https://www.si.edu/exhibitions/taino-native-heritage-and-identity-caribbean%3Aevent-exhib-6313','支持泰诺历史身份；不将资料未涵盖的西瓜约等自动认定为泰诺。'),
}

def propose(new, catalog):
    result={}
    def put(names,target,reason,refs=(),status='existing_category'):
        for n in names:
            if n not in new:raise ValueError('Decision outside new inventory: '+n)
            if n in result:raise ValueError('Duplicate decision: '+n)
            result[n]=dict(target=target,status=status,reason=reason,refs=list(refs))
    def group(g,target,reason,refs=(),exclude=()):
        put(sorted(n for n in new if g in catalog[n]['groups'] and n not in exclude),target,reason,refs)
    def keys(text):return text.split()
    def suff(text):return [n+'_culture' for n in text.split()]
    group('australian_group','aborigine','延续原版澳洲原住民宽类别；逐源身份、人口、地点另存，不声称为单一民族或语言。',('australia',))
    group('papuan_group','melanesian','核对新几内亚及邻近岛屿的原版宽类别；保留源语言，不把Papuan当作单一语族。',('melanesia',),exclude=suff('bunak fataluku kalaw_lagaw_ya'))
    group('micronesian_group','melanesian','这13项实际对应瓦努阿图、新喀里多尼亚及洛亚蒂群岛；不照抄源Micronesian分组。',('melanesia','oceanic'))
    group('polynesian_group','polynesian','沿用原版波利尼西亚宽类别，保留各岛源身份。',('oceanic',))
    group('tungusic_group','siberian','沿用既有西伯利亚宽类别；源通古斯身份不因此被认作单一鄂温克语言。')
    group('nadene_group','athabaskan','北方Dene成员明确列入原版阿萨巴斯卡宽类别；不扩至特林吉特、埃亚克或所有Na-Dene。',exclude=suff('naadahende'))
    put(suff('naadahende'),'apache','源南方阿帕奇成员归原版Apache，不跟随北方Dene批次。')
    for g,t in [('macro_je_group','amazonian'),('dakota_group','dakota'),('anishinabe_group','algonquian'),('cree_group','cree'),('khoisan_group','khoisan'),('powhatan_group','algonquian'),('salishan_group','salish'),('caddoan_group','caddoan'),('haudenosaunee_group','iroquoian'),('iroquoian_group','iroquoian'),('maya_group','mayan'),('myaamia_group','algonquian'),('tutelo_group','siouan'),('chiwere_group','siouan'),('apsaalooke_hiraaca_group','siouan')]:
        group(g,t,'延续原版已采用的宽类别，冻结本批源成员；语言与身份不据此宣布等同。')
    # These are finite membership decisions, not generic same-language rules.
    batches={
      'dayak':'bahau_culture maanyan_culture',
      'bornean':'murut_culture tidung_culture',
      'moluccan':'buru_culture kei_culture maba_culture seramese_culture sula_culture tidore_culture',
      'filipino':'bugkalot_culture gaddang_culture ibaloi_culture ifugao_culture itneg_culture ivatan_culture palawan_culture sambal_culture',
      'lumad':'blaan_culture bukidnon_culture mandaya_culture manobo_culture tboli_culture',
      'visayan':'romblomanon_culture surigaonon_culture',
      'equatorial_bantu':'bandjabi eshira kota_gabun mitsogo omiene',
      'lacustrine_bantu':'singa_culture',
      'cariban':'chaima_culture cumanagoto_culture enepas_culture guaribes_culture kura_culture ukaragma_culture',
      'amazonian':'anambe_culture apiaka_culture awaete_culture purubora_culture wajuru_culture xeta_culture zoe_culture haliti_culture terena_culture karapana_culture towa_panka_culture',
      'hokan':'guaicura_culture mongui_culture pericu_culture pomo_culture quechan_culture xalychidom_culture hualapai_culture',
      'pueblo':'keres_culture hopi_culture',
      'paiute':'kawaiisu_culture',
      'algonquian':'hinonoeino_culture meskwaki_culture penobscot_culture sotaeoo_culture',
      'iroquoian':'agojuda_culture',
      'muskogean':'acolapissa_culture hitchiti_culture sawokli_culture',
      'siberian':'enets_culture ket_culture nganasan_culture tavgi_culture khakas_culture kumandin_culture shor_culture telengit_culture tubalar_culture',
      'polynesian':'',
      'finnish':'finnish savonian',
      'sami':'sapmi',
      'sorb':'sorbian',
      'sephardic':'sephardi',
      'nuer':'nuer_culture',
      'guajiro':'wayuu_culture',
      'miskito':'miskito_culture',
      'sudanese':'sudanese_arab',
      'mande':'susu',
    }
    for target,text in batches.items():
        if text:put(keys(text),target,'逐项列明的现有类别对应；宽类不构成具体支系同义或1337历史边界证明。')
    put(suff('nuxalc'),'salish','修正源Wakashan分组：努哈尔克属萨利希语系；采用现有宽类。',('northwest',),'source_field_correction')
    put(suff('nanwuinenan'),'siouan','源本地化为阿西尼博因/Nakoda，源阿拉帕霍组和语言不宜照抄；采用苏语宽类。',('nakoda',),'source_field_correction')
    # Closed inherited composite: the new member is proposed explicitly, not
    # silently appended to the production membership list.
    put(suff('south_valley_yokut'),'eu5_resident_north_valley_yokut_culture','候选显式补入南谷约库茨，扩充原有约库茨合称；不并入其他Penutian成员。',(), 'extend_closed_composite')
    return result


# Explicit regional heritage/template hints for identities lacking a safe
# existing culture category. Sharing heritage is not ethnic merger. Each
# blueprint keeps its language decision separate and has no new homeland grant.
PRESERVE_BATCHES=[
 ('persian','achomi_culture ormur_culture jasz_culture','伊朗相关传统圈'),
 ('tibetan','baima_culture changpa_culture','藏地相关传统圈'),
 ('burmese','danu_culture','缅甸宽传承'),
 ('bedouin','dhofari_culture mehri_culture shihhi_culture','阿拉伯半岛宽传承'),
 ('sidama','gedeo_culture hadiya_culture kambaata_culture','埃塞俄比亚高地南部宽传承'),
 ('amhara','harla_culture','埃塞俄比亚相关传统圈；历史身份范围待核'),
 ('kashmiri','burusho','喜马拉雅接触圈；语言必须与克什米尔分开'),
 ('kannada','kodaga','德干南部宽传承'),
 ('malayalam','beary','南印度宽传承'),
 ('oriya','halbi','印度东部宽传承'),
 ('pahari','kangri','喜马拉雅南缘宽传承'),
 ('nepali','kirati_culture','喜马拉雅宽传承；不把泛基拉特等同林布'),
 ('gondi','juang_culture','印度东部山地宽传承'),
 ('sinhala','vedda','斯里兰卡接触圈；不是僧伽罗民族别名'),
 ('mashriqi','mandean_culture samaritan_culture','近东历史社群；传承接纳取舍待核'),
 ('georgian','gurji','格鲁吉亚犹太社群；共用地区传承不合并身份'),
 ('han','qayfengi','中国犹太社群；汉传承为接纳设计候选，不等于改为汉族'),
 ('persian','kalimi','波斯犹太社群；不套用黎凡特阿拉伯语言'),
 ('greek','romanyoti','希腊犹太社群；不并入塞法迪'),
 ('north_italian','italki','意大利犹太社群；不并入阿什肯纳兹'),
 ('malayalam','kochini','柯枝犹太社群；不改变居民宗教'),
 ('north_german','gothic_culture','日耳曼宽传承；哥特语言独立处理'),
 ('greek','griko_culture','希腊宽传承；意大利希腊社群保留名称'),
 ('swedish','gutnish','北欧宽传承；哥得兰源身份保留'),
 ('finnish','ingrian kvens vepsian votian','芬兰相关宽传承；不同源语言保留'),
 ('romanian','istroromanian','罗马尼亚宽传承；保留伊斯特拉分支'),
 ('south_italian','southern_gallo_italic','意大利宽传承；不照抄南意大利语言'),
 ('sorb','polabian','西斯拉夫宽传承；不把波拉布改为索布民族'),
 ('lithuanian','sudovian','波罗的海宽传承；存续源身份不按现实灭绝删去'),
 ('slovene','sclavene','南斯拉夫宽传承；宽泛历史源标签不窄化成塞尔维亚人'),
 ('korean','tamna_culture','朝鲜半岛相关传承；保留耽罗源身份'),
 ('yue','danzhou_culture','汉相关传承；儋州语言不能仅靠源粤语字段定论'),
 ('mongol','sarta_culture yugur_culture','蒙古相关宽传承；裕固多语言问题单列'),
 ('turkmen','salar_culture qashqai_culture','中亚突厥宽传承；不合并撒拉或卡什加身份'),
 ('eu5_resident_domari_culture','romani_culture lomari_culture','跨区流动社群；不直接吸收进多姆，具体传承暂缓'),
 ('eu5_resident_huetar_culture','botos_culture katapas_culture tises_culture cueva_culture ette_ennaka_culture maleku_culture naso_culture pech_culture','既有地峡—哥伦比亚共享传承'),
 ('eu5_resident_makah_culture','haida_culture haisla_culture heiltsuk_culture kwakiutl_culture nootka_culture oowekyala_culture','西北海岸共享传承；海达语言不并入瓦卡什'),
 ('eu5_resident_natchez_culture','koroa_culture yazoo_culture tunica_culture cusabo_culture ais_culture','东南原住民传承；不扩大纳切兹—提乌合称'),
 ('eu5_resident_coahuilteco_culture','comecrudo_culture karankawa_culture irritila_culture guarijio_culture','既有北墨西哥旱地共享传承；各源语言另核'),
 ('eu5_resident_lucayo','taino_culture ciguayo_culture macorix_culture guanahatabey igneri','加勒比共享传承；不默认五者与卢卡约为同一民族或语言'),
 ('eu5_resident_huetar_culture','ayamanes_culture kuiba_culture pume_culture warao_culture','南美北部低地接触圈；来源语系不被模板替代'),
 ('eu5_resident_huetar_culture','kukra_culture','地峡接触圈；不等同米斯基托'),
 ('quechua','chimbus_culture hambatus_culture quitu_culture kayambi_culture kolla_culture lule_culture pasto_culture tatuy_culture muzo_culture napuruna_culture','既有安第斯宽传承；不能因前印加地理归属而克丘亚化'),
 ('patagonian','manekenk_culture','南端原住民宽传承；保留豪什源身份'),
 ('patagonian','charrua_culture guenoa_culture yaros_culture bohan_culture','拉普拉塔地区；不直接改称巴塔哥尼亚民族'),
 ('guarani','abipones_culture guaikuru_culture lumnana_culture makas_culture moqoit_culture nivacle_culture pitlaxa_culture wichi_culture enenlhet_culture enlhet_culture enxet_culture guana_culture nenlhet_culture ayoreo_culture yshyr_culture','大查科接触圈；使用瓜拉尼传承仅为候选玩法设计，保留马塔科等独立语言'),
 ('guarani','ache_culture tapiiete_culture','南美南部图皮—瓜拉尼接触圈；不视为源身份同义'),
 ('tupinamba','apyawa_culture potiguara_culture tabajara_culture tenetehara_culture tremembe_culture wapaji_culture','巴西东部与图皮相关接触圈；不新增图皮系一律图皮南巴的身份替换'),
 ('amazonian','aikana_culture shuar_culture monkox_culture kambiwa_culture truka_culture takana_culture henia_culture sanaviron_culture tonokote_culture uakambalelte_culture','南美原住民宽传承候选；地理边缘和孤立语言另列待核'),
 ('hokan','wappo_culture yuki_culture taxliswet_culture','加州原住民传承；Yuki等不照搬Hokan语言'),
 ('equatorial_bantu','baka_culture gyele_culture','中非接触圈；不宣称共同语言或迁移历史'),
 ('dinka','kadu_culture kunama_culture surma_culture','尼罗周边宽传承候选；卡杜、库纳马不可变成丁卡语言'),
 ('shona','venda_culture','南部班图宽传承；文达语言独立审查'),
 ('moluccan','banggai_culture saluan_culture muna_culture','印苏林迪亚共享传承；苏拉威西身份不改成摩鹿加'),
 ('eu5_resident_atoni_culture','bunak_culture fataluku_culture helong_culture rotenese_culture','帝汶及相邻岛屿；身份、语言不并入阿托尼'),
 ('eu5_resident_sumba_culture','hawu_culture lio_culture manggarai_culture sikka_culture sumbawa_culture','小巽他共享传承；不合并进松巴或巴厘民族'),
 ('aborigine','kalaw_lagaw_ya_culture','托雷斯海峡岛民身份保留；现有澳洲传承接纳设计待核'),
]

SPECIAL = {
 'qayfengi':dict(refs=['kaifeng','jewish'],language='1337日常语言待核；保留源southern_mandarin字段，不能仅凭后世汉化断言1337只用汉语；不自动改为希伯来语。',issue='少数社群与语言年代',homeland='开封为社群核心候选；仅一座社群不自动授予整个河南州本土。'),
 'romanyoti':dict(refs=['romaniote'],language='希腊犹太语传统；可先复用希腊语言粒度，保留社群身份；不采用Ladino。'),
 'italki':dict(refs=['italki'],language='意大利犹太语传统；可复用意大利宽语言，不把源lombard字段解释为全社群只用伦巴第语。'),
 'kochini':dict(refs=['kochini'],language='马拉雅拉姆犹太语传统；原版malayalam资产使用Tamil–Tulu，仅可作模板，不能当精确语言对应。'),
 'kalimi':dict(refs=['kalimi'],language='犹太波斯语传统；建议波斯语粒度，不套用旧Mizrahi的黎凡特语言。'),
 'gurji':dict(refs=['jewish'],language='格鲁吉亚犹太社群；格鲁吉亚语言粒度候选，具体历史变体仍待核。'),
 'sephardi':dict(refs=['jewish'],language='沿用原版Sephardic身份；Ladino资产的后世离散语形式不可当作1337全部伊比利亚犹太人的精确语言。',issue='既有资产语言年代'),
 'burusho':dict(refs=['burusho'],language='改为Burushaski语言候选，并保持独立语言组；拒绝Kashmiri/印欧语族自动归类。',issue='源语言明确错配'),
 'tunica_culture':dict(refs=['tunica'],language='图尼卡孤立语言候选；拒绝Chickasaw–Choctaw语言对应。',issue='源语言明确错配'),
 'nuxalc_culture':dict(refs=['northwest'],language='采用Salishan/Salish语言粒度，拒绝源Wakashan字段。',issue='源语言明确错配'),
 'nanwuinenan_culture':dict(refs=['nakoda'],language='源显示名Assiniboine对应Nakoda/Siouan；不采用Arapaho语言。1337族名时段另核。',issue='源组、语言及族名时段'),
 'kunama_culture':dict(refs=['kunama'],language='独立Kunama语言候选；拒绝源Egyptian Arabic字段；更高语系分类不在此强定。',issue='源语言明确错配'),
 'mandean_culture':dict(refs=['mandean'],language='曼达语/阿拉米语传统；不能仅凭源Iraqi Arabic取代全部口语与礼仪语言。',issue='语言层次需区分'),
 'bunak_culture':dict(refs=['timor'],language='Bunak独立语言，TAP语言家族；不随Papuan组归为新几内亚身份。',issue='源分组不能替代地理'),
 'fataluku_culture':dict(refs=['timor'],language='Fataluku独立语言，TAP语言家族；不随Papuan组归为新几内亚身份。',issue='源分组不能替代地理'),
 'kalaw_lagaw_ya_culture':dict(refs=['torres'],language='托雷斯海峡Kalaw Lagaw Ya单列；源Papuan分组不作为语言亲缘证据。',issue='源分组与岛民身份'),
 'qashqai_culture':dict(refs=['qashqai'],language='乌古斯突厥语相关候选；不套用后世联盟范围或迁移史。',issue='源族名可能存在时代投射'),
 'taino_culture':dict(refs=['taino'],language='泰诺语言候选可复用已生成的Taino语言特质；保持与卢卡约的来源区别。'),
 'ciguayo_culture':dict(refs=['taino'],language='亲缘证据不足；保留源标签，暂不断言Arawakan或与Macorix同语。',issue='历史语言资料不足'),
 'macorix_culture':dict(refs=['taino'],language='亲缘证据不足；源ciguayo_language只是游戏字段，不认作历史定论。',issue='历史语言资料不足'),
 'guanahatabey':dict(refs=['taino'],language='古加勒比源身份保留；源ciguayo_language不作为确定亲缘证据。',issue='历史语言资料不足'),
 'haida_culture':dict(refs=['northwest'],language='Haida语言单列；不跟随Makah模板套用Wakashan。'),
 'south_valley_yokut_culture':dict(language='约库茨语言集合；只扩充明确列出的南谷成员，不扩至整个Penutian。',issue='封闭合称增补需审定'),
}

def complete_proposals(new,catalog,definitions):
    result=propose(new,catalog)
    for template,text,reason in PRESERVE_BATCHES:
        for n in text.split():
            if n not in new:raise ValueError('Preservation entry not new: '+n)
            if n in result:
                # Bohan has a broad source group but a Southern Cone identity;
                # explicitly override that authoring cohort, never duplicate silently.
                if n!='bohan_culture':raise ValueError('Preservation overlaps decision: '+n)
            result[n]=dict(target='eu5_resident_'+n,status='preserve_identity_candidate',template=template,
                           reason=reason+'。只提供文化资产设计，姓名/外观/本土未据模板自动通过。',refs=[])
    missing=set(new)-result.keys()
    if missing:raise ValueError('New identities lack explicit decision: '+' '.join(sorted(missing)))
    for n,r in result.items():
        special=SPECIAL.get(n,{})
        r['refs']=list(dict.fromkeys(r['refs']+special.get('refs',[])))
        r['language_note']=special.get('language','原始语言字段保留在台账；现有宽类语言为玩法抽象，新资产语言需单独核查。')
        r['issue']=special.get('issue','新映射成员范围及1337历史边界尚需审定')
        r['homeland_note']=special.get('homeland','不继承1780本土州；1337当前分布仅作证据，不自动生成全州本土。')
        if r['target'] in definitions:
            r['heritage_candidate']=definitions[r['target']].get('heritage','')
            r['language_candidate']=definitions[r['target']].get('language','')
        else:
            template=definitions.get(r['template'],{})
            r['heritage_candidate']=template.get('heritage','')
            r['language_candidate']=''
        r['asset_complete']=False
    return result
