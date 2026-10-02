"""Whole-catalogue, auditable progression mapping with semantic unlock overrides.

Generic research progress uses universal EU5 nodes, not the thousands of mutually
exclusive national/religious advances. Every source and target node is accounted
for. A missing semantic match is reported rather than silently discarded.
"""
from collections import Counter, defaultdict
from pathlib import Path
import re
from economy_model import closure, definitions, map_technology
from extract_m3_politics import fields, sequence
from pdx_text import Object, root


CATEGORY_PATTERNS = {
    'production': r'production|output|rgo|raw_material|food|agricult|farm|plough|mining|mine|ore_|smelt|furnace|steel|iron|coal|lumber|wood|mills?|manufactory|manufactories|workshop|guild|cloth|glass|paper|dyes|pottery|porcelain|saltpeter|road|rail|construction|building_efficiency|tools|distill|brewery|winery|tannery|fish|cotton|silk',
    'military': r'unlock_unit|unlock_levy|mercenar|calibre|supply_limit|army|navy|naval|ship|admiral|artillery|cannon|firearm|gun|weapon|infantry|cavalry|regiment|levy|levies|fort|bastion|barrack|military|discipline|morale|manpower|sailor|tactic|siege|combat|war_score|recruit|supply_depot|anti_piracy',
    'society': r'government|law|policy|reform|cabinet|court|estate|tax|bureauc|culture|religio|tolerance|literacy|research|school|university|academ|print|book|library|bank|coin|currency|trade|merchant|market|diploma|subject|legitim|prestige|stability|enlighten|scientific|institution|health|disease|life_expectancy|sanitation|quinine|medicine|medical|urban|town|population|pop_|migration|colon|explor|artist|power_projection|republic|sovereign|constitution|spies|spy_|relations|antagonism|bond|insurance|interest|stock|rights|separation_of_powers'
}
CAPABILITY_PATTERNS = {
    'agriculture': r'farm|food|agricult|plough|enclosure|plantation|ranch',
    'textiles': r'cloth|cotton|textile|silk|tannery|leather',
    'metallurgy': r'iron|steel|smelt|furnace|ore|mine|metal|prospect',
    'workshops': r'guild|workshop|manufac|mill|tools|lathe|mechanical',
    'steam': r'steam|蒸汽机|atmospheric_engine',
    'rail': r'railroad|railways|铁路',
    'chemical': r'saltpeter|alum|dyes|bleach|chemic|distill|fertiliz',
    'communications': r'paper|print|book|news|communication',
    'construction': r'construction|glass|cement|building',
    'science': r'research|scientific|university|academ|empirici|rational',
    'finance': r'bank|coin|currency|stock|interest|trade|merchant',
    'administration': r'bureau|government|cabinet|tax|law|archive|constitution',
    'health': r'health|life_expectancy|disease|medical|medicin|sanitation|quinine',
    'army': r'army|infantry|regiment|military|gun|weapon|artillery|cannon|manpower|levy|levies|mobiliz|tactic|corps',
    'navy': r'navy|naval|ship|admiral|navigation|drydock|sailor'
}
IGNORED_FIELDS = {'icon', 'potential', 'allow', 'ai_weight', 'ai_preference_tags', 'content_priority', 'requires',
                  'age', 'for', 'in_tree_of', 'depth', 'starting_technology_level', 'research_cost', 'allow_children'}


def concepts(text, patterns):
    return sorted(k for k, pattern in patterns.items() if re.search(pattern, text, re.I))


