"""Explicit audit findings, NOT converter mapping rules or historical certification.

Evidence establishes the stated distinction only, not a complete 1780 boundary.
Modern language catalogs do not by themselves dictate game culture granularity.
"""

SOURCES = {
    'oirat': ('剑桥：卡尔梅克文化记录项目', 'https://www.repository.cam.ac.uk/items/76f6c930-6715-4533-b937-fd73c0fcee98', '卡尔梅克的瓦剌来源及17世纪迁移；不能据此将所有瓦剌居民写成伏尔加支系。'),
    'romansh': ('瑞士外交部：罗曼什语', 'https://www.eda.admin.ch/en/emna-rumantscha-en', '罗曼什为拉丁／罗曼语言，不能作为阿勒曼尼德语身份的同义词。'),
    'frisian': ('弗里斯兰科学院：语言研究', 'https://www.fryske-akademy.nl/en/research/language-and-multilingualism/', '研究明确区分弗里斯兰语与荷兰语；共同地区不构成身份同义。'),
    'indonesia': ('印尼语言机构：语言目录', 'https://petabahasa.kemendikdasmen.go.id/databahasa.php', '萨萨克、巴厘、马都拉、爪哇分别列项；目录不是1780民族边界证明。'),
    'philippines': ('菲律宾教育部：母语目录', 'https://www.deped.gov.ph/2016/10/24/mother-tongue-based-learning-makes-lessonsmore-interactive-and-easier-for-students/', '分别列出Kapampangan、Pangasinan、Iloko、Ybanag、Tagalog。'),
    'limbu': ('尼泊尔原住民族基金会：林布', 'https://nfdin.gov.np/pages/limbu/', '林布／Yakthung的基拉特身份、自有语言与历史核心。'),
    'china_languages': ('教育部：中国语言文字概况', 'https://www.moe.gov.cn/jyb_sjzl/wenzi/202108/t20210827_554992.html', '分别列举彝、傈僳、哈尼、拉祜、基诺、阿昌及壮、仫佬、毛南等语言。现代分类仅用于反证同义映射。'),
    'mulam': ('国家民委：仫佬族概况', 'https://www.neac.gov.cn/seac/ztzl/mlz/gk.shtml', '仫佬语言与毛南、侗语接近，兼通壮语不等于壮族身份。'),
    'maonan': ('国家民委：毛南族历史', 'https://www.neac.gov.cn/seac/ztzl/mnz/lsyg.shtml', '明清形成过程及其与其他群体的关系。'),
    'gurage': ('Glottolog：Sebat Bet Gurage', 'https://glottolog.org/resource/languoid/id/seba1251', '古拉盖语言条目；古拉盖本身也有内部多样性，不等于阿姆哈拉。'),
    'tigre': ('SOAS：Tigre语法研究', 'https://eprints.soas.ac.uk/34084/1/11015900.pdf', 'Tigre独立语法研究；当前V3 tigray资产明确使用Tigrinya语言。'),
    'gilaki': ('亚利桑那大学：Gilaki', 'https://iranian-languages.arizona.edu/node/8', '吉兰语与马赞德兰语接近／连续体，不足以将二者当同义词。检索摘要可读，正文跳转受限。'),
    'norn': ('高地与群岛大学：Between Scotland and Norway', 'https://pure.uhi.ac.uk/files/2094937/Between_Scotland_and_Norway_FINAL_2017.pdf', 'Norn与Scots的历史转换；现实同化不等于存档中仍存续者已同化。'),
    'yuchi': ('尤奇语言项目', 'https://www.yuchilanguage.org/', '该族语言保护项目明确说明尤奇为孤立语言；不能据语言亲缘假说确认苏语族归属。'),
    'hohokam': ('NPS：索诺拉沙漠先民', 'https://www.nps.gov/cagr/learn/historyculture/the-ancestral-sonoran-desert-people.htm', 'Hohokam为考古文化标签，不是已知单一民族／语族名称。'),
    'lucayan': ('特克斯和凯科斯博物馆：Lucayans', 'https://www.tcmuseum.org/culture-history/lucayans/', '卢卡约是加勒比泰诺的一支；检索摘要可读，正文抓取超时。'),
    'lucayan_research': ('PNAS：加勒比泰诺古基因组研究', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC5877975/', '巴哈马卢卡约泰诺个体的考古语境；不使用基因推定游戏民族。'),
    'numic': ('NPS：大盆地历史族群', 'https://home.nps.gov/grba/learn/historyculture/historic-tribes-of-the-great-basin.htm', '区分肖肖尼、戈舒特、尤特、派尤特；Numic是较宽的语言类别。'),
    'tupi': ('巴西原住民资料项目：蒙杜鲁库', 'https://pib.socioambiental.org/en/Povo%3AMunduruku', '蒙杜鲁库属于图皮语系独立分支；图皮系不等于图皮南巴族。'),
    'lozi': ('剑桥：Makololo与Ngoni研究', 'https://www.cambridge.org/core/books/abs/five-hundred-years-rediscovered/mfecane-mutation-in-central-africa-a-comparison-of-the-makololo-and-the-ngoni-in-zambia-1830s1898/4F4969CAABB6A8E4F2CBB60A082ED7B3', '洛齐与19世纪科洛洛进程；不能自动将后来的语言转变提前写入1780。'),
}

LABELS = {
    'framework_decided': '已作有限框架决定',
    'corrected_identity': '已完成明确身份修复',
    'identity_mismatch': '明确应改的身份错配',
    'scope_design': '名称／范围需调整',
    'historical_review': '历史或成员边界待核',
    'source_label_review': '源标签本身待核',
    'approved_composite': '既有封闭合称，保留',
    'source_preserved': '源身份保留',
    'vanilla_broad': '沿用原版大类',
    'no_flag': '本轮未发现此类错配',
}

FINDINGS = []

def add(key, status, target, members, reason, proposal, refs=''):
    FINDINGS.append(dict(id=key, status=status, target=target, members=members.split(),
                         reason=reason, proposal=proposal, sources=refs.split()))

add('oirat', 'identity_mismatch', 'kalmyk', 'oirat_culture',
    '瓦剌整体被写成卡尔梅克；当前没有按真实迁移支系作区分。',
    '恢复瓦剌显示身份，继续共用蒙古传承；政治主流与居民映射一起修正。', 'oirat')
add('romansh', 'identity_mismatch', 'alemannic', 'romansh',
    '罗曼什被归入阿勒曼尼，连语言也成为德语。', '恢复罗曼什身份；不能因瑞士地域共存而德语化。', 'romansh')
add('frisian', 'identity_mismatch', 'dutch', 'frisian',
    '弗里斯兰被当作荷兰身份同义词。', '保留弗里斯兰身份，共用现有广义日耳曼传承即可。', 'frisian')
add('sasak', 'identity_mismatch', 'balinese', 'sasak_culture',
    '萨萨克并非巴厘身份的地方别名。', '恢复萨萨克或设计明确有边界的合称，不直接改称巴厘。', 'indonesia')
add('madurese', 'identity_mismatch', 'javan', 'madurese_culture',
    '马都拉被改为爪哇身份。', '恢复马都拉；传承沿用现有宽组。', 'indonesia')
add('luzon_north', 'identity_mismatch', 'ilocano', 'pangasinan_culture ibanag_culture',
    '邦阿西楠、伊巴纳格并非伊洛卡诺的同义名。', '优先已有宽泛菲律宾类别；若需区分政治身份再作有限拆分。', 'philippines')
add('kapampangan', 'identity_mismatch', 'tagalog', 'kapampangan_culture',
    '卡潘潘甘被改为他加禄。', '同菲律宾其他明确错配一起设计，不逐村新增文化。', 'philippines')
add('limbu', 'identity_mismatch', 'tibetan', 'limbu_culture',
    '林布的基拉特身份被藏族类别吞并。', '恢复林布身份；可与有依据的基拉特文化作封闭合称。', 'limbu')
add('yi_siblings', 'identity_mismatch', 'yi', 'lisu_culture hani_culture lahu_culture jino_culture',
    '亲缘语言分支被直接当作彝族身份；共用传承与变更民族不是一回事。',
    '继续共用宽泛传承，居民名称恢复或采用成员封闭合称；现代分类不自动决定1780边界。', 'china_languages')
add('kam_sui', 'identity_mismatch', 'zhuang', 'mulam_culture maonan_culture',
    '仫佬、毛南被改称壮族；同属宽泛语言传统不足以构成民族同义。',
    '允许共用泰传承；居民名称可设计仫佬—毛南的封闭合称。', 'mulam maonan')
add('gurage', 'identity_mismatch', 'amhara', 'gurage',
    '古拉盖整体被映射成阿姆哈拉。', '保留古拉盖一级身份，共用阿比西尼亚传承。', 'gurage')
add('tigre', 'identity_mismatch', 'tigray', 'tigre',
    '中文近似掩盖了Tigre与Tigrinya差异；目标使用language_tigrinya。',
    '区分Tigre与Tigrinya标签；共用阿比西尼亚传承。', 'tigre')
add('gilaki', 'scope_design', 'mazanderani', 'gilak_culture',
    '吉兰与马赞德兰的接近关系被表达成单一马赞德兰身份。',
    '可采用吉兰—马赞德兰封闭合称，或保留吉兰；不新增传承。', 'gilaki')
add('norn', 'identity_mismatch', 'scottish', 'norn_culture',
    '源文件仍指定北日耳曼的Norn，目标却变成Scots身份。',
    '按存档仍存续身份处理，不能将现实语言替代直接提前套入。', 'norn')
add('yuchi', 'identity_mismatch', 'siouan', 'tsoyaha_culture',
    'Tsoyaha／Yuchi被归入苏语文化，不能把亲缘假说当作确证。',
    '恢复尤奇身份并共用适当宽传承；语言独立问题另列。', 'yuchi')
add('hohokam', 'historical_review', 'hokan', 'hohokam_culture',
    '考古文化Hohokam不等于Hokan语族；当前归类缺少证据。',
    '撤销已确认霍坎的假定；保留源标签或经后裔证据设计，勿直接断言唯一后裔。', 'hohokam')
add('lucayan', 'identity_mismatch', 'amazonian', 'lucayo',
    '加勒比卢卡约被改成亚马孙居民；宽类别仍须有地域边界。',
    '归入已有泰诺身份资产，先复核该资产范围和本土。', 'lucayan lucayan_research')
add('ciboney', 'historical_review', 'amazonian', 'ciboney',
    '加勒比源标签被并入亚马孙；Ciboney历史用法本身也有歧义。',
    '与泰诺／古巴前泰诺证据一起核定，不仅凭名称自动并入泰诺。')
add('numic', 'scope_design', 'paiute',
    'nuwuvi_culture numu_culture nuuchi_culture penkwitikka_culture kusiutta_culture kuccuntikka_culture bannock_culture tukudeka_culture agaideka_culture haivodika_culture watatikka_culture wiyimpihtikka_culture tetadeka_culture nuwuvu_culture timbisha_culture yapahruka_culture monachi_culture kuhtsutuuka_culture',
    '派尤特的具体名称承载了包括肖肖尼、尤特在内的整个Numic集合。',
    '优先保留数量，以明确的Numic／大盆地封闭类别命名，或有限拆成2—3类。', 'numic')
add('tupi', 'scope_design', 'tupinamba',
    'ava_culture tupiniquim_culture wuyjuyu_culture catagua_culture satere_mawe_culture kagwahiva_culture kaapor_culture kawaiwete_culture tupinamba_culture kaete_culture guarasugwe_culture yjxa_culture makurap_culture awa_canoeiro_culture kukakma_culture awa_brazil_culture tapajo_culture arua_culture paiter_culture kambeba_culture',
    '图皮南巴一族的名称被用于图皮系更大的集合；文献仅直接证实蒙杜鲁库与图皮南巴不可视为同义，其余成员继续边界核对。',
    '可保留一个明确称为图皮的大类；先逐项排除误归成员。', 'tupi')
add('tupi_uncertain', 'historical_review', 'tupinamba', 'manaos_culture pankararu_culture yuri_culture',
    '这三条源游戏分类不能单凭tupi_group可靠确定；历史语言身份需独立补证。',
    '先剔出自动审核通过名单；不要只改大类名称就宣布修正完成。')
add('rajput', 'scope_design', 'rajput', 'dhundhari harauti mewari marwari shekhawati mewati bagri',
    '地域文化全部输出拉杰普特，易被误读为所有居民属于特定武士／宗族身份。原版传承实际已为heritage_rajasthani。',
    '优先研究将显示范围解释为拉贾斯坦；无需恢复七个小文化。')
add('bedouin', 'scope_design', 'bedouin', 'najdi_culture hijazi_culture omani_culture kaliji_culture',
    '半岛地域居民一律显示贝都因，无法区分游牧身份与定居地区居民。',
    '优先宽泛半岛阿拉伯类别或有限区域合称；保留原宗教。')
add('lozi', 'historical_review', 'sotho', 'lozi_culture',
    '现代洛齐的索托语言联系涉及19世纪科洛洛历史，不能直接推回1780存档。',
    '按源年代复核卢伊／洛齐身份，暂不以现代索托联系判为同义。', 'lozi')

# Each group below is a flagged hypothesis, not a historical conclusion.
add('minyak', 'historical_review', 'yi', 'mi_niah_culture', '源游戏指定qiangic_language，却因大组并入彝；Minyak／弥药标签语境须核对。', '核定源身份后保留或纳入有依据的羌语集合。')
add('achang', 'historical_review', 'kachin', 'ngacang_culture', '阿昌被并入克钦，克钦究竟用景颇狭义还是地区联盟广义未说明。', '明确克钦范围；不得将宽泛联盟当景颇单一民族。', 'china_languages')
add('kadu', 'historical_review', 'burmese', 'kado_culture', '源语言kachinic被变为burmic；不能只以缅甸地域认定缅族。', '单独核对Kadu身份和目标宽组。')
add('rakhine', 'scope_design', 'burmese', 'rakhine_culture', '若目标是缅甸地域文化圈可以宽并；若指缅族则若开身份被抹平。', '明确名称范围，优先有边界的缅甸—若开设计。')
add('kuy', 'historical_review', 'khmer', 'kuy_culture', '共享南亚语背景不足以证明Kuy就是Khmer。', '核对高棉宽类别是否有明确吸收范围。')
add('bru', 'historical_review', 'khmu', 'bru_culture', 'Bru与Khmu是否只是同一宽组下不同分支尚未证明，当前直接替换身份。', '优先同传承、不同身份或封闭合称。')
add('muong', 'scope_design', 'vietnamese', 'muong_culture', '芒与京的亲缘不自动等于同一民族；Vietnamese标签地域／民族两义混用。', '可以设计京—芒宽合称，或恢复芒，不再新增传承。')
add('bo', 'historical_review', 'zhuang', 'bo_culture', '僰的古代身份不能直接从源壮侗分组推定为壮。', '先核源地域、语言与年代，不自动套现代民族。')
add('tai_shan', 'scope_design', 'shan', 'dai_culture tai_nua_culture tai_lu_culture', '傣及不同Tai支系被统一显示掸；泰传承宽于掸族身份。', '共享泰传承；若并类，名称明确为傣—掸且核准成员。')
add('thai_regions', 'scope_design', 'thai', 'khon_muang_culture dambro_culture', '原版泰可作宽类别，但北部／半岛地域文化的并入不是别名等价。', '可维持原版宽类，报告明示区域抽象。')
add('tibetan_border', 'historical_review', 'tibetan', 'monpa_culture tebbu_culture', '边界群体的藏族／藏文化圈含义未清楚区分。', '核对源标签含义，不因源tibetan_group自动确认。')
add('marathi_border', 'scope_design', 'marathi', 'konkani khandeshi', '孔卡尼、坎德什被映射到马拉地；地域联系不足以证明同一身份。', '复核原版粒度，可用明确封闭合称，避免逐方言拆分。')
add('kohistani', 'historical_review', 'panjabi', 'kohistani', '源游戏使用kashmiri_language，目标旁遮普的身份依据缺失。', '核定科希斯坦来源范围后设计达尔德／山地明确类别。')
add('khorezm', 'historical_review', 'uzbek', 'khorezmian_culture', '源文件指定Karluk而非古伊朗语；不能将古代花剌子模知识直接套入，也不能默认等于乌兹别克。', '按存档所用突厥花剌子模范围核对，避免错误恢复古代语言。')
add('bulghar', 'historical_review', 'chuvash', 'bolghar_culture', '历史祖先群体与后继楚瓦什被当作完全同义。', '尊重源存档仍存续的保加尔身份；可以共享宽传承。')
add('jurchen', 'scope_design', 'manchu', 'jurchen_culture haixi_culture hurga_culture', '女真到满洲涉及历史整合；反事实存档不能默认完整复演，但原版宽称可解释。', '优先女真—满洲宽称；不恢复每支小文化。')
add('sibe', 'historical_review', 'manchu', 'sibe_culture', '锡伯被并入满；语言联系不足以自动认定身份相同。', '与女真—满洲宽称方案一起核定边界。', 'china_languages')
add('baltic', 'historical_review', 'lithuanian', 'curonian pruthenian', '库尔斯、古普鲁士并非立陶宛的直接同义，源西波罗的语言信息丢失。', '可共用波罗的传承，有限恢复身份或明确宽称。')
add('uralic', 'historical_review', 'ugrian', 'merya_culture bjarmian', '梅里亚及比亚尔米亚与乌戈尔的分类不应由地理近邻推定。', '核对源标签所指，保留乌戈尔仅限已证成员。')
add('caucasus_west', 'historical_review', 'circassian', 'abkhazian_culture abazin_culture', '阿布哈兹、阿巴津被改成切尔克斯及Adyghe语言。', '可用阿布哈兹—阿巴津合称并共享北高加索传承。')
add('nakh', 'scope_design', 'chechen', 'nakh_culture', 'Nakh范围可能大于Chechen，需说明源标签是否包含印古什等。', '若为广义Nakh，显示名用纳赫；不将传承变细。')
add('german_diaspora', 'historical_review', 'north_german', 'german_transylvanian german_carpathian', '萨克森／北德的名称容易误导；离散群体来源不等于当代北德地理。', '按源游戏语言与迁移史核对北／南德，不新增无必要细分。')
add('caspian_other', 'historical_review', 'persian', 'semnani_culture dehwar_culture', '波斯宽称是否覆盖该源身份缺少明确约定；并非自动同义。', '复核语言与居民身份后决定宽称或恢复。')
add('zaza', 'historical_review', 'kurdish', 'zaza_culture', '自我认同、语言和库尔德政治文化圈不完全重合，存在争议。', '不强行替用户断定；列明宽并含义与保留身份选项。')
add('sardinian', 'scope_design', 'south_italian', 'sardinian', '南意大利是原版地区抽象，但不能解释成撒丁与半岛民族完全相同。', '保留地区粒度可行；语言代表性另列限制。')
add('italian_border', 'scope_design', 'north_italian', 'ladin friulian dalmatian', '拉丁、弗留利、达尔马提亚的区域／语言边界被北意类别覆盖。', '允许原版地区宽并，但达尔马提亚地域与语言范围须明确。')
add('aromanian', 'scope_design', 'romanian', 'aromanian', '阿罗马尼亚被当作罗马尼亚同义，跨巴尔干范围未说明。', '明确东罗曼宽称，避免仅由现代国家名定义身份。')
add('regional_slavic', 'scope_design', 'polish', 'kashubian', '卡舒比并入波兰是粒度决定，不是没有差异的同义。', '可保留原版宽类，明确语言与地域差异。')
add('rusyn', 'scope_design', 'ukrainian', 'rusyn_culture', '卢森与乌克兰身份关系存在地区／时期差异。', '保留宽类属于设计选择，不标为史实已确认。')
add('anglo_irish', 'historical_review', 'irish', 'anglo_irish', '盎格鲁—爱尔兰可能是移民／混合精英身份，不能仅以居地改成爱尔兰。', '查源定义，按既有移民政策或源身份处理。')
add('kanembu', 'scope_design', 'kanuri', 'kanembu_culture', '卡内姆布与卡努里的历史关系不等于名称完全等价。', '可采用卡内姆—博尔努范围的明确合称。')
add('tuareg_history', 'historical_review', 'tuareg', 'messufa_culture lamtuna_culture', '中世纪桑哈贾群体到现代图阿雷格的对应不能预设。', '与原版柏柏尔大类比较，按年代和源身份处理。')
add('kongo_border', 'historical_review', 'bakongo', 'yaka suku bwende', '刚果文化圈不自动等于巴刚果；边缘成员历史归属未逐项支持。', '核定封闭成员，其他已知刚果核心保留宽并。')
add('luba_border', 'historical_review', 'luba', 'bena_lwalwa bindji lwalwa mbala songye hemba kete pende kasayi kunda', '卢巴政治文化圈、语群与居民民族三个范围混用。', '优先2—3个有名称的区域合称，避免逐部落新增。')
add('lunda_border', 'historical_review', 'lunda', 'mbunda luvale luchazi_culture', '隆达政治圈中的不同居民身份被直接改为隆达。', '核对是否有依据用封闭西南班图合称。')
add('mbundu', 'historical_review', 'ovimbundu', 'ambundu haneka_humbe', '近似名称及地理分组不足以证明Ambundu、Ovimbundu、Haneka-Humbe同一。', '优先区分明确的姆本杜分支，共用西南班图传承。')
add('chewa_border', 'historical_review', 'chewa', 'tumbuka_culture nsenga', '图姆布卡、恩森加与切瓦的关系被表示为直接民族替换。', '核准马拉维湖区域合称边界；不以共同班图传承代替身份。')
add('mossi_border', 'historical_review', 'mossi', 'gurma gurunsi mamprusi', 'Gur范围被缩写成莫西；语言群与单个居民身份需分开。', '采用少量明确合称或恢复关键群体，保持大传承。')
add('sukuma_border', 'historical_review', 'sukuma', 'rukwa_culture bena_culture', '当前苏库马目标实际来自Rukwa与Bena，需核实源标签而非就近指定。', '优先复用合适的东非宽类别，不能只看相邻区域。')
add('swahili_border', 'historical_review', 'swahili', 'mbugu_culture ruvu_culture seuta_culture matuumbi_culture', '沿海／内陆东非居民被赋予斯瓦希里身份，不能仅凭贸易或邻近。', '按斯瓦希里文化圈边界逐条复核。')
add('sara_border', 'historical_review', 'sara', 'gula_iro_culture', 'Gula Iro在Sara宽组中的依据未清楚说明。', '查明族群／语言关系后决定是否保留集合。')
add('cahokia', 'historical_review', 'siouan', 'cahokia_culture', '考古／聚落文化不自动对应某一已知语言家族。', '保留不确定性，不将苏语分类伪称为历史已审。')
add('colombia', 'historical_review', 'cariban', 'quimbaya_culture yarigui_culture tumaco_culture', '哥伦比亚考古或历史群体的语言归属未获逐条支持；源cariban组不是证据结论。', '独立核定，必要时采用已有明确地域类别。')
add('andes_quechua', 'historical_review', 'quechua', 'wari_culture chincha_culture ychsma_culture huarco_culture chancay_culture', '安第斯历史政体／考古文化不能自动等价于克丘亚民族或语言；统治和语言传播另需证据。', '共用安第斯传承；身份层只作有证据的有限合并。')
add('andes_aymara', 'historical_review', 'aimara', 'chango_culture chuwi_culture churajon_culture kallawaya_culture yaro_culture yawyu_culture mollo_culture', '海岸群体、混合语言传统与考古标签不能仅凭源aymara组等同艾马拉。', '复核具体源含义和1780存续身份，维持少数大组。')
add('arctic', 'scope_design', 'inuit', 'unalaska_culture atka_culture attu_culture', '阿留申被归入因纽特，环北极传承比因纽特民族范围宽。', '若保留原版大类需明确环北极命名；否则有限区分阿留申。')
add('dorset', 'historical_review', 'inuit', 'dorset_culture', '多塞特考古文化与因纽特身份的等同不能预设。', '保留源存档存续信息并专门核定，勿自动补历史灭绝／替代。')
add('nakoda', 'scope_design', 'dakota', 'nakoda_culture', 'Nakoda与Dakota的原版宽并需明确，不应当作简单拼写变体。', '保持苏语大传承，可采用明确包含范围的名称。')
add('moro_sama', 'historical_review', 'moro', 'sama_culture', '摩洛包含宗教—历史政治含义；并非所有Sama身份都自然对应。', '查明源群体与原宗教分布后再决定，不改居民宗教迎合名称。')
add('amazon_border', 'historical_review', 'amazonian', 'arawak_culture caquetio_culture', '宽泛亚马孙是否覆盖该来源在加勒比沿岸的全部身份，尚需地理核对。', '保留原版亚马孙主体，仅处理超出范围的成员。')
add('melanesia_border', 'scope_design', 'melanesian', 'alor_culture makasae_culture', '东印尼／帝汶边缘纳入美拉尼西亚是游戏地域抽象，并非语言同源。', '保留大类可行，明确地理边界，不能据此统一语言史。')
add('patagonia_border', 'scope_design', 'patagonian', 'pikumche_culture purun_awqa_culture warpe_culture chana_culture kamiare_culture', '原版巴塔哥尼亚类别向中智利、库约等扩展，名称地域范围需解释。', '保留大类的前提是明确南锥体游戏抽象，不恢复每小文化。')

BROAD = set('aborigine algonquian amazonian athabaskan caddoan dayak equatorial_bantu fluvian_bantu lacustrine_bantu kavango_bantu khoisan iroquoian salish mayan muskogean nahua melanesian micronesian polynesian patagonian moluccan sumatran bornean north_caucasian siberian nilotic mande malagasy lumad visayan nuba berber kru'.split())
COMPOSITES = set('eu5_resident_sherbro eu5_resident_mayo_culture eu5_resident_bodo_culture eu5_resident_dompu_culture eu5_resident_natchez_culture eu5_resident_mayangna_culture eu5_resident_north_valley_yokut_culture eu5_resident_sahaptin_culture eu5_resident_wintuan_culture eu5_resident_maiduan_culture'.split())
SOURCE_BROAD = set('bantoid benue otomanguean_culture gonga_culture omo_culture south_cushitic_culture barbakoan_culture'.split())
