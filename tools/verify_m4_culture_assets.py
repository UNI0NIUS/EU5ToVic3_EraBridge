"""Read actual resident culture assets and their references in the pinned candidate."""
from pathlib import Path

from build_m2_prototype import objects, strings
from build_m3_world import load_localization
from m3_world import digest, fields, load_json
from pdx_text import root


def effective_definitions(game, mod, directory, inputs, political):
    replaced = load_json(mod/'.metadata/metadata.json')['game_custom_data']['replace_paths']
    paths = {}
    for base in (game, mod):
        if base == game and any(directory == p or directory.startswith(p+'/') for p in replaced):
            continue
        for path in sorted((base/directory).glob('*.txt')):
            paths[path.name] = path
    result = {}
    for path in paths.values():
        sha = digest(path)
        if path.is_relative_to(mod):
            assert sha == political['output_sha256'][str(path.relative_to(mod))], ('Political culture asset changed',str(path))
        inputs[str(path)] = sha
        for key,obj in objects(root(path.read_text(encoding='utf-8-sig'))):
            assert key not in result, ('Duplicate effective definition',directory,key)
            result[key] = fields(obj)
    return result


def validate_culture(key, definition, traits, groups, religions, localizations):
    """Validate graph references without using the identity mapping resolver."""
    for typ in ('heritage','language'):
        trait = definition[typ]
        assert trait in traits and traits[trait]['type'] == typ, ('Invalid culture trait',key,typ,trait)
        group = traits[trait]['trait_group']
        assert group in groups and groups[group]['type'] == typ, ('Invalid culture trait group',key,typ,group)
    assert definition['religion'] in religions, ('Missing default religion',key)
    for field in ('male_common_first_names','female_common_first_names','common_last_names'):
        assert strings(definition[field]), ('Empty culture name list',key,field)
    for lang,loc in localizations.items():
        for label in (key,definition['heritage'],definition['language']):
            assert loc.get(label), ('Missing culture localization',key,lang,label)


def validate_source_language(record, languages):
    key = record['source_language']
    found = []
    for name, definition in languages.items():
        if name == key:
            found.append((None, definition.get('family')))
        if 'dialects' in definition:
            for dialect, body in objects(definition['dialects']):
                if dialect == key:
                    found.append((name, fields(body).get('family', definition.get('family'))))
    if record.get('source_language_scope')=='top_level':found=[pair for pair in found if pair[0] is None]
    assert found == [(record.get('source_language_parent'), record['source_language_family'])], ('Source language ancestry differs', key, found)


