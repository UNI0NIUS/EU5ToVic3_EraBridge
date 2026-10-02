"""Evaluate political rules without changing a game mod or reviewed source data."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import json
from pathlib import Path
import re

from pdx_text import Object, root
from extract_m3_politics import fields, sequence
from political_rulebook import DEFAULTS, RULE_VERSION, TECH_BRIDGES, rulebook


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adopted(country):
    return {group: dict(body).get('object') for group, body in country.get('laws', [])}


def territorial_colonial_participants(politics, mapping):
    """Only surviving territorial colonial governments support this fact.

    EU5 building-type trading companies are commercial organizations, not
    evidence of a territorial colonial administration or its institution level.
    """
    represented = {c['source_id']: c for c in mapping['countries'].values() if c.get('source_id')}
    subjects, overlords = set(), set()
    for edge in politics['subjects']:
        cid = edge['subject']
        if edge['type'] not in ('colonial_nation', 'trade_company'):
            continue
        if cid not in represented or edge['overlord'] not in represented:
            continue
        if politics['countries'][cid].get('type') == 'building':
            continue
        if represented[cid]['country_type'] not in ('colonial', 'company'):
            continue
        subjects.add(cid)
        overlords.add(edge['overlord'])
    return subjects, overlords


def demographic_metrics(popdir, literacydir, expected):
    summary = read(popdir/'source_summary.json')
    litreport = read(literacydir/'source_literacy_report.json')
    popfile, litfile = popdir/'source_populations.csv', literacydir/'source_literacy.csv'
    if any(r['source_sha256'] != expected for r in (summary, litreport)):
        raise ValueError('Demographic input save mismatch')
    if sha(popfile) != summary['files_sha256'][popfile.name] or sha(litfile) != litreport['ledger_sha256']:
        raise ValueError('Demographic ledger hash mismatch')
    literacy = {r['pop_id']: r for r in csv.DictReader(litfile.open(encoding='utf-8-sig', newline=''))}
    metrics = defaultdict(lambda: dict(population=0, slave_population=0, literacy_numerator=0))
    for row in csv.DictReader(popfile.open(encoding='utf-8-sig', newline='')):
        n = int(row['centipersons']); l = literacy[row['pop_id']]
        if n != int(l['centipersons']): raise ValueError('Population/literacy size mismatch')
        out = metrics[row['source_owner']]
        out['population'] += n
        out['slave_population'] += n if row['source_class'] == 'slaves' else 0
        out['literacy_numerator'] += n * int(l['literacy_micro_percent'])
    for out in metrics.values():
        out['literacy_percent'] = (out.pop('literacy_numerator')/out['population']/1000000 if out['population'] else None)
        out['population'] /= 100
        out['slave_population'] /= 100
    return dict(metrics)


def evidence(country, features, metrics, colonial_subject=False, colonial_overlord=False):
    policies = set(adopted(country).values()) - {None}
    privileges = {dict(v).get('object') for _, v in (features.get('privileges') or [])} - {None}
    tokens = {f'policy:{p}' for p in policies}
    for kind, values in [('reform', country.get('reforms', [])), ('privilege', privileges),
                         ('advance', features.get('advances', [])), ('institution', features.get('institutions', []))]:
        tokens.update(f'{kind}:{v}' for v in values if v)
    facts = {country.get('government')}
    axes = {k: float(v) for k, v in (features.get('societal_values') or []) if -100 <= float(v) <= 100}
    if colonial_subject: facts.add('colonial_subject')
    if colonial_overlord: facts.add('colonial_overlord')
    if country.get('accepted_cultures'): facts.add('accepted_foreign_cultures')
    if metrics.get('slave_population', 0) > 0: facts.add('slave_population')
    if axes.get('serfdom_vs_free_subjects', 0) <= -50: facts.add('serf_society')
    if ('advance:codified_laws' in tokens or 'institution:legalism' in tokens):
        facts.add('codified_administration')
    if ('reform:agricultural_cultivation' in tokens and 'reform:land_inheritance_act' in tokens and
            axes.get('capital_economy_vs_traditional_economy', 0) >= 25):
        facts.add('agrarian_reform')
    if axes.get('mercantilism_vs_free_trade', 0) <= -50 and 'reform:bank_ledgers_system' in tokens:
        facts.add('mercantilist_commercial_state')
    tokens.update('fact:'+f for f in facts if f)
    return tokens, axes


def matches(rule, tokens):
    return (all(t in tokens for t in rule['all']) and
            (not rule['any'] or any(t in tokens for t in rule['any'])) and
            not any(t in tokens for t in rule['none']))


def normalized_catalog(raw):
    result = {}
    for key, val in raw.items():
        f = fields(root(val['script']))
        result[key] = {**val, 'parent': f.get('parent'),
                       'unlocking_laws': sequence(f.get('unlocking_laws'))}
    # Parent variants inherit constraints, technology and institutions unless overridden.
    def merged(key, chain=()):
        if key in chain: raise ValueError('Cyclic law parent')
        r = result[key].copy(); parent = r['parent']
        if parent:
            p = merged(parent, chain+(key,))
            for prop, script_key in [('institution','institution'), ('technologies','unlocking_technologies'),
                                      ('disallowing_laws','disallowing_laws'), ('unlocking_laws','unlocking_laws')]:
                if script_key not in fields(root(r['script'])): r[prop] = p[prop]
        return r
    return {k: merged(k) for k in result}


def candidate(rule, tokens):
    return {k: rule[k] for k in ('id','law','priority','reason')} | {
        'evidence': sorted(set(rule['all'] + [x for x in rule['any'] if x in tokens])),
        'confidence': 'direct_or_strong' if rule['priority'] >= 90 else 'inferred',
    }


def evaluate(country, features, metrics, catalog, rules, *, colonial_subject=False, colonial_overlord=False,
             historical_context=None, historical_priors=()):
    tokens, axes = evidence(country, features, metrics, colonial_subject, colonial_overlord)
    tokens.update('fact:'+f for f in (historical_context or {}).get('facts',[]))
    candidates = defaultdict(list)
    for row in historical_priors:
        candidates[row['group']].append({k:v for k,v in row.items() if k!='group'})
    for rule in rules:
        if matches(rule, tokens): candidates[rule['group']].append(candidate(rule, tokens))
    for group, law in DEFAULTS.items():
        candidates['lawgroup_'+group].append(dict(id='fallback.'+group, law='law_'+law if law else None,
            priority=0, reason='缺少足够直接证据的保守基线；不是源存档已证实的立法' if law else '仅在目标社会等级体系确实启用时适用；待社会结构阶段判定',
            evidence=[], confidence='low_fallback' if law else 'conditional_not_applicable'))
    for rows in candidates.values(): rows.sort(key=lambda x: (-x['priority'], x['id']))
    selected = {g: rows[0].copy() for g, rows in candidates.items()}
    conflicts = []
    # Reject weaker conflicting choices and try their next candidates. Monotonic per-group
    # cursors guarantee termination; never emit a combination with a known prohibition.
    cursors = {g: 0 for g in selected}
    for _ in range(sum(map(len,candidates.values()))+1):
        choices = {v['law'] for v in selected.values() if v['law']}
        issue = None
        for g in sorted(selected):
            a = selected[g]; law = a['law']
            if not law: continue
            incompatible = set(catalog[law]['disallowing_laws']) & choices
            others = [og for og, b in selected.items() if b['law'] in incompatible]
            if others:
                og = sorted(others)[0]
                loser = min([g,og], key=lambda x: (selected[x]['priority'], x))
                other = og if loser==g else g
                # A historical prior cannot force the only remaining compatible
                # fallback to disappear (e.g. serfdom -> traditionalism -> land tax).
                if (cursors[loser]+1>=len(candidates[loser]) and
                        selected[other]['confidence']=='historical_inference' and
                        cursors[other]+1<len(candidates[other])):
                    loser=other
                issue = (loser, f"{law} incompatible with {selected[og]['law']}")
                break
            # unlocking_laws are enactment transitions, NOT simultaneous constraints:
            # legacy_slavery is unlocked by slave_trade in the SAME law group.
            if law == 'law_subjecthood' and not choices & {'law_monarchy','law_theocracy','law_chiefdom','law_colonial_administration'}:
                issue = (g, 'Subjecthood is reserved for non-republican sovereignty in this conversion policy')
                break
        if issue is None: break
        g, why = issue
        conflicts.append({'group':g, 'rejected': selected[g]['law'], 'reason': why})
        cursors[g] += 1
        selected[g] = (candidates[g][cursors[g]].copy() if cursors[g] < len(candidates[g]) else
                       dict(id='blocked.'+g, law=None, priority=-1, reason='所有候选均违反目标法律约束，必须人工解决', evidence=[], confidence='blocked'))
    else: raise ValueError('Conflict resolution did not converge')
    techs = {key: sorted(set(terms)&tokens) for key,terms in TECH_BRIDGES.items() if set(terms)&tokens}
    for group, row in selected.items():
        row['alternatives'] = [c for c in candidates[group] if c['id'] != row['id']]
        row['required_technologies'] = catalog[row['law']]['technologies'] if row['law'] else []
        row['unsupported_required_technologies'] = sorted(set(row['required_technologies'])-techs.keys())
    warnings = []
    if 'policy:free_press' in tokens and any('policy:'+s in tokens for s in ('strict_censorship','limited_censorship')):
        warnings.append('自由出版与宗教审查并存：保留实际审查约束，不能直接赋予完整言论保障')
    if 'policy:slavery_outlawed' in tokens and metrics.get('slave_population', 0) > 0:
        warnings.append('废奴法与现存奴隶人口冲突：法律优先；人口阶段须转为自由人口并保持总人口守恒')
    if 'advance:abolished_serfdom' in tokens:
        warnings.append('abolished_serfdom 革新实际仅加陆军士气，不独立充当废除农奴法')
    if metrics.get('slave_population',0) > 0 and selected['lawgroup_slavery']['law']=='law_slavery_banned' and 'policy:slavery_outlawed' not in tokens:
        warnings.append('既有奴隶人口与最终法律冲突；不得部署或静默释放，须人工处理')
    if any(v['confidence'] == 'blocked' for v in selected.values()): warnings.append('存在无法自动解决的法律组合')
    return {'laws': selected, 'source_axes': axes, 'metrics': metrics,
            'capability_technology_proposals': techs, 'conflict_resolutions': conflicts,
            'warnings': warnings, 'tokens': sorted(tokens)}


def investment_add(script, institution):
    # Read unconditional modifier blocks only, never conditional AI/script branches.
    f = fields(root(script)); modifier = fields(f.get('modifier'))
    return int(modifier.get('country_'+institution+'_max_investment_add', 0))


def institutions(result, lawdefs, techdefs, institutiondefs):
    tokens = set(result['tokens']); laws = {v['law'] for v in result['laws'].values() if v['law']}
    enabled = {lawdefs[k]['institution'] for k in laws if lawdefs[k]['institution']}
    out = {}
    central = 'policy:centralized_bureaucracy_policy' in tokens
    modern = 'advance:modern_bureaucracy' in tokens
    lit = result['metrics'].get('literacy_percent')
    for institution in institutiondefs:
        why = []
        desired = 1 if institution in enabled else 0
        if desired:
            why.append('法律已建立服务，最低一级')
            if institution == 'institution_schools':
                if 'law_private_schools' not in laws:
                    if 'reform:the_education_act' in tokens or 'policy:education_of_the_people' in tokens:
                        desired += 1; why.append('大众教育制度补强 +1')
                    if central and lit is not None and lit >= 60:
                        desired += 1; why.append('源人口加权识字率 >=60% 且中央组织 +1')
            elif institution == 'institution_police':
                if central and 'law_dedicated_police' in laws:
                    desired += 1; why.append('专职治安与中央官僚 +1')
                if modern and central:
                    desired += 1; why.append('现代官僚能力 +1')
            elif institution == 'institution_home_affairs':
                if central: desired += 1; why.append('中央官僚 +1')
                if modern: desired += 1; why.append('现代官僚能力 +1')
            elif institution == 'institution_colonial_affairs':
                if 'fact:colonial_overlord' in tokens:
                    desired += 1; why.append('已运营殖民属国网络 +1')
                if modern and central:
                    desired += 1; why.append('中央现代殖民行政 +1')
            # Service coverage for health/welfare/workplace is not present: remain at 1.
        contributions = {k: investment_add(techdefs[k]['script'], institution)
                         for k in result['capability_technology_proposals']}
        contributions.update({k:investment_add(lawdefs[k]['script'],institution) for k in laws})
        contributions = {k:v for k,v in contributions.items() if v}
        cap = min(5,max(1,sum(contributions.values()))) if desired else 0
        out[institution] = dict(desired_level=desired, cap_if_proposed_tech_adopted=cap,
            planned_level=min(desired,cap), deployable_level=None if desired else 0,
            reasons=why, cap_contributions=contributions,
            budget_status='pending_target_population_and_bureaucracy' if desired else 'inactive',
            note='1.13.11 活跃机构上限修正值钳制在 1–5；没有额外基础 +1。能力桥接不是已授予技术。')
    return out


def source_inventory(politics, features, mapped, rules, definitions):
    used = {t for r in rules for key in ('all','any','none') for t in r[key]}
    used.update(t for terms in TECH_BRIDGES.values() for t in terms)
    # Inputs used outside declarative candidate rules (facts / service levels).
    used.update(['policy:centralized_bureaucracy_policy','reform:agricultural_cultivation',
                 'reform:land_inheritance_act','reform:bank_ledgers_system','reform:the_education_act',
                 'policy:education_of_the_people','advance:codified_laws','institution:legalism',
                 'advance:modern_bureaucracy'])
    counts = Counter()
    for cid in mapped:
        c=politics['countries'][cid]; f=features['countries'][cid]
        t,_=evidence(c,f,{})
        counts.update(x for x in t if not x.startswith('fact:'))
    inventory=[]
    policydefs={}
    for group,row in definitions['eu5']['laws'].items():
        for k,v in root(row['script']).entries():
            if isinstance(v,Object) and 'country_modifier' in fields(v): policydefs[k]=row
    tables={'policy':policydefs,'reform':definitions['eu5']['government_reforms'],
            'privilege':definitions['eu5']['estate_privileges'],'advance':definitions['eu5']['advances'],
            'institution':definitions['eu5']['institution']}
    for token,count in sorted(counts.items()):
        kind,key=token.split(':',1); definition=tables[kind].get(key)
        status=('rule_or_capacity_input' if token in used else
                'unknown_definition_review_required' if definition is None else 'context_only_no_automatic_law')
        inventory.append(dict(token=token,countries=count,status=status,
                              reason=('参与法律候选或机构能力判断' if token in used else
                                      '当前原版与已检索模组中未找到定义，禁止根据名称猜测' if definition is None else
                                      '已保留定义；本版不将此因素单独等同于 V3 立法，详见规则说明的证据边界'),
                              definition_file=definition['file'] if definition else None))
    return inventory


def render(report, out):
    esc=html.escape
    rows=[]
    for tag,c in report['countries'].items():
        if c['status'] != 'evaluated': continue
        lawrows=''.join('<tr><td>'+esc(g.removeprefix('lawgroup_'))+'</td><td>'+esc(v['law'] or '条件未适用/待核')+
            '</td><td>'+esc(v['reason'])+'</td><td>'+esc(', '.join(v['evidence']))+
            ('<br>原版参照：'+esc(', '.join(x['tag'] for x in v.get('references',[]))) if v.get('references') else '')+'</td><td>'+
            esc(', '.join(v['unsupported_required_technologies']))+'</td></tr>' for g,v in c['laws'].items())
        inst='；'.join(k.removeprefix('institution_')+': '+str(v['planned_level'])+'（制度目标 '+str(v['desired_level'])+'）' for k,v in c['institutions'].items())
        context=c.get('historical_context',{})
        mig=context.get('migration',{})
        context_text=('移民例外：'+('符合' if mig.get('eligible') else '不符合')+'；首都地区：'+str(context.get('capital_region'))+
                      '；文化传承：'+', '.join(h or '未知' for h in context.get('primary_heritages',[]))) if context else ''
        rows.append('<details class="country"><summary>'+esc(tag+' '+c['name'])+'</summary><p>'+esc(context_text)+'</p><p>'+esc(inst)+
                    '</p><p>'+esc('；'.join(c['warnings']))+'</p><table><tr><th>法律组</th><th>草案</th><th>理由</th><th>证据</th><th>缺少桥接的技术</th></tr>'+lawrows+'</table></details>')
    page='''<!doctype html><meta charset="utf-8"><title>EU5 → V3 政治转换规则审核</title>
<style>body{font:15px system-ui;max-width:1400px;margin:30px auto;background:#f7f5ef;color:#20312c}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:9px;border-bottom:1px solid #ccc;text-align:left;overflow-wrap:anywhere}summary{font-size:18px;padding:12px;cursor:pointer}details{background:white;margin:8px 0;padding:8px}input{padding:10px;width:50%}</style>
<h1>EU5 → V3 政治转换规则审核</h1><p>规则草案 RULE_VERSION · EU5 1.3.11 → V3 1.13.11 · 未部署到游戏。</p>
<p>机构显示制度目标与能力技术桥接后的计划值；实际官僚成本、完整技术及条件脚本尚待部署前核验。缺少证据的保守基线不是源存档的确定事实。</p>
<input id="search" placeholder="搜索国家、法律或源政策"><p>''' + esc(json.dumps(report['summary'],ensure_ascii=False))+'</p>'+''.join(rows)+'''
<script>document.getElementById('search').addEventListener('input',function(){let q=this.value.toLowerCase();document.querySelectorAll('.country').forEach(e=>e.hidden=!e.textContent.toLowerCase().includes(q));});</script>'''
    (out/'review.html').write_text(page.replace('RULE_VERSION',report['rule_version']),encoding='utf-8')


def build(a):
    politics=read(a.politics); features=read(a.evidence/'features.json'); definitions=read(a.evidence/'definitions.json'); mapping=read(a.mapping)
    if len({r['source_sha256'] for r in (politics,features,mapping)}) != 1: raise ValueError('Input saves differ')
    metrics=demographic_metrics(a.population,a.literacy,politics['source_sha256'])
    laws=normalized_catalog(definitions['v3']['laws']); rules=rulebook()
    groups={v['group'] for v in laws.values()}
    if groups != {'lawgroup_'+g for g in DEFAULTS}: raise ValueError('Uncovered target law groups')
    for r in rules:
        if r['law'] not in laws or laws[r['law']]['group'] != r['group']: raise ValueError('Invalid rule target '+r['id'])
    contexts={};native=None;context_inputs=[]
    if a.historical_context:
        from political_historical_context import load_native,prepare_contexts,historical_candidates
        if not all((a.audit,a.economy,a.v3)):raise ValueError('Historical context requires --audit --economy --v3')
        if sha(a.audit)!=mapping['audit_sha256']:raise ValueError('Audit differs from mapped run')
        owner_path=a.mapping.parent/'province_owners.json'
        native=load_native(a.v3,Path(mapping['mod_directory']))
        contexts=prepare_contexts(mapping,politics,features,read(a.audit),metrics,read(a.economy),native,read(owner_path))
        context_inputs=[a.audit,a.economy,owner_path,Path(__file__).with_name('political_historical_context.py')]
    subjects,overlords=territorial_colonial_participants(politics,mapping)
    countries={}
    for tag,target in mapping['countries'].items():
        cid=target['source_id']
        if not cid:
            countries[tag]={'status':'vanilla_uncolonized_fallback','name':target.get('name_simp_chinese',tag)};continue
        context=contexts.get(tag)
        priors=historical_candidates(context,native,laws) if context else []
        result=evaluate(politics['countries'][cid],features['countries'][cid],metrics.get(cid,{}),laws,rules,
                        colonial_subject=cid in subjects,colonial_overlord=cid in overlords,
                        historical_context=context,historical_priors=priors)
        if context:result['historical_context']=context
        result.update(status='evaluated',source_id=cid,name=target.get('name_simp_chinese',tag),
                      target_country_type=target['country_type'],export_enabled=False)
        result['institutions']=institutions(result,laws,definitions['v3']['technology/technologies'],definitions['v3']['institutions'])
        if target['country_type']=='decentralized':
            result['warnings'].append('目标为去中心化国家：法律仅供源社会结构参考，不输出可游玩国家机构')
            for inst in result['institutions'].values():
                inst.update(planned_level=0,deployable_level=0,budget_status='decentralized_no_export')
        countries[tag]=result
    evaluated=[c for c in countries.values() if c['status']=='evaluated']
    inventory=source_inventory(politics,features,{c['source_id'] for c in evaluated},rules,definitions)
    historical_laws={row['law'] for c in evaluated for v in c['laws'].values() for row in [v]+v['alternatives']
                     if row['confidence']=='historical_inference'}
    targetcoverage={k:{'group':v['group'],'status':'automatic_candidate' if any(r['law']==k for r in rules) else
                       'historical_candidate' if k in historical_laws else
                       'fallback_candidate' if k.removeprefix('law_') in DEFAULTS.values() else 'requires_additional_verified_evidence',
                       'required_technologies':v['technologies'],'disallowing_laws':v['disallowing_laws'],
                       'unlocking_laws':v['unlocking_laws'],'definition_file':v['file']}
                    for k,v in laws.items()}
    report=dict(schema=1,rule_version=RULE_VERSION,status='review_only_not_deployed',source_sha256=politics['source_sha256'],
        target_version='1.13.11',countries=countries,source_inventory=inventory,target_law_inventory=targetcoverage,rules=rules,
        limitations=['No engine execution of possible/can_enact/scripted triggers/DLC checks',
                     'Technology bridges are proposals, not a complete researched technology set',
                     'Estate and bureaucracy references retained, effective power/service coverage not evaluated',
                     'Caste and Edo law groups require separately reviewed target social hierarchies',
                     'Institution budget and target incorporated-population cost pending',
                     'Source mods and legacy unknown definitions require review; no guessed automatic mapping'],
        summary=dict(evaluated_countries=len(evaluated),vanilla_fallback_countries=len(countries)-len(evaluated),
                     law_groups=len(groups),target_laws=len(laws),institutions=7,rules=len(rules),
                     conflicts_resolved=sum(len(c['conflict_resolutions']) for c in evaluated),
                     unknown_source_keys=sum(r['status']=='unknown_definition_review_required' for r in inventory),
                     blocked_law_groups=sum(v['confidence']=='blocked' for c in evaluated for v in c['laws'].values()),
                     low_confidence_law_choices=sum(v['confidence']=='low_fallback' for c in evaluated for v in c['laws'].values()),
                     historical_law_choices=sum(v['confidence']=='historical_inference' for c in evaluated for v in c['laws'].values()),
                     open_borders_countries=sum(c['laws']['lawgroup_migration']['law']=='law_no_migration_controls' for c in evaluated)),
        native_reference_files_sha256=native['files_sha256'] if native else {},
        input_sha256={str(p):sha(p) for p in [a.politics,a.mapping,a.evidence/'features.json',a.evidence/'definitions.json',Path(__file__),Path(__file__).with_name('political_rulebook.py')]+context_inputs})
    a.output.mkdir(parents=True,exist_ok=False)
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (a.output/'rulebook.json').write_text(json.dumps({'version':RULE_VERSION,'defaults':DEFAULTS,'rules':rules,'capability_bridges':TECH_BRIDGES},ensure_ascii=False,indent=2),encoding='utf-8')
    if native:
        from political_historical_context import PROFILES
        (a.output/'historical-reference.json').write_text(json.dumps({'profiles':PROFILES,'native':native},ensure_ascii=False,indent=2),encoding='utf-8')
    render(report,a.output)
    print(json.dumps(report['summary'],ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('politics','evidence','mapping','population','literacy','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--historical-context',action='store_true')
    for key in ('audit','economy','v3'):p.add_argument('--'+key,type=Path)
    build(p.parse_args())
