"""Load actual V3 candidate files and calculate map-linked opening scenarios."""
from converter_i18n import Message, diagnostic
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
from PIL import Image
from converter_project import read, digest, settings, apportion, resolve_merges, assess, summarize
from pdx_text import root, Object
from build_m2_prototype import objects, strings, state_owners
from build_m3_world import load_localization
from economy_model import Target, definitions, building_rows, apportioned
from package_m4_population_test import parse_pops
from m3_uncolonized import province_land_edges

POPS = 'common/history/pops/00_eu5_world.txt'
STATES = 'common/history/states/00_eu5_world.txt'
BUILDINGS = 'common/history/buildings/00_eu5_world.txt'

def opening_laws(obj, target, country, prior=()):
    laws={target._law_definitions[k]['group']:k for k in prior}
    def condition(o):
        tests=[]
        for k,v in o.entries():
            if k in ('NOR','NOT'):tests.append(not any(condition_terms(v)))
            elif k=='OR':tests.append(any(condition_terms(v)))
            elif k=='AND':tests.append(all(condition_terms(v)))
            elif k=='has_law_or_variant':tests.append(v.split(':')[-1] in laws.values())
            elif k=='country_is_islamic':tests.append((country.get('religion') in ('sunni','shiite'))==(v=='yes'))
            elif k=='is_country_type':tests.append(country.get('country_type')==v)
            else:raise ValueError(Message('不能解析法律条件：{0}', str(k)))
        return all(tests)
    def condition_terms(o):
        for k,v in o.entries():yield condition(root(entry_local(k,v)))
    def process(o):
        last=None
        for k,v in o.entries():
            if k=='activate_law':
                law=v.split(':')[-1];laws[target._law_definitions[law]['group']]=law
            elif k in target._law_effects:process(target._law_effects[k])
            elif k=='if':
                last=condition(dict(v.entries())['limit'])
                if last:process(v)
            elif k=='else' and last is False:process(v)
    from build_m3_world import entry as entry_local
    process(obj)
    return set(laws.values())