def source_catalogue(eu5):
    eu5 = Path(eu5)
    buildings = definitions(eu5/'in_game/common/building_types')
    loc = {}
    path = eu5/'main_menu/localization/simp_chinese/advances_l_simp_chinese.yml'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            m = re.match(r'\s*([\w]+):\s*(?:\d+\s*)?"(.*)"', line)
            if m and not m[1].endswith('_desc'): loc[m[1]] = m[2]
    result = {}
    for path in sorted((eu5/'in_game/common/advances').glob('*.txt')):
        for key, obj in root(path.read_text(encoding='utf-8-sig')).entries():
            if not key or not isinstance(obj, Object): continue
            if key in result: raise ValueError('Duplicate source technology '+key)
            f = fields(obj)
            # Actual effects and unlocked objects are the primary classification
            # evidence. Names/localized titles supply sparse-node context.
            effects = [k+' '+(v.text() if isinstance(v, Object) else v) for k, v in f.items() if k not in IGNORED_FIELDS]
            unlocked = f.get('unlock_building')
            if unlocked in buildings:
                b = buildings[unlocked]
                effects += [str(b.get('category', '')), str(b.get('employment_size', '')),
                            fields(obj).get('unlock_building', '')]
            evidence = ' '.join(effects)
            text = evidence+' '+key+' '+loc.get(key, '')
            categories = concepts(evidence, CATEGORY_PATTERNS) or concepts(key, CATEGORY_PATTERNS)
            age = int(re.search(r'age_(\d)', f.get('age', 'age_0'))[1])
            generic = path.name[0].isdigit() and 'potential' not in f and 'government' not in f and 'for' not in f
            result[key] = {'age': age, 'file': path.name, 'generic': generic, 'categories': categories,
                           'capabilities': concepts(text, CAPABILITY_PATTERNS), 'evidence': evidence,
                           'unlock_road_type': f.get('unlock_road_type'),
                           'parents': [v for k, v in obj.entries() if k == 'requires' and isinstance(v, str)],
                           'classification': 'effects' if concepts(evidence, CATEGORY_PATTERNS) else 'name_context' if categories else 'unclassified'}
    # Sparse nodes may inherit context from their prerequisite branch. A fixed
    # point handles arbitrarily ordered definitions without defaulting to society.
    for _ in range(len(result)):
        updates = {}
        for key, node in result.items():
            if node['categories']: continue
            inherited = sorted({c for p in node['parents'] if p in result for c in result[p]['categories']})
            if inherited: updates[key] = inherited
        if not updates: break
        for key, categories in updates.items():
            result[key]['categories'] = categories; result[key]['classification'] = 'prerequisite_context'
    return result


