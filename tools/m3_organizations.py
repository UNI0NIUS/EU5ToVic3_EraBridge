"""Translate overlapping EU5 organizations into V3's exclusive bloc system.

Source sovereignty takes precedence: never liberate a subject or conscript an
unrelated overlord merely to preserve a church membership. Every loss is audited.
"""
from collections import Counter, defaultdict

from pdx_text import root
from build_m2_prototype import objects
from m3_world import fields


KINDS = {'hre': ('identity_eu5_hre_empire', 'principle_eu5_hre_vassalization_1'),
         'middle_kingdom': ('identity_sovereign_empire', 'principle_vassalization_1'),
         'ilkhanate': ('identity_sovereign_empire', 'principle_vassalization_1'),
         'japanese_shogunate': ('identity_eu5_shogunate', 'principle_eu5_shogunate_vassalization_1'),
         'autocephalous_patriarchate': ('identity_religious', 'principle_sacred_civics_1')}


def plan_blocs(politics, tags, countries, edges):
    parents = {e['target_subject']: e['target_overlord'] for e in edges}
    roots = {}
    for tag in countries:
        cur, seen = tag, set()
        while cur in parents:
            if cur in seen: raise ValueError('Subject cycle while planning blocs')
            seen.add(cur); cur = parents[cur]
        roots[tag] = cur
    families = defaultdict(set)
    for tag, top in roots.items(): families[top].add(tag)
    candidates, omitted, ignored = [], [], []
    for org in politics['international_organizations']:
        if not org['members']: continue
        if org['type'] not in KINDS:
            ignored.append({'id': org['id'], 'type': org['type'], 'reason': 'not_a_nonoverlapping_political_bloc'})
            continue
        surviving = sorted({tags[s] for s in org['members'] if s in tags})
        if not surviving: continue
        leader = org.get('leader')
        selection = 'source_organization_leader'
        row = {'source_id': org['id'], 'source_type': org['type'], 'source_leader': leader,
               'leader': tags.get(leader), 'leader_selection': selection,
               'source_members_surviving': surviving,
               'source_members_without_target': sorted(set(org['members']) - tags.keys(), key=int)}
        if not leader or leader == '0':
            omitted.append(dict(row, reason='source_leadership_vacuum')); continue
        if leader not in tags:
            omitted.append(dict(row, reason='source_leader_has_no_target_country')); continue
        if org['type']=='japanese_shogunate':
            from source_country_names import shogunate_roles
            row.update(shogunate_roles(politics,org))
            row.update(nominal_shogun=tags[leader],
                imperial_court=[tags[s] for s in org.get('special_statuses',{}).get('japanese_emperor',[]) if s in tags],
                source_constitution=org.get('constitution',{}))
            if tags[leader] in parents and roots[tags[leader]] in surviving:
                # V3 requires an independent bloc leader. Preserve the existing
                # union rather than freeing the nominal shogun or inventing a ruler.
                row['leader']=roots[tags[leader]]
                row['leader_selection']='independent_member_sovereign_of_nominal_shogun'
        if row['leader'] in parents:
            omitted.append(dict(row, reason='leader_is_subject', overlord=parents[tags[leader]])); continue
        identity, principle = KINDS[org['type']]
        row.update(identity=identity, principle=principle, name='EU5_BLOC_' + org['id'],
                   founding_date=org.get('created') or politics['date'])
        candidates.append(row)
    order = {k: n for n,k in enumerate(KINDS)}
    candidates.sort(key=lambda b: (order[b['source_type']], int(b['source_id'])))
    # Reserve independent church leaders before political membership assignment.
    reserved = {}
    accepted = []
    for b in candidates:
        if b['leader'] in reserved:
            omitted.append(dict(b, reason='leader_already_leads_another_bloc')); continue
        reserved[b['leader']] = b['name']; accepted.append(b)
    assigned = {}
    for b in accepted:
        direct, excluded = {b['leader']}, []
        for tag in b['source_members_surviving']:
            top = roots[tag]
            reason = None
            if top not in b['source_members_surviving'] and top != b['leader']:
                reason = 'overlord_not_a_source_member'
            elif top in reserved and reserved[top] != b['name']:
                reason = 'reserved_as_other_bloc_leader'
            elif top in assigned and assigned[top] != b['name']:
                reason = 'already_in_other_bloc'
            if reason:
                excluded.append({'tag': tag, 'sovereign': top, 'reason': reason})
            else:
                direct.add(top)
        members = set().union(*(families[t] for t in direct))
        for tag in members:
            if tag in assigned: raise ValueError('Duplicate bloc membership: ' + tag)
            assigned[tag] = b['name']
        b.update(direct_members=sorted(direct - {b['leader']}), members=sorted(members),
                 subjects_joined_automatically=sorted(members - direct),
                 additional_subject_members=sorted(members - set(b['source_members_surviving'])),
                 excluded_members=excluded)
    return {'power_blocs': accepted, 'omitted_organizations': omitted, 'other_organizations': ignored,
            'policy': 'Preserve subject trees; reserve independent leaders; political membership before church membership; subjects follow sovereign.',
            'requires_dlc_feature': 'power_bloc_features', 'runtime_membership_check': 'pending'}


