"""Deterministic British-calibrated economic candidate for the personal campaign.

Gross output at base prices is a capacity measure, never a GDP forecast. Runtime
prices, trade, wages, qualifications and hiring require a separate game test.
"""
from collections import Counter, defaultdict
import math
from pathlib import Path
import re
from pdx_text import Object, root
from extract_m3_politics import fields, sequence


class LawDefinitions(dict):
    """Economic readers may resolve our exact-modifier variant via its native base.

    This does not add it to keys()/membership: exporters must still load or write
    the real mod definition before selecting it as a deployable law.
    """
    def __missing__(self,key):
        if key=='law_eu5_bakufu' and 'law_bakufu' in self:
            return self['law_bakufu']
        raise KeyError(key)

def definitions(directory):
    result = LawDefinitions() if Path(directory).name=='laws' else {}
    for path in sorted(Path(directory).glob('*.txt')):
        for key, obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if key and isinstance(obj, Object):
                if key in result:
                    raise ValueError('Duplicate definition: '+key)
                result[key] = fields(obj)
    return result


def closure(seeds, technologies):
    result, active = set(), set()
    def visit(key):
        if key in active:
            raise ValueError('Technology prerequisite cycle: '+key)
        if key in result:
            return
        if key not in technologies:
            raise ValueError('Undefined technology: '+key)
        active.add(key)
        for parent in sequence(technologies[key].get('unlocking_technologies')):
            visit(parent)
        active.remove(key)
        result.add(key)
    for key in sorted(seeds):
        visit(key)
    return result


def map_technology(country, rules, technologies):
    advances, institutions = set(country['advances']), set(country['institutions'])
    reasons = {}
    for rule in rules:
        if 'advances_all' in rule and not set(rule['advances_all']) <= advances:
            continue
        if 'advances_any' in rule and not advances.intersection(rule['advances_any']):
            continue
        if 'institutions_any' in rule and not institutions.intersection(rule['institutions_any']):
            continue
        reasons[rule['target']] = rule['reason']
    researched = closure(reasons, technologies)
    return researched, {'direct': reasons, 'prerequisites': sorted(researched - reasons.keys()),
                        'by_category': {category: sorted(t for t in researched if technologies[t]['category'] == category)
                                        for category in ('production', 'military', 'society')}}


def apportioned(weights, total=None):
    """Deterministic largest remainder, no per-state minimum that creates capacity."""
    if any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Invalid allocation weight')
    if not weights or not sum(weights.values()):
        return {k: 0 for k in weights}
    if total is None:
        total = math.floor(sum(weights.values()) + 0.5)
    scaled = {k: v * total / sum(weights.values()) for k, v in weights.items()}
    result = {k: math.floor(v) for k, v in scaled.items()}
    for key in sorted(scaled, key=lambda k: (-(scaled[k]-result[k]), k))[:total-sum(result.values())]:
        result[key] += 1
    return result


