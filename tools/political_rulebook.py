"""Personal EU5 1.3 -> V3 1.13.11 policy, not an assertion of equivalence.

Rules use positive evidence; research never masquerades as an enacted policy.
Higher priority wins; all matching alternatives remain in the audit.
"""
RULE_VERSION = 'politics-0.2'

DEFAULTS = {
    'governance_principles': 'monarchy', 'distribution_of_power': 'autocracy',
    'bureaucracy': 'hereditary_bureaucrats', 'army_model': 'peasant_levies',
    'navy_model': 'merchant_navy', 'church_and_state': 'state_religion',
    'citizenship': 'national_supremacy', 'internal_security': 'no_home_affairs',
    'colonization': 'no_colonial_affairs', 'economic_system': 'traditionalism',
    'education_system': 'no_schools', 'health_system': 'no_health_system',
    'land_reform': 'tenant_farmers', 'policing': 'no_police',
    'taxation': 'land_based_taxation', 'trade_policy': 'mercantilism',
    'childrens_rights': 'child_labor_allowed', 'free_speech': 'right_of_assembly',
    'labor_rights': 'no_workers_rights', 'labour_associations': 'right_to_associate',
    'migration': 'migration_controls', 'rights_of_women': 'no_womens_rights',
    'slavery': 'slavery_banned', 'welfare': 'no_social_security',
    'caste_hegemony': None, 'edo_social_system': None,
}


