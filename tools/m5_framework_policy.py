"""Explicit framework decisions. Evidence is not a claim of exhaustive history.

Culture, shared heritage, language and homeland are separate decisions. Unknown
archaeological languages get separate mechanical traits, not invented ancestry.
"""
from m5_identity_audit_rules import FINDINGS, SOURCES, SOURCE_BROAD

REFS = {
 'tangut':'https://rubinmuseum.org/projecthimalayanart/glossary/tanguts/',
 'achang':'https://www.neac.gov.cn/seac/ztzl/acz/lsyg.shtml',
 'kadu':'https://sealang.net/archives/ltba/pdf/LTBA-36.2.15.pdf',
 'katuic':'https://www.researchgate.net/publication/327860779_Language_Shift_and_Maintenance_of_Non-Tai_Communities_in_Northeastern_Thailand_Kuay_and_Bru',
 'monpa':'https://www.neac.gov.cn/seac/ztzl/mbz/lsyg.shtml',
 'kohistani':'https://www.iranicaonline.org/articles/dardestan-ii-languages/',
 'zaza':'https://www.iranicaonline.org/articles/dimli/',
 'unangan':'https://www.nps.gov/aleu/learn/historyculture/unangax-history-and-culture.htm',
 'gula':'https://asjp.clld.org/languages/GULA_IRO',
 'cahokia':'https://www.nps.gov/articles/000/cahokia-mounds-state-historic-site-world-heritage-site.htm',
 'quimbaya':'https://enciclopedia.banrepcultural.org/Quimbaya',
 'tumaco':'https://publicaciones.banrepcultural.org/index.php/fian/article/view/5434/0',
 'pankararu':'https://pib.socioambiental.org/pt/Povo%3APankararu',
 'mapuche':'https://www.memoriachilena.gob.cl/archivos2/pdfs/MC0070055.pdf',
 'lunda':'https://fowler.ucla.edu/exhibitions/makishi-mask-characters-of-zambia/',
 'luba':'https://www.metmuseum.org/de/essays/kingdoms-of-the-savanna-the-luba-and-lunda-empires',
 'gilan':'https://www.iranicaonline.org/articles/gilan-x/',
 'abkhaz':'https://academic.oup.com/edited-volume/37095/chapter-abstract/323239876',
 'sardinian':'https://www.sardegnacultura.it/categoria/lingua/storia-della-lingua',
 'anglo_irish':'https://academic.oup.com/reference/62337/reference-article-abstract/554129006',
 'ciboney':'https://www.cambridge.org/core/journals/antiquity/article/creating-the-guanahatabey-ciboney-the-modern-genesis-of-an-extinct-culture/33C6799D77A0B74B7CCC10DBE6AC78D6',
}
REFS.update({k:v[1] for k,v in SOURCES.items()})


