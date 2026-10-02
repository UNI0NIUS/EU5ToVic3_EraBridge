"""Geographic candidates and runtime-priced, side-wide war-goal budgets."""
from collections import Counter,defaultdict
from decimal import Decimal
import re
from extract_m3_politics import fields,sequence
from economy_model import definitions
from economy_market import land_edges
from pdx_text import root

VALUES='common/script_values/zz_eu5_war_budget.txt'


def candidates(rows,owned,homelands,cultures,claims,edges,budget):
    flat={p:(s,t) for s,ps in owned.items() for p,t in ps.items()}
    holdings=Counter((s,t) for s,ps in owned.items() for t in ps.values())
    borders=defaultdict(set)
    for a,b in edges:
        if a not in flat or b not in flat:continue
        for a,b in ((a,b),(b,a)):
            sa,ha=flat[a];sb,hb=flat[b]
            if ha!=hb:borders[ha,sb,hb].add((a,b))
    for row in rows:
        if row['goal'] in ('independence','secession') or row.get('civil_war_bridge'):continue
        row['budget_per_side']=budget;row['candidates']=[]
        for side,holder,enemies,leader in (
                ('attacker',row['attacker'],row['defenders'],row['attacker']),
                ('defender',row['target'],row['attackers'],row['leader_target'])):
            found=[]
            for (state,owner),count in sorted(holdings.items()):
                if owner not in enemies:continue
                border=borders.get((holder,state,owner),set())
                shared=holdings[state,holder]>0 and bool(border)
                homeland=bool(homelands.get(state,set()) & cultures.get(holder,set()))
                if not shared and not (side=='defender' and homeland):continue
                evidence='shared_border' if shared else 'border_homeland' if border else 'homeland'
                item={'side':side,'holder':holder,'target':owner,'state':state,
                      'type':'return_state' if holder in claims.get(state,set()) else 'conquer_state',
                      'budget_holder':leader,'reason':evidence,'homeland':homeland,
                      'border_edges':[list(p) for p in sorted(border)],
                      'own_provinces_in_state':holdings[state,holder],'enemy_provinces_in_state':count}
                # Original objective first if it meets the new rule. Then consolidate
                # split states before reaching for unsplit cultural homelands.
                item['priority']=[0 if shared and row.get('state')==state else
                                  1 if shared else 2 if border else 3,
                                  -holdings[state,holder],state,owner]
                found.append(item)
            row['candidates'].extend(sorted(found,key=lambda c:c['priority']))
        for i,item in enumerate(row['candidates']):
            item['key']=f"eu5_w_{row['id']}_{i}"
            item['remaining_key']=f"eu5_w_{row['id']}_{item['side']}_remaining"


def load_candidates(rows,base,game,cache,claims,budget):
    from build_m2_prototype import state_owners
    state_root=fields(root((base/'common/history/states/00_eu5_world.txt').read_text(encoding='utf-8-sig')))['STATES']
    owned={k[2:]:state_owners(obj) for k,obj in state_root.entries()}
    homelands={k[2:]:{v.removeprefix('cu:') for op,v in obj.entries() if op=='add_homeland'} for k,obj in state_root.entries()}
    defs=definitions(base/'common/country_definitions')
    cultures={k:set(sequence(v.get('cultures'))) for k,v in defs.items()}
    edges,_=land_edges(game,cache,owned)
    candidates(rows,owned,homelands,cultures,claims,edges,budget)


def price_scripts(game):
    from opening_wars import effect_block
    scripts=[]
    for goal,filename in [('conquer_state','03_conquer_state.txt'),('return_state','21_return_state.txt')]:
        body=fields(fields(root((game/'common/war_goal_types'/filename).read_text(encoding='utf-8-sig')))[goal])['infamy'].text()
        # Explicit holder avoids depending on the history file's initial ROOT.
        body=re.sub(r'\broot\b','scope:eu5_goal_holder',body)
        scripts.append(effect_block('eu5_native_'+goal+'_infamy',body.strip()))
        scripts.append(effect_block('eu5_budget_'+goal,
            'value = eu5_native_'+goal+'_infamy\n'
            'multiply = eu5_budget_aggressor_rank\n'
            'multiply = eu5_budget_target_rank\n'
            'multiply = { value = 1 add = modifier:country_infamy_generation_mult min = 1 }\n'
            'multiply = 1.01'))
    ranks=definitions(game/'common/country_ranks')
    for who,key in [('aggressor','infamy_aggressor_scaling'),('target','infamy_target_scaling')]:
        body='value = 1\n'
        for name,data in sorted(ranks.items()):
            # Ignore national-rank discounts; multiplying positive contributions
            # also bounds an additive combination. Never underprice to fit a goal.
            extra=max(Decimal(0),Decimal(data.get(key,'0')))
            if not extra:continue
            condition='country_rank = rank_value:'+name
            if who=='target':condition='scope:target_country = { '+condition+' }'
            body+='if = { limit = { '+condition+' } add = '+str(extra)+' }\n'
        scripts.append(effect_block('eu5_budget_'+who+'_rank',body))
    return '\n'.join(scripts)


def allocation_script(row):
    from opening_wars import effect_block,remove_seed_goal,initial_war_goals
    body='save_scope_as = diplomatic_play\n'
    primary=f"eu5_w_{row['id']}_primary"
    body+=f'c:{row["attacker"]} = {{ set_variable = {{ name = {primary} value = 0 }} }}\n'
    for side,holder in [('attacker',row['attacker']),('defender',row['leader_target'])]:
        key=f"eu5_w_{row['id']}_{side}_remaining"
        body+=f'c:{holder} = {{ set_variable = {{ name = {key} value = {row["budget_per_side"]} }} }}\n'
    # Remove native seed and default defence goals only after set_war (engine safety).
    for who,goal in (row.get('initial_war_goals') or initial_war_goals(row)).items():
        body+=remove_seed_goal(row,who,goal)
    for c in row['candidates']:
        holder,target,state,key=c['holder'],c['target'],c['state'],c['key'];remaining=c['remaining_key']
        body+=f'c:{holder} = {{ save_scope_as = eu5_goal_holder }}\n'
        body+=f'c:{target} = {{ save_scope_as = target_country }}\n'
        body+=f's:{state}.region_state:{target} = {{ save_scope_as = target_state region = {{ save_scope_as = target_region }} }}\n'
        body+=f'c:{holder} = {{ set_variable = {{ name = eu5_goal_price value = eu5_budget_{c["type"]} }} }}\n'
        selection=f'set_variable = {{ name = {key}_price value = scope:eu5_goal_holder.var:eu5_goal_price }}\n'
        add='add_war_goal = { holder = c:'+holder+' type = '+c['type']+' target_country = c:'+target+' target_state = s:'+state+'.region_state:'+target
        goal_effect=effect_block('scope:diplomatic_play',
            effect_block('if',f'limit = {{ c:{row["attacker"]} = {{ var:{primary} = 0 }} }}\n'+add+' primary_demand = yes }\n'+
                         f'c:{row["attacker"]} = {{ set_variable = {{ name = {primary} value = 1 }} }}\n')+
            effect_block('else',add+' primary_demand = no }'))
        selection+=effect_block('if',
            f'limit = {{ var:{key}_price > 0 var:{remaining} >= var:{key}_price }}\n'
            f'change_variable = {{ name = {remaining} subtract = var:{key}_price }}\n'
            f'set_variable = {{ name = {key}_selected value = 1 }}\n'+
            goal_effect)
        body+=effect_block('c:'+c['budget_holder'],selection)
    return body