def plan_treaties(relations, tags, countries, edges, autonomous):
    parents = {e['target_subject']: e for e in edges}
    treaties, omitted, seen = [], [], set()
    for rel in relations:
        if rel['type'] != 'alliance' or not rel['mutual']: continue
        a,b = tags.get(rel['first']), tags.get(rel['second'])
        row = dict(rel, target_first=a, target_second=b)
        reason = None
        if not a or not b: reason = 'country_has_no_target_territory'
        elif a == b: reason = 'same_target_country'
        elif any(countries[t]['country_type'] == 'decentralized' for t in (a,b)):
            reason = 'decentralized_country'
        elif any(t in parents and not autonomous.get(parents[t]['target_type'], False) for t in (a,b)):
            reason = 'insufficient_subject_diplomatic_autonomy'
        elif parents.get(a, {}).get('target_overlord') == b or parents.get(b, {}).get('target_overlord') == a:
            reason = 'direct_subject_relation'
        elif tuple(sorted((a,b))) in seen: reason = 'duplicate_pair'
        if reason:
            omitted.append(dict(row, reason=reason)); continue
        a,b = sorted((a,b)); seen.add((a,b))
        treaties.append(dict(row, target_first=a, target_second=b, article='defensive_pact',
                             binding_months=1, automatic_expiry=False, name=f'EU5_DEFENCE_{a}_{b}'))
    return {'created': treaties, 'omitted': omitted,
            'other_relation_types_not_converted': dict(Counter(r['type'] for r in relations if r['type'] != 'alliance')),
            'binding_policy': 'One month from 1836.1.1; termination allowed afterwards, no automatic expiry.',
            'relation_initialization': 50, 'technology_prerequisite': 'international_relations'}


