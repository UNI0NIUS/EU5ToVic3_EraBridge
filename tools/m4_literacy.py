"""Population-weighted literacy at the existing state/owner/culture/religion grain."""
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
import csv,json
from pathlib import Path
from build_m2_prototype import objects,patch,replace_body
from build_m3_world import block,entry
from m3_world import load_json,digest,fields
from pdx_text import root
from extract_m4_literacy import OUT,SOURCE,SCALE

FRACTION_DENOMINATOR=100*SCALE
EFFECT_PATH='common/scripted_effects/zz_eu5_m4_literacy.txt'
HOOK_PATH='common/on_actions/zz_eu5_m4_literacy.txt'
CODE_PATH='common/on_actions/00_code_on_actions.txt'
POPULATION_PATH='common/history/population/00_eu5_world.txt'
HOOK='eu5_m4_literacy_after_setup'
FLAG='eu5_m4_literacy_imported'

def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)

def decimal_rate(numerator,centipersons):
    if centipersons<=0 or not 0<=numerator<=centipersons*FRACTION_DENOMINATOR:raise ValueError('Invalid literacy weight')
    # The engine rejected the old nine-decimal literals (Badly read script value).
    # Keep the source ledger exact; only quantize the engine-facing fraction.
    return format((Decimal(numerator)/Decimal(centipersons*FRACTION_DENOMINATOR)).quantize(Decimal('0.00001'),rounding=ROUND_HALF_UP),'f')

