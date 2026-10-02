"""Generate explicitly configured resident-only custom cultural identities."""
import json
import re
from pathlib import Path

from build_m2_prototype import objects, strings
from build_m3_world import block, load_localization
from m3_world import digest, fields
from m4_religions import definitions, source_color
from pdx_text import root


def checked_source(source, definition, config):
    groups = strings(definition['culture_groups']) if 'culture_groups' in definition else []
    if definition.get('language') != config['source_language'] or set(groups) != set(config['source_groups']):
        raise ValueError('Custom resident source definition changed: '+source)


def checked_source_language(languages, config):
    """Resolve only an explicitly configured language or nested dialect."""
    key = config['source_language']
    matches = [(None, languages[key])] if key in languages else []
    for parent, definition in languages.items():
        if 'dialects' in definition:
            for dialect, body in objects(definition['dialects']):
                if dialect == key:
                    matches.append((parent, {'family':definition.get('family'), **fields(body)}))
    if config.get('source_language_scope') == 'top_level':
        # Explicit exception for installed Greek's self-named default dialect.
        matches = [(parent,definition) for parent,definition in matches if parent is None]
    if len(matches) != 1 or matches[0][0] != config.get('source_language_parent'):
        raise ValueError('Missing, ambiguous or changed source language parent: '+key)
    if matches[0][1].get('family') != config.get('source_language_family'):
        raise ValueError('Custom source language family changed: '+key)


def resident_language(config, traits, groups, new_traits, new_groups):
    reviewed = config.get('reviewed_language')
    if reviewed:
        if config.get('aggregate_language') or config.get('language_trait'):
            raise ValueError('Reviewed language conflicts with automatic language selection')
        language, group = reviewed['trait'], reviewed['group']
        if not reviewed.get('sources') or not reviewed.get('basis'):
            raise ValueError('Reviewed language requires evidence and a design rationale')
        if not all(re.fullmatch('[a-z][a-z0-9_]*', k) for k in (language, group)):
            raise ValueError('Invalid reviewed language identifier')
        if not language.startswith('eu5_reviewed_language_') or language in traits:
            raise ValueError('Reviewed language collision or namespace mismatch')
        if group in groups:
            if groups[group]['type'] != 'language':raise ValueError('Invalid reviewed language group')
        else:
            if not group.startswith('eu5_reviewed_language_group_') or not reviewed.get('group_labels'):
                raise ValueError('New reviewed language group requires explicit labels')
            new_groups[group] = 'type = language'
        body = 'type = language\ntrait_group = '+group
        if language in new_traits and new_traits[language] != body:
            raise ValueError('Conflicting reviewed language group')
        new_traits[language] = body
        return language, group
    if config.get('aggregate_language'):
        seed=config['aggregate_seed']
        language='eu5_aggregate_language_'+seed
        group='eu5_aggregate_language_group_'+seed
        if language in traits or group in groups:raise ValueError('Aggregate language collision')
        new_traits[language]='type = language\ntrait_group = '+group
        new_groups[group]='type = language'
        return language,group
    language = config['language_trait']
    if language:
        if traits[language]['type'] != 'language':raise ValueError('Invalid resident language type')
        group = traits[language]['trait_group']
        if groups[group]['type'] != 'language':raise ValueError('Invalid resident language group')
        return language, group
    language = 'eu5_resident_language_'+config['source_language']
    group = config.get('language_group') or 'eu5_resident_language_group_'+config['source_language']
    if language in traits:raise ValueError('Custom resident language collision')
    if config.get('language_group'):
        if groups[group]['type'] != 'language':raise ValueError('Invalid resident language group')
    else:
        if group in groups:raise ValueError('Custom resident language group collision')
        new_groups[group] = 'type = language'
    body = 'type = language\ntrait_group = '+group
    if language in new_traits and new_traits[language] != body:
        raise ValueError('Conflicting resident source language family')
    new_traits[language] = body
    return language, group