def rulebook():
    rules = []
    def add(group, law, rank, reason, *, any=(), all=(), none=()):
        rules.append(dict(id=f'{group}.{law}.{len(rules)+1:03}', group='lawgroup_'+group,
                          law='law_'+law, priority=rank, reason=reason,
                          any=list(any), all=list(all), none=list(none)))
    def policies(group, law, names, reason, rank=90, **kw):
        add(group, law, rank, reason, any=['policy:'+n for n in names.split()], **kw)
    def reforms(group, law, names, reason, rank=80, **kw):
        add(group, law, rank, reason, any=['reform:'+n for n in names.split()], **kw)
    def facts(group, law, names, reason, rank=60, **kw):
        add(group, law, rank, reason, any=['fact:'+n for n in names.split()], **kw)

    facts('governance_principles','monarchy','monarchy steppe_horde','继承源君主/汗国政体',120)
    facts('governance_principles','presidential_republic','republic','保留共和国；选举范围另判',120)
    facts('governance_principles','theocracy','theocracy','继承实际神权政体',120)
    facts('governance_principles','chiefdom','tribe','部落政治；不凭地区更换政体',120)
    facts('governance_principles','colonial_administration','colonial_subject','经源附庸类型确认的殖民政府',130)
    # Parliamentary form requires both assembly sovereignty and no presidential concentration.
    add('governance_principles','parliamentary_republic',125,'共和制且国民议会与权力下放并存',
        all=['fact:republic','policy:dop_law_assemblee_nationale','policy:devolution_of_powers_policy'],
        none=['policy:absolute_presidential_power_policy','policy:dynastic_rule_policy'])

    facts('distribution_of_power','oligarchy','republic','缺少普遍选举证据的共和国',40)
    facts('distribution_of_power','elder_council','tribe','部落会议的保守近似',45)
    policies('distribution_of_power','autocracy','absolute_presidential_power_policy dynastic_rule_policy authoritarianism_policy absolute_rule_policy','明确的个人/世袭集权优先于共和国名称',110)
    reforms('distribution_of_power','bakufu','shogunate','幕府实际制度；不按日本标签猜测',115)
    policies('distribution_of_power','oligarchy','military_rulership_policy board_of_admirals_policy','军官或海军委员会统治，不等同全民军政府选举',95)
    policies('distribution_of_power','landed_voting','landholders dop_law_english_parliament dop_law_estates_general','财产/等级代表制的保守选举近似',95)
    policies('distribution_of_power','census_voting','citizenry','有公民选任但公民边界不明，不自动普选',95)
    reforms('distribution_of_power','landed_voting','peasant_republic_reform','有土地农民参与；不是自动社会主义或普选',96)
    policies('distribution_of_power','wealth_voting','dop_favor_the_burghers','商人共和国且确有商人政治优势',65,all=['reform:merchant_republic'])

    policies('bureaucracy','hereditary_bureaucrats','dynastic_administration_policy','中央集权不取消家族官僚制',105)
    policies('bureaucracy','appointed_bureaucrats','meritocratic_recruitment_policy sinicized_cabinet_policy continue_the_imperial_examination nobles_of_the_robe_policy','科举/任命制度',95)
    policies('bureaucracy','appointed_bureaucrats','centralized_bureaucracy_policy','集权官僚可推定任命制，但服从明确家族任用',65)
    # Devolution is not proof of elected civil servants.
    policies('army_model','peasant_levies','peasant_levies noble_levies noble_levies_policy expanded_levies_policy burghers_levies_policy','实际征召体系优先于已研究军事革新',100)
    policies('army_model','professional_army','early_standing_army_policy elite_training_policy allotment_system_policy','已实施常备军/常备编练',100)
    policies('army_model','mass_conscription','levee_en_masse_policy','实际大规模征兵；技术仍另行核验',105)
    reforms('army_model','national_militia','mass_levy_system','民兵动员组织的近似，优先级低于征募法',75)
    policies('navy_model','merchant_navy','merchant_navy','实际商船海军学说',95)
    policies('navy_model','professional_navy','fleet_in_being navy_audits','常设舰队或制度化海军审计',85)
    policies('navy_model','diplomatic_navy','protect_trade_routes','贸易护航的近似，低于明确商船学说',65)

    facts('church_and_state','state_religion','theocracy','神权政体必须保留国教',130)
    policies('church_and_state','state_religion','state_inquisitors papal_control de_heretico_comburendo doktrinalnaya_ohrana','强制宗教司法/迫害阻止完全分离',110)
    reforms('church_and_state','state_religion','religious_laws_enforced anti_heresy_act','实际宗教强制优先于一般宽容宣言',105)
    policies('church_and_state','freedom_of_conscience','separate_clergy_from_state_policy complete_religious_autonomy_policy','教俗分离/宗教自治；尚不足以证明普遍平等',90)
    policies('church_and_state','freedom_of_conscience','secular_education','国家已实行世俗大众教育；缺少明确国教强制时采用兼容教育的有限宗教自由',55)
    reforms('church_and_state','freedom_of_conscience','religious_tolerance spanish_tolerance','实际宽容改革',80)
    add('church_and_state','total_separation',100,'教俗分离、所有奴隶信仰受容忍、宗教自治和世俗教育共同支持',
        all=['policy:separate_clergy_from_state_policy','policy:allow_slave_religion','policy:complete_religious_autonomy_policy','policy:secular_education'],
        none=['policy:force_slave_conversion','policy:local_courts','privilege:clergy_enforced_unity'])
    facts('citizenship','subjecthood','monarchy theocracy tribe steppe_horde colonial_subject','前民族国家政治归属；共和国不能用臣民制',65)
    policies('citizenship','cultural_exclusion','allow_foreign_rituals','文化包容的近似，须已有实际接纳文化；不等于多元文化主义',70,all=['fact:accepted_foreign_cultures'])
    policies('citizenship','national_supremacy','blood_tax_of_foreigners','对外来族群实行明确差别待遇',95)
    reforms('citizenship','cultural_exclusion','cultural_recognition_act','明确承认其他文化的制度',85,all=['fact:accepted_foreign_cultures'])

    policies('internal_security','secret_police','secret_police_policy jinyiwei_policy oprichnik_policy','实际秘密警察/锦衣卫/特辖组织',100)
    policies('internal_security','national_guard','home_security_policy','内卫制度的近似；间谍办公室不算',75)
    facts('colonization','frontier_colonization','colonial_subject','殖民政府的边疆扩张近似；不是宗主国海外殖民部',80)
    policies('colonization','colonial_resettlement','settled_colonies','移民殖民政策且确有殖民属国',95,all=['fact:colonial_overlord'])
    policies('colonization','colonial_exploitation','trade_colonies','贸易殖民政策且确有殖民属国',95,all=['fact:colonial_overlord'])
    # Merely having the ubiquitous colonial law is insufficient for all 376 countries.
    reforms('economic_system','interventionism','royal_factories_reform production_quota_bureaus','实际国家生产干预；不等同计划经济',85)
    reforms('economic_system','laissez_faire','capitalistic_cities','资本城市、自由贸易与银行组织共同支持市场私营近似',80,
            all=['policy:free_trade_policy','reform:bank_ledgers_system'],none=['policy:strong_guilds_policy'])
    facts('economic_system','agrarianism','agrarian_reform','农政改革与农业社会共同证据；农业普遍存在不算',65)
    policies('education_system','no_schools','uneducated_masses_education oral_tradition_education','无普遍正规学校；不否定口传知识',105)
    policies('education_system','religious_schools','basic_religious_education theocratic_education scottish_presbyterian_education personal_religious_education','已实行大众宗教教育',95)
    policies('education_system','public_schools','secular_education','已实行世俗大众教育，公共制度近似',95)
    policies('education_system','no_schools','apprenticeships_education','行会学徒培养不等于全国学校机构；保留为职业教育证据',70)
    # Universities, medical research or a prosperous elite do not prove universal services.
    facts('health_system','charitable_health_system','charitable_health_network','须有经审核的真实医疗服务网络',90)
    reforms('welfare','poor_laws','public_welfare_act','已实施公共救济改革；不直接变成养老金',85)
    facts('welfare','chiefs_distribute_aid','tribal_redistribution','须确认部落再分配，部落政体本身不够',85)

    reforms('land_reform','serfdom','universal_serfdom','明确普遍农奴制',110)
    add('land_reform','serfdom',100,'贵族农奴特权并有农奴方向社会结构',
        all=['privilege:noble_serfdom_rights','fact:serf_society'],none=['privilege:peasants_free_peasantry'])
    add('land_reform','peasant_proprietorship',100,'确认自耕农土地权',all=['privilege:land_owning_farmers'])
    reforms('land_reform','peasant_proprietorship','peasant_republic_reform','农民共和国的土地制度近似',85)
    add('land_reform','tenant_farmers',95,'自由农民权利：取消人身束缚，不凭此假定人人有地',all=['privilege:peasants_free_peasantry'])
    facts('land_reform','manorialism','serf_society','强农奴倾向但缺乏完整农奴立法的保守近似',55)
    policies('policing','dedicated_police','centralized_bureaucracy_policy','中央官僚与成文法近似专职治安；属于中等强度推断',65,
             all=['fact:codified_administration'],none=['fact:tribe'])
    facts('policing','local_police','codified_administration','地方成文法司法可近似地方警察',55)
    policies('taxation','consumption_based_taxation','trade_tax','明确贸易税制',95)
    policies('taxation','proportional_taxation','income_tax','明确所得税，但税率结构未给出，比例税为近似',90)
    policies('taxation','land_based_taxation','traditional_tax rice_based_tax','传统地租/实物税',90)
    policies('trade_policy','free_trade','free_trade_policy','实际自由贸易政策；不自动赋予自由放任',100)
    facts('trade_policy','protectionism','mercantilist_commercial_state','成熟商业组织与强重商倾向共同支持',60)
    policies('free_speech','censorship','strict_censorship limited_censorship censored_press state_press_only de_heretico_comburendo doktrinalnaya_ohrana','任何实际审查约束优先于另一领域的自由出版',110)
    reforms('free_speech','censorship','licensing_of_the_press_act','已实行出版许可',105)
    add('free_speech','protected_speech',95,'无宗教审查与自由出版同时成立；V3人权技术为待核前置',all=['policy:no_censorship','policy:free_press'])
    policies('free_speech','right_of_assembly','no_censorship free_press','单一领域宽松不足以证明完整言论保障',70)
    reforms('labour_associations','combination_acts','the_combination_act','实际禁止结社法案',100)
    policies('labour_associations','guild_system','strong_guilds_policy','明确强行会制度',95)
    policies('migration','closed_borders','closed_borders_law','实际禁止跨境迁移',100)
    policies('migration','no_migration_controls','open_borders_law','源开放边境且为美洲独立移民主流文化国家，保留 V3 开放边境',96,
             all=['fact:american_independent_immigrant'],none=['policy:closed_borders_law'])
    policies('migration','migration_controls','open_borders_law','源开放边境在 V3 转为控制边境；美洲独立移民国家除外',95,
             none=['fact:american_independent_immigrant'])
    policies('rights_of_women','women_own_property','matrilineal_customary_law_policy','母系财产/习惯法近似，置信度低；不推导妇女普选',65)
    reforms('rights_of_women','women_own_property','haudenosaunee_clan_mothers','氏族母亲制度的有限权利近似，非西式普选',70)
    policies('slavery','slavery_banned','slavery_outlawed','明确废奴',120)
    policies('slavery','slave_trade','slavery_allowed','定义明确允许奴隶进出口',110)
    facts('slavery','legacy_slavery','slave_population','确有奴隶但贸易许可不明；保留既有奴隶，禁止凭空扩张',80)
    policies('slavery','legacy_slavery','force_slave_conversion allow_slave_religion','奴隶信仰管理说明奴役制度仍有法律对象；不证明贸易许可',60)
    return rules


# These are capabilities, NOT extra enactment rules or a complete technology conversion.
TECH_BRIDGES = {
    'rationalism': ['institution:renaissance','advance:humanism'],
    'empiricism': ['institution:scientific_revolution'],
    'tech_bureaucracy': ['advance:codified_laws','advance:educated_bureaucrats'],
    'centralization': ['policy:centralized_bureaucracy_policy'],
    'central_archives': ['advance:modern_bureaucracy'],
    'military_drill': ['institution:professional_armies'],
    'international_trade': ['institution:global_trade'],
    'stock_exchange': ['advance:central_bank_advance'],
    'colonization': ['advance:colonial_charters','advance:colonial_policy_advance'],
    'medical_degrees': ['advance:medical_school_advance'],
    'quinine': ['advance:jesuits_bark'],
    'currency_standards': ['advance:banking_advance'],
}