class Target:
    def __init__(self, game):
        self.game = Path(game)
        self.buildings = definitions(self.game/'common/buildings')
        self.pms = definitions(self.game/'common/production_methods')
        self.groups = definitions(self.game/'common/production_method_groups')
        self.techs = definitions(self.game/'common/technology/technologies')
        self.goods = definitions(self.game/'common/goods')
        self.states = definitions(self.game/'map_data/state_regions')
        self.building_groups = definitions(self.game/'common/building_groups')
        self.traits = definitions(self.game/'common/state_traits')
        self.base_modifiers = definitions(self.game/'common/static_modifiers')['base_values']
        define_text = (self.game/'common/defines/00_defines.txt').read_text(encoding='utf-8-sig')
        self.infrastructure_population_unit = int(re.search(r'INDIVIDUALS_PER_POP_INFRASTRUCTURE\s*=\s*(\d+)', define_text)[1])
        self.prices = {k: float(v['cost']) for k, v in self.goods.items()}
        self.aliases = {a: k for k, f in self.buildings.items() for a in sequence(f.get('aliases'))}

    def infrastructure_usage(self, kind):
        group = self.buildings[kind]['building_group']
        seen = set()
        while group:
            if group in seen: raise ValueError('Building group cycle')
            seen.add(group); f = self.building_groups[group]
            if 'infrastructure_usage_per_level' in f: return float(f['infrastructure_usage_per_level'])
            group = f.get('parent_group')
        return 0

    def infrastructure(self, state, population, techs, rows):
        modifiers = Counter({k: float(v) for k, v in self.base_modifiers.items() if k.startswith('state_infrastructure')})
        for tech in sorted(techs):
            for k, v in fields(self.techs[tech].get('modifier')).items():
                if k.startswith('state_infrastructure'): modifiers[k] += float(v)
        for trait in sequence(self.states[state].get('traits')):
            for k, v in fields(self.traits[trait].get('modifier')).items():
                if k.startswith('state_infrastructure'): modifiers[k] += float(v)
        for row in rows:
            for pm in row['pms']:
                for obj in fields(self.pms[pm].get('state_modifiers')).values():
                    for k, v in fields(obj).items():
                        if k.startswith('state_infrastructure'): modifiers[k] += float(v)*row['levels']
        value = modifiers['state_infrastructure_add']+min(modifiers['state_infrastructure_from_population_max_add'],
                    population/self.infrastructure_population_unit*modifiers['state_infrastructure_from_population_add'])
        return value*(1+modifiers['state_infrastructure_mult'])

    def numeric(self, pms):
        result = Counter()
        for pm in pms:
            modifiers = fields(self.pms[pm].get('building_modifiers'))
            for scaling, obj in modifiers.items():
                for key, value in fields(obj).items():
                    if key.startswith(('goods_input_', 'goods_output_', 'building_employment_')) and key.endswith('_add'):
                        if scaling not in ('workforce_scaled', 'level_scaled'):
                            raise ValueError('Unsupported economic PM scaling: '+scaling)
                        result[key] += float(value)
        return result

    def coefficients(self, building, pms, techs):
        values = self.numeric(pms)
        throughput = 1.0
        aliases = [a for a, k in self.aliases.items() if k == building]
        for tech in sorted(techs):
            modifiers = fields(self.techs[tech].get('modifier'))
            for key in [building+'_throughput_add', *(a+'_throughput_add' for a in aliases)]:
                throughput += float(modifiers.get(key, 0))
        outputs = {k[13:-4]: v*throughput for k, v in values.items() if k.startswith('goods_output_') and v > 0}
        inputs = {k[12:-4]: v*throughput for k, v in values.items() if k.startswith('goods_input_') and v > 0}
        jobs = sum(v for k, v in values.items() if k.startswith('building_employment_'))
        gross = sum(self.prices[g]*v for g, v in outputs.items())
        return {'gross': gross, 'jobs': jobs, 'inputs': inputs, 'outputs': outputs,
                'technology_throughput': throughput}

    def available(self, pm, techs, laws=frozenset()):
        f = self.pms[pm]
        if not set(sequence(f.get('unlocking_technologies'))) <= techs:
            return False
        # Conditional law/religion/DLC/bloc PMs require a game-script evaluator.
        unlocking_laws = set(sequence(f.get('unlocking_laws')))
        if (unlocking_laws and not unlocking_laws & laws) or set(sequence(f.get('disallowing_laws'))) & laws:
            return False
        if any(k in f for k in ('is_shown', 'possible', 'allow',
                                'potential', 'unlocking_principles', 'unlocking_religions', 'unlocking_production_methods', 'unlocking_identity')):
            return False
        if sequence(f.get('unlocking_geographic_regions')):
            return False
        if not set(sequence(f.get('unlocking_global_technologies'))) <= getattr(self,'global_technologies',techs):
            return False
        return True

    def select(self, building, techs, british_pms, laws=frozenset()):
        chosen = []
        groups = sequence(self.buildings[building].get('production_method_groups'))
        for group in groups:
            options = [p for p in sequence(self.groups[group]['production_methods']) if self.available(p, techs, laws)]
            if not options:
                raise ValueError('No unconditional unlocked PM: '+building+'/'+group)
            if building == 'building_government_administration' and group == groups[0]:
                # Administration produces a national capacity, not saleable goods.
                # Ranking it by gross goods output (or an overseas British reference)
                # can strand an advanced country on simple organization forever.
                def bureaucracy(pm):
                    return sum(float(fields(o).get('country_bureaucracy_add',0))
                               for o in fields(self.pms[pm].get('country_modifiers')).values())
                chosen.append(max(options,key=lambda p:(bureaucracy(p),p)))
                continue
            # Advance only the main production group to the British reference.
            candidates = [p for p in options if p in british_pms] if group == groups[0] else []
            if candidates:
                pm = max(candidates, key=lambda p: (self.coefficients(building, [p], techs)['gross'], p))
            else:
                pm = options[0]
            chosen.append(pm)
        return chosen

    def complete_methods(self, building, existing, defaults):
        """History may omit default PMs or serialize groups in any order."""
        groups = sequence(self.buildings[building].get('production_method_groups'))
        result, recognized = [], set()
        for i,group in enumerate(groups):
            members = set(sequence(self.groups[group]['production_methods']))
            active = [p for p in existing if p in members]
            if len(active)>1: raise ValueError('Multiple active PMs in '+building+'/'+group)
            result.append(active[0] if active else defaults[i])
            recognized.update(active)
        if set(existing)-recognized: raise ValueError('Foreign PM in '+building)
        return result