class Candidate:
    def __init__(self, package, game, cache):
        self.package, self.game, self.cache = Path(package).resolve(), Path(game).resolve(), Path(cache)
        self.report = read(self.package/'package_report.json')
        declared = Path(self.report['mod_directory'])
        self.mod = declared if declared.is_absolute() else self.package/declared
        # Support relocating a package as one directory.
        if not self.mod.is_dir(): self.mod = self.package/declared.name
        if not self.mod.is_dir(): raise ValueError(Message('找不到模组目录：{0}', str(self.mod)))
        self.input_hashes = {p.relative_to(self.mod).as_posix():digest(p) for p in self.mod.rglob('*') if p.is_file()}
        for rel, sha in self.report.get('output_sha256', {}).items():
            if self.input_hashes.get(rel) != sha: raise ValueError(Message('候选包已改变，需重新生成清单：{0}', rel))
        self.target = Target(self.game)
        for key, folder in [('states','map_data/state_regions'),('buildings','common/buildings'),('pms','common/production_methods'),('groups','common/production_method_groups'),('techs','common/technology/technologies')]:
            getattr(self.target,key).update(definitions(self.mod/folder))
        self.labels = load_localization(self.game/'localization/simp_chinese')
        self.labels.update(load_localization(self.mod/'localization/simp_chinese'))
        self.labels.update(load_localization(self.mod/'localization/replace/simp_chinese'))
        strategic=definitions(self.game/'common/strategic_regions')
        strategic.update(definitions(self.mod/'common/strategic_regions'))
        self.strategic_regions={s:k for k,f in strategic.items() if 'states' in f for s in strings(f['states'])}
        self.owners = {}
        self.state_objects = dict(objects(root((self.mod/STATES).read_text(encoding='utf-8-sig')).fields()['STATES']))
        for s, obj in self.state_objects.items():
            self.owners[s[2:]] = {p[0]+p[1:].upper(): t for p,t in state_owners(obj).items()}
        self.parts = {}
        for s, ps in self.owners.items():
            for t in sorted(set(ps.values())):
                self.parts[s+'|'+t] = dict(state=s, country=t, provinces=sorted(p for p in ps if ps[p]==t))
        self.population = Counter(parse_pops(self.mod/POPS))
        self.buildings = building_rows(self.mod/BUILDINGS)
        self.techs, self.laws = {}, {}
        from build_economy import expand_template_tech
        from complete_economy import active_laws
        self.target._law_definitions = definitions(self.game/'common/laws')
        self.target._law_definitions.update(definitions(self.mod/'common/laws'))
        self.target._law_effects = dict(objects(root((self.game/'common/scripted_effects/00_political_setup.txt').read_text(encoding='utf-8-sig'))))
        effects = dict(objects(root((self.game/'common/scripted_effects/00_starting_inventions.txt').read_text(encoding='utf-8-sig'))))
        self.country_objects = {}
        country_defs=definitions(self.game/'common/country_definitions')
        country_defs.update(definitions(self.mod/'common/country_definitions'))
        political_path=Path(self.report.get('political_run',self.package/'political'))/'conversion_report.json'
        political=read(political_path).get('countries',{}) if political_path.exists() else self.report.get('countries',{})
        for path in sorted((self.mod/'common/history/countries').glob('*.txt')):
            for _, container in objects(root(path.read_text(encoding='utf-8-sig'))):
                for k, obj in objects(container):
                    self.country_objects[k[2:]] = obj
                    self.techs.setdefault(k[2:],set()).update(expand_template_tech(obj,effects,self.target))
                    country=dict(country_defs.get(k[2:],{}),**political.get(k[2:],{}))
                    country.setdefault('religion',country.get('religion_type'))
                    self.laws[k[2:]] = opening_laws(obj,self.target,country,self.laws.get(k[2:],()))
        self.target.global_technologies = set().union(*self.techs.values())
        self.countries=political or {t:{k:v for k,v in c.items() if isinstance(v,(str,int,float,bool))} for t,c in country_defs.items()}
        self.buy_packages = definitions(self.game/'common/buy_packages')
        self.cache.mkdir(parents=True,exist_ok=True)
        province_state = {p:s for s,ps in self.owners.items() for p in ps}
        self.edges = province_land_edges(SimpleNamespace(game=self.game,owners=self.owners,province_state=province_state),self.cache/'land_edges.json')
        transport=read(self.cache/'land_edges.json')
        self.transport_edges=[('x'+a[1:].upper(),'x'+b[1:].upper()) for a,b in transport['edges']]
        self.coastal_provinces={'x'+p[1:].upper() for p in transport.get('coastal_provinces',[])}
        self.map_path = self.game/'map_data/provinces.png'
        self.map_hash = digest(self.map_path)
        self.fingerprint = digest(self.package/'package_report.json') + ':' + self.map_hash
        self.arable_kinds = set()
        for kind, row in self.target.buildings.items():
            g = row.get('building_group'); seen=set()
            while g and g not in seen:
                seen.add(g); f=self.target.building_groups[g]
                if f.get('land_usage') == 'rural': self.arable_kinds.add(kind); break
                g=f.get('parent_group')
        self.coefficients = {}
        for i, row in enumerate(self.buildings):
            try:
                defaults=self.target.select(row['building'],self.techs[row['owner']],set(),self.laws[row['owner']])
                pms=self.target.complete_methods(row['building'],row['pms'],defaults)
                self.coefficients[i]=self.target.coefficients(row['building'],pms,self.techs[row['owner']])
            except (ValueError,KeyError): self.coefficients[i]=None
        self._raster = None

    def raster(self):
        if self._raster is None:
            a=np.asarray(Image.open(self.map_path).convert('RGB'),dtype=np.uint32)
            self._raster=(a[:,:,0]<<16)|(a[:,:,1]<<8)|a[:,:,2]
        return self._raster

    def preview(self, options, operations):
        import json
        key=json.dumps([options,operations],sort_keys=True)
        cache=getattr(self,'_preview_cache',None)
        if cache is None:self._preview_cache=cache={}
        if key in cache:return cache[key]
        result=self._calculate_preview(options,operations)
        if len(cache)>=4:cache.pop(next(iter(cache)))
        cache[key]=result
        return result

    def _calculate_preview(self, options, operations):
        if operations:
            from converter_edits import materialize
            from converter_reconcile import reconcile
            view=materialize(self,operations)
            view._political_reconciliation=reconcile(self,view)
            result=dict(view.preview(options,[]))
            _,political_notes=view._political_reconciliation
            result.update(merges=operations,aliases=view._edit_aliases,adjustments=view._edit_notes+political_notes,bulk_outcomes=view._bulk_outcomes)
            result['assumptions']=result['assumptions']+[Message('地块拆分按地块数量比例分配现有人口与建筑，整数采用最大余数法；这不是地块级历史人口数据。')]
            return result
        options=settings(options)
        owners, aliases, transfers, _=resolve_merges(self.parts,operations,self.edges)
        # Preserve global rounded population, with stable group allocation.
        scaled=apportioned({k:n*options['population_multiplier'] for k,n in self.population.items()})
        pops=Counter()
        for (s,t,c,r),n in scaled.items(): pops[s,transfers.get((s,t),t)]+=n
        ps=defaultdict(list)
        province_states={p:row['state'] for row in self.parts.values() for p in row['provinces']}
        for p,t in owners.items(): ps[province_states[p],t].append(p)
        counts=defaultdict(Counter)
        for (s,t),pr in ps.items(): counts[s][t]=len(pr)
        land={}
        for s, weights in counts.items():
            n=int(math.floor(int(self.target.states[s].get('arable_land',0))*options['arable_multiplier']+.5))
            land.update({(s,t):v for t,v in apportion(n,weights).items()})
        formal=Counter(); farms=Counter(); balance=defaultdict(Counter); unknown=set();building_levels=defaultdict(Counter)
        for i,b in enumerate(self.buildings):
            pair=b['state'],transfers.get((b['state'],b['owner']),b['owner'])
            building_levels[pair][b['building']]+=b['levels']
            c=self.coefficients[i]
            if pair[1]!=b['owner']:
                try:
                    defaults=self.target.select(b['building'],self.techs[pair[1]],set(),self.laws[pair[1]])
                    methods=self.target.complete_methods(b['building'],b['pms'],defaults)
                    c=self.target.coefficients(b['building'],methods,self.techs[pair[1]])
                except (ValueError,KeyError):c=None
            if b['guards'] or c is None: unknown.add(pair); continue
            formal[pair]+=c['jobs']*b['levels']
            if b['building'] in self.arable_kinds: farms[pair]+=b['levels']
            staffing=options['staffing']
            for g,n in c['outputs'].items(): balance[pair][g]+=n*b['levels']*staffing
            for g,n in c['inputs'].items(): balance[pair][g]-=n*b['levels']*staffing
        rows=[]
        basket=self.buy_packages['wealth_'+str(options['food_wealth'])]['goods'].fields()
        # Same base-price food budget units as the existing economy planner.
        food_per_person=float(basket.get('popneed_basic_food',basket.get('basic_food',0)))/10000
        if not food_per_person: raise ValueError(Message('游戏食物消费篮子缺失，不能把未知需求显示为零'))
        foods=('grain','fish','meat','fruit','groceries')
        for pair,pr in sorted(ps.items()):
            s,t=pair; population=pops[pair]; workforce=population*options['workforce_share']
            used=min(workforce,formal[pair]*options['staffing'])
            b=self.target.states[s].get('subsistence_building','building_subsistence_farm')
            try:
                methods=self.target.select(b,self.techs[t],set(),self.laws[t])
                c=self.target.coefficients(b,methods,self.techs[t])
                available=max(0,land[pair]-farms[pair]); subjobs=c['jobs']*available
                occupied=min(max(0,workforce-used),subjobs)
                active=occupied/c['jobs'] if c['jobs'] else 0
                for g,n in c['outputs'].items(): balance[pair][g]+=n*active
                for g,n in c['inputs'].items(): balance[pair][g]-=n*active
            except (ValueError,KeyError): subjobs=0; occupied=0; unknown.add(pair)
            supply=sum(max(0,balance[pair][g])*self.target.prices[g] for g in foods)
            # Match existing planner: peasants' in-kind food covers 95% of their basket.
            # Unemployed households retain full demand. Subsistence goods are the saleable remainder.
            household_factor=(options['workforce_share']+(1-options['workforce_share'])*.5)/options['workforce_share']
            demand=(max(0,workforce-occupied)+occupied*.05)*household_factor*food_per_person
            row=dict(id=s+'|'+t,state=s,country=t,state_name=self.labels.get(s,s),country_name=self.labels.get(t,t),
                     strategic_region=self.strategic_regions.get(s),strategic_region_name=self.labels.get(self.strategic_regions.get(s),self.strategic_regions.get(s,Message('未知战略地区'))),
                     population=population,arable=land[pair],province_count=len(pr),provinces=sorted(pr),
                     state_arable=int(self.target.states[s].get('arable_land',0)),
                     buildings=dict(building_levels[pair]),
                     formal_jobs=formal[pair],subsistence_jobs=subjobs,
                     job_capacity=None if pair in unknown else formal[pair]*options['staffing']+subjobs,
                     food_supply=None if pair in unknown else supply,food_demand=demand,
                     food_net={g:balance[pair][g]*self.target.prices[g] for g in foods},
                     overbuilt_arable=max(0,farms[pair]-land[pair]))
            rows.append(assess(row,options))
        country_food=defaultdict(lambda:dict(supply=0,demand=0,unknown=False))
        for row in rows:
            c=country_food[row['country']];c['demand']+=row['food_demand']
            if row['food_supply'] is None:c['unknown']=True
            else:c['supply']+=row['food_supply']
        for row in rows:
            c=country_food[row['country']]
            row['country_food_shortfall']=None if c['unknown'] else max(0,1-c['supply']/c['demand']) if c['demand'] else 0
        neighbors=defaultdict(set)
        for a,b in self.edges:
            if a not in owners or b not in owners:continue
            x=province_states[a]+'|'+owners[a];y=province_states[b]+'|'+owners[b]
            if x!=y:neighbors[x].add(y);neighbors[y].add(x)
        for row in rows:row['neighbors']=sorted(neighbors[row['id']])
        from converter_food_markets import apply as market_food
        markets=market_food(self,rows,options)
        from converter_arable_advice import calculate as arable_advice
        state_rows=defaultdict(list)
        for row in rows:state_rows[row['state']].append(row)
        for row in rows:
            if 'unemployment' in row['risks']:
                try:row['arable_advice']=arable_advice(self,options,row,state_rows[row['state']])
                except (ValueError,KeyError) as e:row['arable_advice_error']=diagnostic(e)
        return dict(rows=rows,summary=summarize(rows),settings=options,merges=operations,
                    markets=markets,
                    aliases=aliases,source_date=self.report.get('source_date',Message('未知')),fingerprint=self.fingerprint,
                    assumptions=[Message('耕地按地块比例以最大余数法分配，实际引擎分配需入游戏核对。'),
                    Message('失业为岗位容量缺口估算；未模拟资质、工资、价格和实际招聘。'),
                    Message('食物按附属关系、独立市场协议及国家集团实际关税同盟原则汇总；普通集团、贸易与防御条约不会自动成为同一市场。'),
                    Message('食物风险使用预计市场接入后的缺口；陆路、两端有效港口及基础设施容量决定接入估算。未模拟舰船吨位、封锁、市场外贸易、价格或实际饥荒事件。'),
                    Message('本地净产能含自给农业并扣除工业原料；自给农民95%口粮视为实物自给。未知产能或市场接入显示未知，不据此自动合并。'),
                    Message('合并不会创造耕地、岗位或粮食，跨州的岗位不能自动解决本地失业。')])

    def verify_unchanged(self):
        current={p.relative_to(self.mod).as_posix():digest(p) for p in self.mod.rglob('*') if p.is_file()}
        if current!=self.input_hashes or digest(self.map_path)!=self.map_hash:raise ValueError(Message('输入在编辑期间发生变化，请重新载入'))