def policy():
    p={'schema':1,'audit':'.local/m5/culture-identity-audit/20261003-010045-202813/audit.json','mappings':{},'assets':{},'overrides':{},'labels':{},'decisions':{},
       'sources':REFS,'budget':{'max_used_cultures':640,'max_effective_cultures':705,'max_population_groups':16100,'max_new_cultures':30,'max_resident_assets':380},
       'policy':'Retain native broad classes. Closed composites are gameplay aggregates, not synonyms or claims of shared ethnic identity. Reuse existing heritage and heritage groups. Historical cores are independently projected; migrants retain strict statewide >50%. No blanket historical approval of inherited names, appearance or source language hypotheses.',
       'asset_limitations':'Name pools and appearance are inherited. Archaeological continuity is alternate-history survival from the source save; uncertain language traits are mechanical distinctions, not attested language families.'}
    def asset(key, members, en,zh,template,heritage,lang,group,states,anchors,refs,basis):
        target='eu5_framework_'+key
        p['mappings'].update({s:target for s in members.split()})
        spec={'labels':[en,zh],'template':template,'heritage':heritage,'homelands':states.split(),
              'anchors':anchors.split(),'homeland_sources':[REFS[r] for r in refs.split()], 'homeland_basis':basis}
        if lang.startswith(('language_','eu5_')):spec['language']=lang
        else:spec['new_language']=[key,group,lang,zh+'语']
        p['assets'][target]=spec
    asset('tangut','mi_niah_culture','Tangut','党项','tibetan','heritage_tibetan','Tangut','language_group_tibeto_burman',
          'STATE_NINGXIA','ningxia','tangut','EU5 Chinese label and source comment identify Tangut, not modern Muya; Western Xia core. Tibetan heritage is a broad gameplay grouping.')
    asset('achang','ngacang_culture','Achang','阿昌','kachin','heritage_burmese','Achang','language_group_tibeto_burman',
          'STATE_YUNNAN','tengchong','achang','Husa and Lianghe core recorded before 1780; no automatic Putao or overseas claims.')
    asset('kadu','kado_culture','Kadu','卡杜','burmese','heritage_burmese','Kadu','language_group_tibeto_burman',
          'STATE_KACHIN','katha','kadu','Katha core; modern language evidence distinguishes Kadu from Burmese, not a census of 1780.')
    asset('bru_kuy','bru_culture kuy_culture','Bru–Kuy','布鲁—奎','khmu','heritage_cambodian','Bru and Kuy','language_group_austroasiatic',
          'STATE_LAOS STATE_NAKHON_RATCHASIMA','savannakhet khukhan','katuic','Closed two-member Katuic gameplay aggregate. Limited Mekong/Isan cores; modern fieldwork is a conservative geographic back-projection, not proof of a single historical nation.')
    asset('monpa','monpa_culture','Monpa','门巴','tibetan','heritage_tibetan','Monpa','language_group_tibeto_burman',
          'STATE_EASTERN_HIMALAYAS','tawang','monpa','Tawang/Monyul core. State projection is not a present-day sovereignty statement. No automatic claims from emigrants.')
    asset('kohistani','kohistani','Kohistani','科希斯坦','kashmiri','heritage_kashmiri','language_dardic',None,
          'STATE_KASHMIR','kandia','kohistani','Indus Kohistan core projected through Kandia; broad Dardic language is a gameplay simplification.')
    asset('zaza','zaza_culture','Zaza','扎扎','kurdish','heritage_iranian','Zazaki','language_group_iranic',
          'STATE_DIYARBAKIR','harput','zaza','Upper Euphrates core. Linguistic distinction does not settle contested modern Kurdish self-identification.')
    asset('unangan','unalaska_culture atka_culture attu_culture','Unangan','乌南干','inuit','heritage_circumpolar','Unangam Tunuu','language_group_eskaleut',
          'STATE_ALASKA','qawalangin','unangan','Three Aleut island identities merged into one established Unangan aggregate; coarse Alaska state includes Aleutian core, not every Alaskan region.')
    asset('lozi','lozi_culture','Luyi','卢伊','sotho','heritage_eastern_bantu','Luyana','language_group_bantu',
          'STATE_ZAMBIA','zambesia_katongo','lozi','Pre-Makololo Luyi/Barotse core; do not backdate the 1830s Sotho-language transformation to the source start.')
    asset('abkhaz_abaza','abkhazian_culture abazin_culture','Abkhaz–Abaza','阿布哈兹—阿巴扎','circassian','heritage_north_caucasian','Abkhaz and Abaza','language_group_circassic',
          'STATE_GREATER_CAUCASUS STATE_KUBAN','pitsunda costa','abkhaz','Closed two-member composite; preserve western Caucasus source-region cores, not all Circassian claims. Language survey establishes distinction, not exact 1780 boundaries.')
    asset('sardinian','sardinian','Sardinian','撒丁','south_italian','heritage_italic','Sardinian','language_group_romance',
          'STATE_SARDINIA','terralba','sardinian','Island historical language and identity; no continental South Italian homelands.')
    asset('anglo_irish','anglo_irish','Anglo-Irish','盎格鲁—爱尔兰','irish','heritage_british','language_anglophone',None,
          'STATE_LEINSTER','dublin','anglo_irish','Historical English-speaking Irish community, not automatically Protestant. Pale/Leinster core; no claim over all Ireland.')
    # Independent traits for unknown archaeological languages prevent a false
    # Hokan/Siouan/Cariban genealogical assertion and avoid grouping all unknowns.
    for key,member,en,zh,template,heritage,states,anchors,ref,basis in [
        ('ciboney','ciboney','Ciboney','西博内','amazonian','heritage_caribbean','STATE_WESTERN_CUBA','guaniguanico','ciboney','Cuban source identity retained, not Amazonian. Western Cuba is a bounded gameplay core under the older Ciboney interpretation; conflation with Guanahatabey and language remain disputed, not historically certified.'),
        ('hohokam','hohokam_culture','Hohokam','霍霍坎','oodham','heritage_southwest_indian','STATE_ARIZONA','tse_binestie','hohokam','Sonoran Salt/Gila archaeological core. Source survival retained; no unique modern descendant or Hokan language claim.'),
        ('cahokia','cahokia_culture','Cahokian','卡霍基亚','siouan','heritage_southeast_indian','STATE_ILLINOIS','cahokia','cahokia','American Bottom archaeological core. Does not equate archaeological Cahokia with the later Illinois tribe or certify a Siouan language.'),
        ('quimbaya','quimbaya_culture','Quimbaya','金巴亚','cariban','eu5_shared_heritage_isthmo_colombian','STATE_CUNDINAMARCA','otun','quimbaya','Middle Cauca core; distinguish archaeological periods and contact-era populations. Cariban affiliation is not established.'),
        ('tumaco','tumaco_culture','Tumaco–La Tolita','图马科—拉托利塔','cariban','eu5_shared_heritage_isthmo_colombian','STATE_ECUADOR','tumaco','tumaco','Pacific coastal core projected by mapped Tumaco to the coarse Ecuador state, not the surviving emigrants in Cajamarca. Language unknown.'),
        ('pankararu','pankararu_culture','Pankararu','潘卡拉鲁','tupinamba','heritage_atlantic','STATE_PERNAMBUCO','pankararu','pankararu','Pernambuco Sao Francisco core; source location spans two game states but only Pernambuco is granted. No assumption of Tupi language affiliation.')]:
        asset(key,member,en,zh,template,heritage,en,'eu5_framework_language_group_'+key,states,anchors,ref,basis)
    asset('gula_iro','gula_iro_culture','Gula Iro','伊罗古拉','sara','heritage_sahelian','Gula Iro','eu5_framework_language_group_bua',
          'STATE_WADDAI','bahr_salamat','gula','Lake Iro/Salamat core; Bua language, not Sara Gula. Modern linguistic location is a limited historical back-projection.')
    # Resolve over-narrow titles without creating a culture per dialect.
    p['labels'].update({
        'mazanderani':['Gilaki–Mazanderani','吉兰—马赞德兰'],
        'paiute':['Numic','努米克'],
        'tupinamba':['Tupi','图皮'],
        'rajput':['Rajasthani','拉贾斯坦'],
        'bedouin':['Bedouin','贝都因'],
        'burmese':['Burman–Arakanese','缅—若开'],
        'vietnamese':['Viet–Muong','越—芒'],
        'shan':['Shan–Dai','掸—傣'],
        'marathi':['Marathi–Konkani–Khandeshi','马拉地—孔卡尼—坎德什'],
        'uzbek':['Uzbek–Khwarezmian','乌兹别克—花剌子模'],
        'chuvash':['Chuvash–Volga Bulgar','楚瓦什—伏尔加保加尔'],
        'manchu':['Manchu–Jurchen–Sibe','满洲—女真—锡伯'],
        'chechen':['Nakh','纳赫'],
        'romanian':['Romanian–Aromanian','罗马尼亚—阿罗马尼亚'],
        'kanuri':['Kanuri–Kanembu','卡努里—卡涅姆布'],
        'eu5_chokwe':['Chokwe–Luvale–Mbunda','乔奎—卢瓦莱—姆本达'],
    })
    for s in 'mbunda luvale luchazi_culture'.split():p['mappings'][s]='eu5_chokwe'
    # Keep proven broad geographic categories when the source remains uncertain.
    p['mappings'].update({'manaos_culture':'amazonian','yuri_culture':'amazonian'})
    # Every old finding gets an explicit decision; unresolved evidence is never
    # relabeled as verified. Further changes require a new bounded policy.
    notes={
      'ciboney':'恢复加勒比西博内具名资产；西古巴为保守游戏核心。标签与Guanahatabey的混用及语言仍有争论，不作已知阿拉瓦克/西瓜约语断言。',
      'sardinian':'恢复撒丁居民及语言，复用原版意大利传承，本土限撒丁岛。',
      'anglo_irish':'恢复英语爱尔兰居民，继续共用不列颠传承；实际宗教完全保留。',
      'caucasus_west':'阿布哈兹—阿巴扎封闭合称，保留两成员，不直接改称切尔克斯。',
      'gilaki':'封闭合称吉兰—马赞德兰；继承原版伊朗传承，语言显示亦改为两成员合称。',
      'numic':'用努米克宽名涵盖肖肖尼、派尤特、尤特等；保留原版大盆地传承与努米克语言。',
      'tupi':'图皮南巴名称扩大为图皮；Catagua源语言为Macro-Je，另列证据缺口，不视为已确认图皮身份。',
      'tupi_uncertain':'Manaos/Yuri退回原版亚马孙宽类；Pankararu保留具名身份，不再断言图皮归属。',
      'rajput':'地区语言群不能都标为拉杰普特社会身份；使用拉贾斯坦宽称，原版传承不变。',
      'bedouin':'按用户命名偏好保留原版“贝都因”显示名；已审查的合并范围、居民宗教及传承不变。',
      'lozi':'恢复前科洛洛卢伊身份及语言；不把19世纪语言变化提前。',
      'minyak':'固定EU5注释和中文本地化明确为党项，不是木雅；恢复宁夏党项及藏缅语言。',
      'achang':'阿昌独立居民身份，复用缅甸大传承。',
      'kadu':'卡杜保留独立身份与Luish语言；复用缅甸大传承。',
      'kuy':'奎与布鲁组成成员封闭的游戏合称；共同大陆东南亚文化传统，不等于高棉民族。',
      'bru':'与奎共同采用封闭合称；取消克木语同义假定。',
      'muong':'使用越—芒合称，保留原版越语支及越南大传承，不宣称二者同民族。',
      'rakhine':'使用缅—若开合称；保留若开区域差异于来源台账，复用缅甸大传承。',
      'tai_shan':'掸—傣宽称；北傣与傣泐不全改称某一掸分支。',
      'thai_regions':'保留原版泰宽类，覆盖北部与南部区域来源；不把每个地方支系重建为资产。',
      'tibetan_border':'门巴保留具名身份；迭部按源定义藏族地域文化保留。',
      'marathi_border':'明确列出马拉地、孔卡尼、坎德什三个成员，避免窄名吞并。语言字段为游戏聚合，不声称同一种语言。',
      'kohistani':'科希斯坦独立身份，复用克什米尔传承与达尔德宽语类。',
      'khorezm':'源文化明确使用Karluk，合称仅涵盖突厥化花剌子模，不指古代伊朗语花剌子模。',
      'bulghar':'封闭楚瓦什—伏尔加保加尔连续传统；Oghuric不改成保加利亚斯拉夫语。',
      'jurchen':'满洲—女真合称符合本局存续来源；Hurga/Nanai仍有语言边界疑问，保留限制。',
      'sibe':'在满洲—女真—锡伯的明确宽称内保留来源，不认定锡伯即满族。',
      'nakh':'使用纳赫宽称，保留原版Vainakh语言和北高加索传承。',
      'german_diaspora':'保留原版德语文化粒度；移民来源在台账保留，不强制据移居地另造民族或扩大本土。',
      'zaza':'恢复扎扎语与居民标签；共用伊朗传承，不对现代民族自我认同争议作裁决。',
      'aromanian':'封闭罗马尼亚—阿罗马尼亚合称；保留原版东罗曼语与罗马尼亚传承。',
      'regional_slavic':'沿用原版波兰宽类；卡舒布来源持续可回溯，不据现代标准强制无限细分。',
      'rusyn':'沿用原版乌克兰/东斯拉夫宽类；鲁塞尼亚边界争议不写为已解决的同义关系。',
      'kanembu':'卡努里—卡涅姆布封闭合称；沿用原版萨赫勒传承。',
      'lunda_border':'与现有乔奎资产合并为明确成员的乔奎—卢瓦莱—姆本达传统；Luchazi列入封闭成员台账，共用刚果传承。',
      'kongo_border':'保留原版刚果宽类的有限游戏聚合；Yaka/Suku/Bwende并非民族同义词，不复制整个刚果帝国疆域为本土。',
      'luba_border':'原版卢巴宽类暂保留；王权/艺术传统传播不等于所有Kasai成员同族，具体语言仍保留未决标记于报告。',
      'sara_border':'伊罗古拉独立，纠正Sara Gula与Bua Gula Iro的混淆。',
      'hohokam':'保留考古文化的架空存续，不指认为霍坎或单一现代后裔。',
      'cahokia':'保留源考古文化存续，撤销已知苏语族归属假定；本土限伊利诺伊核心。',
      'colombia':'Quimbaya/Tumaco保留具名来源和有限历史核心，撤销Cariban确证假定；Yarigui保留原版加勒比宽类但记录证据限制。',
      'andes_quechua':'保留原版克丘亚大类和源语言；考古名称的年代、后续语言变化不据此认定全部有连续民族史。',
      'andes_aymara':'保留原版艾马拉大类；Chango/Kallawaya等边缘语言并未确证为同一民族，报告明确保留未决项。',
      'arctic':'Unalaska/Atka/Attu合并为乌南干；与因纽特共用环极传承、使用独立阿留申语。',
      'dorset':'保留原版环极大类作为游戏压缩；不称多塞特与现代因纽特为已证实同一民族。',
      'nakoda':'保留原版达科他宽类，纳科达成员单独记账；共用苏语及原版传承。',
      'moro_sama':'原版Moro为地区宽类可保留；Sama并不等于单一宗教，实际居民宗教不受文化合并影响。',
      'amazon_border':'沿用用户接受的原版亚马孙宽类；阿拉瓦克与Caquetio的外围边界不通过全域本土补足。',
      'melanesia_border':'暂保留原版美拉尼西亚宽类；帝汶—阿洛尔与新几内亚不同，不将其语言字段认定为谱系结论。',
      'patagonia_border':'保留原版巴塔哥尼亚宽类作游戏粒度；北部Mapudungun和Huarpe/Chana等边界仍有证据缺口。',
    }
    uncertain={'ciboney','tupi','bo','jurchen','baltic','uralic','caspian_other','italian_border','tuareg_history','luba_border','mbundu','chewa_border','mossi_border','sukuma_border','swahili_border','colombia','andes_quechua','andes_aymara','dorset','moro_sama','melanesia_border','patagonia_border'}
    for f in FINDINGS:
        if f['status'] not in ('scope_design','historical_review'):continue
        p['decisions'][f['id']]={'members':f['members'],'decision':notes.get(f['id'],
            '复核源定义后仍缺少足以确定新边界的证据；保留当前游戏聚合，不把同语言/邻近等同于同民族，也不据此扩大历史本土。'),
            'evidence_status':'historical_boundary_unresolved' if f['id'] in uncertain else 'bounded_gameplay_decision',
            'refs':[REFS[x] for x in f['sources'] if x in REFS]}
    p['labels']['language_tabari']=['Gilaki and Mazanderani','吉兰语与马赞德兰语']
    p['labels']['language_burmic']=['Burmese and Arakanese','缅语与若开语']
    p['labels']['language_shan']=['Shan and Dai','掸语与傣语']
    p['source_label_decisions']={s:'保留源标签及居民；成员不足以具名拆分，不授予整个语言区域的本土。' for s in SOURCE_BROAD}
    return p

if __name__=='__main__':
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'config/personal/m5_culture_framework.json'
    path.write_text(json.dumps(policy(),ensure_ascii=False,indent=2),encoding='utf-8')
    print(path)