def british_baseline(path, target):
    doc = root(Path(path).read_text(encoding='utf-8')).fields()
    db = lambda name: fields(fields(doc[name])['database'])
    countries = {i: fields(o) for i, o in db('country_manager').items() if isinstance(o, Object)}
    cid = next(i for i, c in countries.items() if c['definition'] == 'GBR')
    states = {i: fields(o) for i, o in db('states').items() if isinstance(o, Object)}
    techs = next(set(sequence(fields(o)['acquired_technologies'])) for o in db('technology').values()
                 if fields(o).get('country') == cid)
    population = 0
    for o in db('pops').values():
        f = fields(o)
        if states.get(f.get('location'), {}).get('country') == cid:
            population += int(f.get('workforce', 0)) + int(f.get('dependents', 0))
    buildings = []
    for o in db('building_manager').values():
        f = fields(o)
        if states.get(f.get('state'), {}).get('country') != cid or int(f.get('levels', 0)) <= 0:
            continue
        kind = f['building']; pms = sequence(f.get('production_methods'))
        # Auto-generated ownership/company/subsistence buildings are not anchors.
        if any(x in kind for x in ('company_', 'subsistence', 'financial_district', 'manor_house')):
            continue
        buildings.append({'building': kind, 'levels': int(f['levels']), 'pms': pms})
    if population != 25951649:
        raise ValueError('British baseline population mismatch: '+str(population))
    return {'population': population, 'technologies': sorted(techs), 'buildings': buildings}


def industry_mapping(eu5, config):
    directory = Path(eu5)/'in_game/common/building_types'
    mapping, stages = {}, {}
    for name, target in config['industry_files'].items():
        for key, obj in root((directory/(name+'.txt')).read_text(encoding='utf-8-sig')).entries():
            if not isinstance(obj, Object):
                continue
            f = fields(obj)
            employment = str(f.get('employment_size', ''))
            stage = next((s for s in ('mill', 'manufactory', 'workshop', 'guild') if s in employment), 'guild')
            mapping[key] = target; stages[key] = stage
    for key, target in config['industry_overrides'].items():
        mapping[key] = target
        stages[key] = 'mill' if 'mill' in key else 'manufactory'
    return mapping, stages


def building_rows(path):
    """Parse existing history, preserving exact bodies and conditional scopes."""
    rows = []
    def walk(obj, state=None, owner=None, guards=()):
        for key, value in obj.entries():
            if key == 'BUILDINGS': walk(value)
            elif key and key.startswith('s:'): walk(value, key[2:], owner, guards)
            elif key and key.startswith('region_state:'): walk(value, state, key[13:], guards)
            elif key == 'if':
                f = fields(value)
                if 'limit' not in f:
                    raise ValueError('Conditional building history lacks limit')
                walk(value, state, owner, guards+(f['limit'].text(),))
            elif key == 'limit': continue
            elif key == 'create_building':
                f = fields(value)
                def levels(o):
                    return sum(int(v) if k in ('levels', 'level') else levels(v) if isinstance(v, Object) else 0 for k, v in o.entries())
                rows.append({'state': state, 'owner': owner, 'building': f['building'],
                             'levels': levels(value), 'pms': sequence(f.get('activate_production_methods')),
                             'body': value.text(), 'guards': guards})
            else: raise ValueError('Unexpected history operation: '+str(key))
    walk(root(Path(path).read_text(encoding='utf-8-sig')))
    return rows


def block(key, body):
    return key+' = {\n'+body+'\n}\n'


def render_buildings(rows):
    states = defaultdict(lambda: defaultdict(list))
    for r in sorted(rows, key=lambda r: (r['state'], r['owner'], r['building'])):
        if r['levels'] <= 0:
            continue
        body = r.get('body')
        if body is None:
            # Local self ownership: no invented foreign investors or ownership districts.
            body = f'building = "{r["building"]}"\nreserves = 1\n'
            body += block('add_ownership', block('building', f'type = "{r["building"]}"\ncountry = "c:{r["owner"]}"\nregion = "{r["state"]}"\nlevels = {r["levels"]}'))
            body += 'activate_production_methods = { '+' '.join('"'+p+'"' for p in r['pms'])+' }\n'
        rendered = block('create_building', body)
        for guard in reversed(r.get('guards', ())):
            rendered = block('if', block('limit', guard)+rendered)
        states[r['state']][r['owner']].append(rendered)
    return block('BUILDINGS', ''.join(block('s:'+s, ''.join(block('region_state:'+o, ''.join(bs))
                 for o, bs in sorted(owners.items()))) for s, owners in sorted(states.items())))