def verify_culture_assets(game, political_run, crosswalk, religions, assets=None, resident_report=None):
    report_path = political_run/'conversion_report.json'
    political = load_json(report_path); mod = Path(political['mod_directory'])
    inputs = {str(report_path):digest(report_path)}
    metadata = mod/'.metadata/metadata.json'
    assert digest(metadata) == political['output_sha256'][str(metadata.relative_to(mod))]
    inputs[str(metadata)] = digest(metadata)
    cultures = effective_definitions(game,mod,'common/cultures',inputs,political)
    traits = effective_definitions(game,mod,'common/discrimination_traits',inputs,political)
    groups = effective_definitions(game,mod,'common/discrimination_trait_groups',inputs,political)
    native_templates = dict(cultures)
    resident_report = resident_report or {'cultures':[], 'inputs_sha256':{}}
    resident_custom = {c['target']:c for c in resident_report['cultures']}
    for p,sha in resident_report['inputs_sha256'].items():assert digest(Path(p)) == sha
    inputs.update(resident_report['inputs_sha256'])
    source_languages = {}
    for p in resident_report['inputs_sha256']:
        path = Path(p)
        if path.parent.name == 'languages':
            source_languages.update({k:fields(o) for k,o in objects(root(path.read_text(encoding='utf-8-sig')))})
    added_cultures = set()
    if assets:
        for directory,definitions in [('common/cultures',cultures),('common/discrimination_traits',traits),('common/discrimination_trait_groups',groups)]:
            for path in sorted((assets/directory).glob('*.txt')):
                inputs[str(path)] = digest(path)
                for key,obj in objects(root(path.read_text(encoding='utf-8-sig'))):
                    assert key not in definitions, ('Resident asset collision',key)
                    definitions[key] = fields(obj)
                    if directory == 'common/cultures':added_cultures.add(key)
    assert added_cultures == resident_custom.keys(), ('Resident culture manifest differs',added_cultures)
    locs = {}
    for lang in ('english','simp_chinese'):
        locs[lang] = {}
        for base in (game/'localization'/lang,mod/'localization'/lang,mod/'localization/replace'/lang):
            for path in sorted(base.rglob('*.yml')):
                sha = digest(path)
                if path.is_relative_to(mod):
                    assert sha == political['output_sha256'][str(path.relative_to(mod))], ('Political localization changed',str(path))
                inputs[str(path)] = sha
            locs[lang].update(load_localization(base))
        if assets:
            locs[lang].update(load_localization(assets/'localization'/lang))
    used = {x['target_culture'] for x in crosswalk.values() if x['target_culture']}
    custom = {c['target']:c for c in political['custom_cultures']}
    assert used <= cultures.keys(), ('Undefined resident cultures',sorted(used-cultures.keys()))
    checked = used | custom.keys() | resident_custom.keys()
    for key in sorted(checked):
        validate_culture(key,cultures[key],traits,groups,religions,locs)
        if key in custom:
            c = custom[key]; actual = cultures[key]
            assert actual['heritage'] == c['heritage'] and actual['language'] == c['language'], ('Custom culture definition differs',key)
            assert traits[actual['heritage']]['trait_group'] == c['heritage_group']
            assert traits[actual['language']]['trait_group'] == c['language_group']
        if key in resident_custom:
            c = resident_custom[key];actual = cultures[key];template = native_templates[c['template']]
            assert actual['heritage'] == c['heritage'] and actual['language'] == c['language']
            assert traits[actual['heritage']]['trait_group'] == c['heritage_group']
            assert traits[actual['language']]['trait_group'] == c['language_group']
            assert [float(v) for v in strings(actual['color'])] == c['color']
            if c.get('provisional_heritage_group'):
                assert c['heritage_group']=='eu5_resident_heritage_group_'+c['source']
                assert c['review_status']=='generated_preservation_candidate_not_historically_reviewed'
                for lang,loc in locs.items():assert loc.get(c['heritage_group'])
            if c.get('reviewed_language'):
                reviewed = c['reviewed_language']
                assert reviewed['sources'] and reviewed['basis']
                assert actual['language'] == reviewed['trait']
                assert c['language_group'] == reviewed['group']
                validate_source_language(c,source_languages)
                for lang,loc in locs.items():
                    assert loc[actual['language']] == reviewed['labels'][lang]
                    if 'group_labels' in reviewed:assert loc[c['language_group']] == reviewed['group_labels'][lang]
            elif c.get('aggregate_language'):
                assert actual['language']=='eu5_aggregate_language_'+c['source']
                assert c['language_group']=='eu5_aggregate_language_group_'+c['source']
                assert len(c['aggregate_members'])>1 and c['source'] in c['aggregate_members']
                for lang,loc in locs.items():assert loc.get(c['language_group'])
            elif c.get('custom_language'):
                assert actual['language'] == 'eu5_resident_language_'+c['source_language']
                validate_source_language(c,source_languages)
                if c['isolated_language_group']:
                    assert c['language_group'] == 'eu5_resident_language_group_'+c['source_language']
                    for lang,loc in locs.items():assert loc.get(c['language_group'])
            # All inherited template fields must remain disclosed and unchanged.
            for field,value in template.items():
                if field in (None,'color','heritage','language'):continue
                actual_value = actual[field]
                assert (actual_value.text() if hasattr(actual_value,'text') else actual_value) == (value.text() if hasattr(value,'text') else value), ('Unexpected template field change',key,field)
            for lang,loc in locs.items():assert loc[key] == c['labels'][lang]
    entries = []
    for key in sorted(used):
        source_rows = [x for x in crosswalk.values() if x['target_culture'] == key]
        d = cultures[key]
        entries.append({'target':key,'source_cultures':[x['source_culture'] for x in source_rows],
                        'centipersons':sum(int(x['centipersons']) for x in source_rows),
                        'heritage':d['heritage'],'language':d['language'],'default_religion':d['religion'],
                        'names':{lang:locs[lang][key] for lang in locs},'political_custom':key in custom,'resident_custom':key in resident_custom})
    return {'status':'passed','resolved_source_cultures':sum(bool(x['target_culture']) for x in crosswalk.values()),
            'used_target_cultures':len(used),'political_custom_cultures_checked':len(custom),
            'used_political_custom_cultures':len(used & custom.keys()),
            'resident_custom_cultures_checked':len(resident_custom),
            'definition_trait_group_religion_name_lists_localization_validated':True,
            'entries':entries,'inputs_sha256':inputs,
            'limitations':['Static reference and nonempty name-list validation only; does not certify historical names, cultural mapping policy, portraits, homelands or game loading.',
                           'Culture default religion is validated as an asset reference only; resident religions remain explicitly sourced from population records.']}
