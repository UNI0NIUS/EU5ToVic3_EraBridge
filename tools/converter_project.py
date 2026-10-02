"""Portable project settings and deterministic, independently testable risk/merge rules."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid

DEFAULTS = dict(population_multiplier=1.0, arable_multiplier=1.0,
                workforce_share=.25, staffing=.75, food_wealth=10,
                small_arable=3, unemployment_threshold=.25, food_shortfall_threshold=.20)
RANGES = dict(population_multiplier=(.1, 5), arable_multiplier=(.1, 5),
              workforce_share=(.1, .6), staffing=(.1, 1), food_wealth=(1, 30),
              small_arable=(0, 100), unemployment_threshold=(.01, 1), food_shortfall_threshold=(.01, 1))

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)

def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def mod_name(value):
    if not isinstance(value,str):raise ValueError('请输入模组名称')
    value=value.strip()
    if not value:raise ValueError('模组名称不能为空')
    if len(value)>120:raise ValueError('模组名称最多 120 个字符')
    if any(ord(c)<32 or 127<=ord(c)<160 for c in value):raise ValueError('模组名称不能包含换行或控制字符')
    return value

def settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('未知参数')
    result = dict(DEFAULTS, **value)
    for key, (lo, hi) in RANGES.items():
        n = result[key]
        if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or not lo <= n <= hi:
            raise ValueError(f'{key} 必须在 {lo}–{hi} 之间')
    for key in ('small_arable', 'food_wealth'):
        if result[key] != int(result[key]): raise ValueError(key + ' 必须为整数')
        result[key] = int(result[key])
    return result

def apportion(total, weights):
    """Largest remainder with a stable tie break; never invents arable slots."""
    if total < 0 or any(v < 0 for v in weights.values()): raise ValueError('Negative capacity')
    den = sum(weights.values())
    if not den: return {k: 0 for k in weights}
    result = {k: total * v // den for k, v in weights.items()}
    order = sorted(weights, key=lambda k: (-(total * weights[k] % den), k))
    for k in order[:total-sum(result.values())]: result[k] += 1
    return result

def resolve_merges(parts, operations, edges):
    """Replay ordered decisions. Part transfers require an existing adjacent same-state part."""
    owners = {p: row['country'] for row in parts.values() for p in row['provinces']}
    states = {p: row['state'] for row in parts.values() for p in row['provinces']}
    original = dict(owners)
    aliases = {}
    transitions = []
    for op in operations:
        if not isinstance(op, dict) or op.get('kind') not in ('country', 'region'):
            raise ValueError('未知合并类型')
        source, target = op.get('source'), op.get('target')
        if source == target or source not in owners.values() or target not in owners.values():
            raise ValueError('请选择两个仍存在的不同国家')
        state = op.get('state') if op['kind'] == 'region' else None
        selected = {p for p, t in owners.items() if t == source and (state is None or states[p] == state)}
        if not selected: raise ValueError('待合并地区已不存在')
        neighboring = any((a in selected and owners.get(b) == target and (state is None or states[b] == state)) or
                          (b in selected and owners.get(a) == target and (state is None or states[a] == state)) for a,b in edges)
        if not neighboring: raise ValueError('合并目标必须真实陆地相邻；地区合并需在同一州')
        if state and not any(t == source and p not in selected for p,t in owners.items()):
            raise ValueError('这会删除整个国家，请选择“整个国家合并”以同步外交关系')
        transitions.append((deepcopy(op), sorted(selected)))
        for p in selected: owners[p] = target
        if state is None:
            for old, new in list(aliases.items()):
                if new == source: aliases[old] = target
            aliases[source] = target
    transfers = {(states[p], original[p]): owners[p] for p in owners if owners[p] != original[p]}
    return owners, aliases, transfers, transitions

def assess(row, options):
    workforce = row['population'] * options['workforce_share']
    capacity = row.get('job_capacity')
    unemployment = max(0, 1 - capacity/workforce) if workforce and capacity is not None else (0 if not workforce else None)
    demand, supply = row.get('food_demand'), row.get('food_supply')
    shortage = max(0, 1-supply/demand) if demand and supply is not None else (0 if demand == 0 else None)
    risks = []
    if row.get('arable') is not None and row['arable'] <= options['small_arable']: risks.append('arable')
    if unemployment is not None and unemployment+1e-12 >= options['unemployment_threshold']: risks.append('unemployment')
    if shortage is not None and shortage+1e-12 >= options['food_shortfall_threshold']: risks.append('food')
    return dict(row, estimated_unemployment=unemployment, food_shortfall=shortage, risks=risks)

def summarize(rows):
    result = Counter(population=0, arable=0, regions=len(rows), countries=len({r['country'] for r in rows}))
    for row in rows:
        result['population'] += row['population']; result['arable'] += row['arable']
        for risk in row['risks']: result[risk + '_alerts'] += 1
        if row['estimated_unemployment'] is None: result['unknown_jobs'] += 1
        if row['food_shortfall'] is None: result['unknown_food'] += 1
    return dict(result)