def write_custom_cultures(out, game, eu5, source_defs, profile, reserved):
    configs = profile.get('custom_resident_cultures',{})
    if not configs:
        return {'cultures':[], 'inputs_sha256':{}}
    templates = {k:o for p in sorted((game/'common/cultures').glob('*.txt')) for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    traits = definitions(game/'common/discrimination_traits')
    groups = definitions(game/'common/discrimination_trait_groups')
    color_path = eu5/'main_menu/common/named_colors/02_map.txt'
    colors = color_path.read_text(encoding='utf-8-sig')
    locs = {lang:load_localization(eu5/'main_menu/localization'/lang) for lang in ('english','simp_chinese')}
    bodies, new_traits, new_groups, labels, records = {}, {}, {}, {lang:{} for lang in locs}, []
    source_languages = definitions(eu5/'in_game/common/languages')
    inputs = {str(color_path):digest(color_path)}
    for directory in (eu5/'in_game/common/cultures',eu5/'in_game/common/languages',game/'common/cultures',game/'common/discrimination_traits',game/'common/discrimination_trait_groups'):
        inputs.update({str(p):digest(p) for p in sorted(directory.glob('*.txt'))})
    for source,config in sorted(configs.items()):
        if source in profile.get('culture_compaction',{}):continue
        if not re.fullmatch('[a-z][a-z0-9_]*',source):raise ValueError('Invalid culture identifier')
        key = 'eu5_resident_'+source; heritage = config.get('heritage_trait') or 'eu5_resident_heritage_'+source
        if key in reserved or (not config.get('heritage_trait') and heritage in traits) or source in profile['culture_aliases']:
            raise ValueError('Custom resident identity collision: '+source)
        checked_source(source,source_defs[source],config)
        if config.get('asset_basis'):
            basis=config['asset_basis']
            for label in ('source_file','scaffold_policy'):
                path=Path(basis[label])
                if digest(path)!=basis[label+'_sha256']:raise ValueError('Frozen asset scaffold input changed: '+str(path))
                inputs[str(path)]=digest(path)
        group = config['heritage_group'] or 'eu5_resident_heritage_group_'+source
        if config.get('heritage_trait'):
            if not config.get('heritage_design',{}).get('sources') or not config['heritage_design'].get('basis'):
                raise ValueError('Shared native heritage requires a documented design decision')
            if traits[heritage]['type'] != 'heritage' or traits[heritage]['trait_group'] != group:
                raise ValueError('Shared native heritage group mismatch')
        if config['heritage_group']:
            if groups[group]['type'] != 'heritage':raise ValueError('Invalid custom resident heritage type')
        else:
            if group in groups:raise ValueError('Custom resident heritage group collision')
            new_groups[group]='type = heritage'
        if not config['language_trait'] and not config.get('aggregate_language'):
            checked_source_language(source_languages,config)
        language,language_group = resident_language({**config,'aggregate_seed':source},traits,groups,new_traits,new_groups)
        template = templates[config['template']]; template_fields = fields(template)
        if 'display_color_override' in config:
            override=config['display_color_override']
            if source_defs[source]['color']!=override['source_color']:raise ValueError('Color override source changed')
            color=override['rgb'];notes=[override['reason']]
            if len(color)!=3 or any(not 0<=v<=1 for v in color):raise ValueError('Invalid display override')
        else:color,notes = source_color(colors,source_defs[source]['color'])
        body,n = re.subn(r'\bheritage\s*=\s*\w+','heritage = '+heritage,template.text())
        if n != 1:raise ValueError('Ambiguous template heritage')
        body,n = re.subn(r'\blanguage\s*=\s*\w+','language = '+language,body)
        if n != 1:raise ValueError('Ambiguous template language')
        body,n = re.subn(r'\bcolor\s*=\s*(?:(?:rgb|hsv|hsv360)\s*)?\{[^}]*\}', 'color = { '+' '.join(map(str,color))+' }',body)
        if n != 1:raise ValueError('Ambiguous template color')
        bodies[key] = body
        if not config.get('heritage_trait'):
            new_traits[heritage] = 'type = heritage\ntrait_group = '+group
        for lang,loc in locs.items():
            label = config.get('display_labels',{}).get(lang,loc[source])
            labels[lang][key] = label
            if not config.get('heritage_trait'):
                labels[lang][heritage] = label+('传承' if lang=='simp_chinese' else ' Heritage')
            if not config['heritage_group']:
                # Review state belongs in asset metadata, never in game labels.
                labels[lang][group]=label+('传承' if lang=='simp_chinese' else ' Heritage')
            if config.get('reviewed_language'):
                labels[lang][language] = config['reviewed_language']['labels'][lang]
                if language_group in new_groups:
                    labels[lang][language_group] = config['reviewed_language']['group_labels'][lang]
            elif config.get('aggregate_language'):
                labels[lang][language]=config['aggregate_language_labels'][lang]
                labels[lang][language_group]=config['aggregate_language_labels'][lang]
            elif not config['language_trait']:
                labels[lang][language] = loc[config['source_language']]
                if language_group in new_groups:labels[lang][language_group] = loc[config['source_language']]
        records.append({'source':source,'target':key,'template':config['template'],
                        'source_language':config['source_language'],'source_groups':config['source_groups'],
                        'heritage':heritage,'heritage_group':group,'language':language,'language_group':language_group,
                        'heritage_design':config.get('heritage_design'),
                        'reviewed_language':config.get('reviewed_language'),
                        'research_review':config.get('research_review'),
                        'custom_language':not bool(config['language_trait']),
                        'aggregate_language':config.get('aggregate_language',False),
                        'aggregate_members':config.get('aggregate_members',[]),
                        'isolated_language_group':not bool(config['language_trait']) and not bool(config.get('language_group')),
                        'source_language_family':config.get('source_language_family'),
                        'source_language_parent':config.get('source_language_parent'),
                        'source_language_scope':config.get('source_language_scope'),
                        'provisional_heritage_group':not bool(config['heritage_group']),
                        'review_status':config.get('review_status','explicit_identity_template_approximations'),
                        'asset_basis':config.get('asset_basis'),
                        'default_religion':template_fields['religion'],'color':color,'color_notes':notes,
                        'labels':{lang:labels[lang][key] for lang in labels},'reason':config['reason'],
                        'limitation':config['template_limitation']})
    for relative,values in [('common/cultures/zz_eu5_resident_cultures.txt',bodies),('common/discrimination_traits/zz_eu5_resident_cultures.txt',new_traits),('common/discrimination_trait_groups/zz_eu5_resident_languages.txt',new_groups)]:
        path = out/relative;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(''.join(block(k,v) for k,v in sorted(values.items())),encoding='utf-8-sig')
    for lang,values in labels.items():
        path = out/'localization'/lang/('eu5_resident_cultures_l_'+lang+'.yml');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('l_'+lang+':\n'+''.join(' '+k+':0 '+json.dumps(v,ensure_ascii=False)+'\n' for k,v in sorted(values.items())),encoding='utf-8-sig')
    return {'cultures':records,'inputs_sha256':inputs}