def export_organizations(exporter):
    from build_m3_world import block
    from m3_hre_stability import export_hre_stability
    from m3_hre_constitution import plan_constitution, export_constitutions
    from m3_hre_player_exit import export_player_exit
    w = exporter.w
    edges = w.edges + exporter.vanilla_fallback_subjects
    organization_report = plan_blocs(w.politics, w.tags, w.countries, edges)
    for b in organization_report['power_blocs']:
        if b['source_type'] == 'hre':
            org = next(o for o in w.politics['international_organizations'] if o['id'] == b['source_id'])
            b['constitution'] = plan_constitution(org, b, w.tags, w.profile.get('hre_market_mode', 'source_only'))
    export_hre_stability(exporter, organization_report['power_blocs'])
    from m3_shogunate import export_shogunate
    export_shogunate(exporter, organization_report['power_blocs'])
    subject_defs = dict(objects(root(w.read('common/subject_types/00_subject_types.txt'))))
    autonomous = {k.removeprefix('subject_type_'): fields(v).get('can_start_own_diplomatic_plays') == 'yes'
                  for k,v in subject_defs.items()}
    treaty_report = plan_treaties(w.politics['relations'], w.tags, w.countries, edges, autonomous)
    history = []
    prerequisites = defaultdict(list)
    for b in organization_report['power_blocs']:
        leader = w.countries[b['leader']]
        source = w.politics['countries'][b['source_leader']]
        names = {'hre': ('Holy Roman Empire', '神圣罗马帝国'),
                 'middle_kingdom': ('Celestial Empire', '天朝'),
                 'ilkhanate': ('Ilkhanate', '伊尔汗国')}
        names['japanese_shogunate']=('Japanese Shogunate','日本幕府')
        labels = names.get(b['source_type'])
        if not labels:
            faith = leader.get('religion')
            en,zh = (' Orthodox Church','正教会') if faith == 'orthodox' else (' Autocephalous Church','自主教会')
            labels = (leader['name_english'] + en, leader['name_simp_chinese'] + zh)
        b['name_english'], b['name_simp_chinese'] = labels
        for lang,label in zip(('english','simp_chinese'), labels): exporter.localization[lang][b['name']] = label
        color = ' '.join(source['color'])
        body = f'name = {b["name"]}\nmap_color = {{ {color} }}\nfounding_date = {b["founding_date"]}\nidentity = {b["identity"]}\nprinciple = {b["principle"]}\n'
        body += ''.join(f'member = c:{tag}\n' for tag in b['direct_members'])
        charter = ''
        if b['source_type'] == 'hre':
            charter = block('power_bloc', 'add_cohesion_number = 50\n' + ''.join(
                'add_principle = ' + p + '\n' for p in b['constitution']['additional_principles']))
        elif b['source_type']=='japanese_shogunate':
            charter=block('power_bloc','add_cohesion_number = 50')
        history.append(block('c:' + b['leader'] + ' ?', block('create_power_bloc', body) + charter))
        if b['identity'] == 'identity_religious':
            # Keep either compatible existing law; only fix incompatible template secularism.
            prerequisites[b['leader']].append(block('if',
                block('limit', block('NOR', 'has_law_or_variant = law_type:law_state_religion\nhas_law_or_variant = law_type:law_freedom_of_conscience'))
                + 'activate_law = law_type:law_freedom_of_conscience'))
    exporter.write('common/history/power_blocs/00_eu5_world.txt', block('POWER_BLOCS', ''.join(history)))
    treaties, relations = [], defaultdict(list)
    for t in treaty_report['created']:
        a,b = t['target_first'],t['target_second']
        body = f'name = {t["name"]}\nfirst_country = c:{a}\nsecond_country = c:{b}\nis_draft = no\nentered_into_force_on = {w.profile["start_date"]}\n'
        body += block('binding_period', 'months = 1') + block('articles_to_create', '{ article = defensive_pact }')
        treaties.append(block('create_treaty', body))
        relations[a].append(block('set_relations', f'country = c:{b}\nvalue = 50'))
        for tag in (a,b):
            effect = 'add_technology_researched = international_relations\n'
            if effect not in prerequisites[tag]: prerequisites[tag].append(effect)
        for lang in exporter.localization:
            names = [w.countries[tag]['name_' + lang] for tag in (a,b)]
            exporter.localization[lang][t['name']] = ('—'.join(names) + '共同防御条约' if lang == 'simp_chinese'
                                                     else '–'.join(names) + ' Mutual Defence Treaty')
    exporter.write('common/history/treaties/00_eu5_world.txt', block('TREATIES', ''.join(treaties)))
    exporter.write('common/history/diplomacy/01_eu5_allied_relations.txt', block('DIPLOMACY', ''.join(block('c:' + t + ' ?', ''.join(r)) for t,r in sorted(relations.items()))))
    exporter.write('common/history/countries/01_eu5_diplomatic_prerequisites.txt', block('COUNTRIES', ''.join(block('c:' + t + ' ?', ''.join(r)) for t,r in sorted(prerequisites.items()))))
    export_constitutions(exporter, organization_report['power_blocs'])
    organization_report['source_player_exit'] = export_player_exit(exporter, organization_report['power_blocs'], edges)
    exporter.organization_report, exporter.treaty_report = organization_report, treaty_report