def build(package,demographic,mod,game,OUT=OUT,SOURCE=SOURCE):
    source_report=load_json(OUT/'source_literacy_report.json')
    if digest(OUT/'source_literacy.csv')!=source_report['ledger_sha256']:raise ValueError('Literacy extraction changed')
    d=load_json(demographic/'demographics/demographics_report.json')
    if source_report['source_sha256']!=d['source_sha256']:raise ValueError('Literacy belongs to a different campaign')
    source={r['pop_id']:r for r in rows(OUT/'source_literacy.csv')}
    culture={r['source_culture']:r['target_culture'] for r in rows(demographic/'demographics/resident_culture_crosswalk.csv')}
    religion={r['source_religion']:r['target_religion'] for r in rows(demographic/'demographics/resident_religion_crosswalk.csv')}
    migrant={(m['source'],s):m['target'] for m in d['migrant_cultures']['cultures'] for s in m['states']}
    population=Counter();weighted=Counter();allocated=Counter()
    for r in rows(demographic/'staging/province_population_draft.csv'):
        n=int(r['centipersons']);pid=r['source_pop_id'];allocated[pid]+=n
        c=migrant.get((r['source_culture'],r['target_state']),culture[r['source_culture']])
        key=r['target_state'],r['target_owner'],c,religion[r['source_religion']]
        population[key]+=n;weighted[key]+=n*int(source[pid]['literacy_micro_percent'])
    if any(allocated[pid]!=int(r['centipersons']) for pid,r in source.items()):raise ValueError('Not every source literacy weight was allocated')
    if sum(weighted.values())!=source_report['weighted_literacy_numerator']:raise ValueError('Global literacy numerator changed')
    groups={tuple(r[k] for k in ('state','owner','culture','religion')):r for r in rows(demographic/'demographics/resident_population_groups.csv')}
    if population!={k:int(r['centipersons']) for k,r in groups.items()}:raise ValueError('Literacy group population differs')
    out=package/'literacy';out.mkdir()
    by_country=defaultdict(lambda:defaultdict(list));country_n=Counter();country_w=Counter();records=[]
    for k,n in sorted(population.items()):
        state,owner,c,r=k;rate=decimal_rate(weighted[k],n);integer=int(groups[k]['preview_integer_persons'])
        records.append([*k,n,weighted[k],rate,integer])
        country_n[owner]+=n;country_w[owner]+=weighted[k]
        if integer:
            by_country[owner][state].append(block('every_scope_pop',block('limit',f'culture = cu:{c}\nreligion = rel:{r}')+block('set_pop_literacy',block('literacy_rate','value = '+rate))))
    with (out/'literacy_groups.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['state','owner','culture','religion','centipersons','weighted_micro_percent','literacy_fraction','integer_persons']);w.writerows(records)
    effects={}
    for owner,states in sorted(by_country.items()):
        effects['eu5_m4_literacy_'+owner]=''.join(block('every_scope_state',block('limit','state_region = s:'+state)+''.join(parts)) for state,parts in sorted(states.items()))
    (mod/EFFECT_PATH).write_text('# EU5 source-weighted literacy. Applied during history and once after bookmark setup.\n'+''.join(block(k,v) for k,v in effects.items()),encoding='utf-8-sig')
    # Native literacy also mutates by profession/incorporation. Keep it only for
    # countries containing explicit source-empty template populations; their
    # source-origin groups are overridden by the exact selectors afterwards.
    template_owners={r['owner'] for r in rows(demographic/'template_fallback/template_population_groups.csv')}
    original_population=(mod/POPULATION_PATH).read_text(encoding='utf-8-sig')
    countries=[]
    for scope,obj in objects(root(original_population).fields()['POPULATION']):
        owner=scope[2:].strip(' ?')
        body=''.join(entry(k,v) for k,v in obj.entries() if not (k and k.startswith('effect_starting_pop_literacy_') and owner not in template_owners))
        if owner in by_country:body+='eu5_m4_literacy_'+owner+' = yes\n'
        countries.append(block(scope,body))
    (mod/POPULATION_PATH).write_text(block('POPULATION',''.join(countries)),encoding='utf-8-sig')
    # Native 1.13.11 documents this hook as after bookmark initialization, before
    # the lobby. It is not a daily/monthly pulse and does not fire on save reload.
    original_code=(mod/CODE_PATH).read_text(encoding='utf-8-sig')
    start=root(original_code).fields()['on_game_started'];hooks=start.fields().get('on_actions')
    if hooks:
        changes=[replace_body(hooks,hooks.text()+'\n'+HOOK+'\n')]
    else:changes=[replace_body(start,start.text()+'\non_actions = { '+HOOK+' }\n')]
    (mod/CODE_PATH).write_text(patch(original_code,changes),encoding='utf-8-sig')
    hooks_body=''.join(block('c:'+owner+' ?',block('if',block('limit',block('NOT','has_variable = '+FLAG))+'eu5_m4_literacy_'+owner+' = yes\nset_variable = '+FLAG)) for owner in sorted(by_country))
    (mod/HOOK_PATH).write_text(block(HOOK,block('effect',hooks_body)),encoding='utf-8-sig')
    with (out/'country_literacy.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['owner','source_origin_persons','weighted_source_literacy_percent','template_people_not_assigned_source_literacy'])
        for owner in sorted(country_n):w.writerow([owner,str(Decimal(country_n[owner])/100),str(Decimal(country_w[owner])/Decimal(country_n[owner]*SCALE)),owner in template_owners])
    inputs=[OUT/'source_literacy_report.json',OUT/'source_literacy.csv',SOURCE/'source_populations.csv',
        demographic/'staging/province_population_draft.csv',demographic/'demographics/resident_population_groups.csv',
        demographic/'demographics/resident_culture_crosswalk.csv',demographic/'demographics/resident_religion_crosswalk.csv',
        game/'common/scripted_effects/00_starting_pop_literacy.txt',game/'common/on_actions/00_code_on_actions.txt',
        game/'events/boxer_rebellion_events.txt',game/'events/balkans_events/balkan_wars_events.txt']
    result={'status':'source_weighted_literacy_candidate','source_sha256':source_report['source_sha256'],
        'source_literacy_directory':str(OUT),'demographic_run':str(demographic),'world_literacy_percent':source_report['world_literacy_percent'],
        'weighted_literacy_numerator':sum(weighted.values()),'world_centipersons':sum(population.values()),
        'source_population_objects':len(source),'source_groups':len(population),'emitted_groups':sum(int(r[-1])>0 for r in records),
        'target_ITA_literacy_percent':str(Decimal(country_w['ITA'])/Decimal(country_n['ITA']*SCALE)) if country_n['ITA'] else None,
        'template_policy':'Keep native template literacy only for template-origin residents; do not fabricate EU5 literacy for them.',
        'application':'POPULATION history plus once at on_game_started after bookmark setup; country one-time guard; no ongoing reset.',
        'rate_precision':5,'script_value_form':'literacy_rate = { value = <five-decimal fraction> }','semantic_limit':'EU5 population-weighted rate is used as the initial V3 workforce literacy fraction. Age/workforce composition and occupations are not converted.',
        'runtime_verified':False,'input_sha256':{str(p):digest(p) for p in inputs},
        'output_sha256':{p.name:digest(p) for p in out.glob('*.csv')},
        'mod_files':{rel:digest(mod/rel) for rel in (EFFECT_PATH,HOOK_PATH,CODE_PATH,POPULATION_PATH)}}
    (out/'literacy_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