class TechnologyMapper:
    def __init__(self, eu5, target, british_techs, policy, direct_rules):
        self.source = source_catalogue(eu5)
        self.target = target
        self.reference = set(british_techs)
        self.policy = policy
        self.direct_rules = direct_rules
        self.depths = {}
        def depth(key, active=frozenset()):
            if key in active: raise ValueError('Technology cycle '+key)
            if key not in self.depths:
                ps = sequence(target.techs[key].get('unlocking_technologies'))
                same = [p for p in ps if target.techs[p]['era'] == target.techs[key]['era']]
                self.depths[key] = 1+max((depth(p, active|{key}) for p in same), default=0)
            return self.depths[key]
        for key in target.techs: depth(key)
        self.max_depth = defaultdict(int)
        for key, d in self.depths.items():
            f = target.techs[key]; pair = f['category'], f['era']
            self.max_depth[pair] = max(d, self.max_depth[pair])
        self.target_features = {}
        for key, f in target.techs.items():
            evidence = [key]
            for kind, definition in target.buildings.items():
                if key in sequence(definition.get('unlocking_technologies')): evidence.append(kind)
            for pm, definition in target.pms.items():
                if key in sequence(definition.get('unlocking_technologies')):
                    evidence.append(pm)
            self.target_features[key] = concepts(' '.join(evidence), CAPABILITY_PATTERNS)

    def map(self, country):
        known = set(country['advances'])
        unknown = sorted(known-self.source.keys())
        if unknown: raise ValueError('Unknown researched source advances: '+', '.join(unknown))
        scores, coverage, evidence = {}, {}, defaultdict(list)
        for key in sorted(known):
            for feature in self.source[key]['capabilities']: evidence[feature].append(key)
        for category in ('production', 'military', 'society'):
            candidates = {k: n for k, n in self.source.items() if n['generic'] and category in n['categories']}
            weights = {k: float(self.policy['age_weights'][str(n['age'])]) for k, n in candidates.items()}
            scores[category] = sum(w for k, w in weights.items() if k in known)/sum(weights.values()) if weights else 0
            coverage[category] = {str(age): {'researched': sum(k in known for k, n in candidates.items() if n['age'] == age),
                                           'available': sum(n['age'] == age for n in candidates.values())} for age in range(1, 7)}
        direct, direct_report = map_technology(country, self.direct_rules, self.target.techs)
        exact = {}
        for key in sorted(known):
            if self.source[key]['unlock_road_type'] == 'railroad': exact['railways'] = key+' unlocks road type railroad'
            if 'steam' in self.source[key]['capabilities'] and 'production' in self.source[key]['categories']:
                exact['atmospheric_engine'] = key+' has explicit steam capability'
        seeds = set(direct_report['direct']) | exact.keys()
        decisions = {}
        for key, f in sorted(self.target.techs.items()):
            category, era = f['category'], f['era']
            rank = (self.depths[key]-1)/max(1, self.max_depth[category, era]-1)
            threshold = self.policy['era_thresholds'].get(era)
            required = threshold[0]+rank*(threshold[1]-threshold[0]) if threshold else None
            features = self.target_features[key]
            feature_evidence = {x: evidence[x] for x in features if evidence[x]}
            if key in exact: reason = 'semantic_unlock'; seeds.add(key)
            elif key in direct_report['direct']: reason = 'direct_analogue'; seeds.add(key)
            elif f.get('can_research') == 'no': reason = 'special_technology_requires_explicit_evidence'
            elif key not in self.reference: reason = 'outside_british_1836_inference_frontier'
            elif required is None: reason = 'outside_source_period'
            elif scores[category] < required: reason = 'insufficient_branch_progress'
            elif 'rail' in features and not evidence['rail']: reason = 'missing_railway_capability'
            elif features and not feature_evidence: reason = 'missing_capability_evidence'
            else: reason = 'generic_branch_progress'; seeds.add(key)
            decisions[key] = {'category': category, 'era': era, 'branch_progress': round(scores[category], 6),
                              'required_progress': required, 'features': features,
                              'capability_evidence': feature_evidence, 'decision': reason, 'researched': False}
        researched = closure(seeds, self.target.techs)
        for key in researched:
            decisions[key]['researched'] = True
            if key not in seeds: decisions[key]['decision'] = 'prerequisite_closure'
        report = {'method': 'whole_tree_weighted_progress_with_capability_gates', 'branch_progress': scores,
                  'age_coverage': coverage, 'direct': direct_report['direct'], 'semantic_unlocks': exact,
                  'prerequisites': sorted(researched-seeds), 'decisions': decisions,
                  'source_advance_count': len(known),
                  'unclassified_researched': sorted(k for k in known if not self.source[k]['categories']),
                  'by_category': {c: sorted(k for k in researched if self.target.techs[k]['category'] == c)
                                  for c in ('production', 'military', 'society')}}
        return researched, report

    def catalogue_report(self):
        return {'source_nodes': len(self.source), 'target_nodes': len(self.target.techs),
                'source_classification': dict(Counter(n['classification'] for n in self.source.values())),
                'generic_denominator_nodes': sum(n['generic'] for n in self.source.values()),
                'unclassified': [k for k, n in self.source.items() if not n['categories']],
                'sources': self.source,
                'targets': {k: {'category': f['category'], 'era': f['era'], 'features': self.target_features[k],
                                'prerequisites': sequence(f.get('unlocking_technologies'))} for k, f in self.target.techs.items()}}
