"""Nonzero pre-industrial command capacity without granting modern technology."""
from pathlib import Path
from pdx_text import root, Object
from build_m2_prototype import patch,replace_body
from build_m3_world import block
from v3_startup_validation import effective_objects

EFFECT='eu5_sync_command_capacity'
MODIFIERS={role:'eu5_early_'+role+'_command_capacity' for role in ('general','admiral')}
ON_ACTIONS='common/on_actions/00_code_on_actions.txt'
SCRIPT='common/scripted_effects/zz_eu5_command_capacity.txt'
STATIC='common/static_modifiers/zz_eu5_command_capacity.txt'


def render(game,mod):
    game,mod=Path(game),Path(mod)
    technologies=effective_objects(game,mod,'common/technology/technologies')
    floors={}
    for role in MODIFIERS:
        key='country_'+role+'_rank_impact_mult'
        amounts=[sum(float(value) for field,obj in o.entries() if field=='modifier' and isinstance(obj,Object)
                     for name,value in obj.entries() if name==key) for o in technologies.values()]
        positive=[v for v in amounts if v>0]
        if not positive:raise ValueError('无法找到指挥倍率科技基准：'+key)
        floors[role]=min(positive)
    effects=[];modifiers=[]
    for role,name in MODIFIERS.items():
        key='country_'+role+'_rank_impact_mult'
        modifiers.append(block(name,f'{key} = {floors[role]:g}'))
        # Remove our own contribution before evaluating the native value. This is
        # idempotent and automatically retires the fallback after any real bonus.
        effects.append(block('if',block('limit','has_modifier = '+name)+'remove_modifier = '+name))
        effects.append(block('if',block('limit',f'modifier:{key} <= 0')+block('add_modifier','name = '+name)))
    source=mod/ON_ACTIONS
    text=(source if source.exists() else game/ON_ACTIONS).read_text(encoding='utf-8-sig')
    actions=root(text).fields();edits=[]
    for action in ('on_game_started','on_monthly_pulse_country','on_acquired_technology'):
        if action not in actions:raise ValueError('缺少指挥倍率更新入口：'+action)
        obj=actions[action];effect=obj.fields().get('effect')
        if EFFECT in obj.text():continue
        invoke=block('every_country',EFFECT+' = yes') if action=='on_game_started' else EFFECT+' = yes\n'
        if effect is not None:edits.append(replace_body(effect,effect.text()+'\n'+invoke))
        else:edits.append(replace_body(obj,obj.text()+'\n'+block('effect',invoke)))
    files={ON_ACTIONS:patch(text,edits),SCRIPT:block(EFFECT,''.join(effects)),STATIC:''.join(modifiers)}
    labels={'simp_chinese':('基础陆军指挥体系','基础海军指挥体系'),
            'english':('Early Army Command','Early Naval Command')}
    for lang,names in labels.items():
        files[f'localization/{lang}/eu5_command_capacity_l_{lang}.yml']='l_'+lang+':\n'+''.join(
            f' {MODIFIERS[role]}:0 "{name}"\n' for role,name in zip(MODIFIERS,names))
    return files,dict(policy='fallback_only_when_native_rank_impact_nonpositive',floors=floors,
                      existing_save_update='next monthly country pulse',technology_grants=[])


def install(game,mod):
    files,report=render(game,mod)
    for rel,text in files.items():
        path=Path(mod)/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8-sig')
    return report
