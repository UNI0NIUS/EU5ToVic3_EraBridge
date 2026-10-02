"""Reusable terrain references, with no campaign owner or population allocation."""
import json
from pathlib import Path
import threading
from location_reviews import ReviewStore
from terrain_connectivity import source_seeds

SCHEMA = 'terrain-references-v1'


def validate_entries(entries, targets, sources):
    if not isinstance(entries, dict) or len(entries) > len(targets):
        raise ValueError('Invalid terrain entries')
    clean = {}
    for p, row in entries.items():
        if p not in targets or not isinstance(row, dict):
            raise ValueError('Unknown review target: '+str(p))
        status = row.get('status')
        if status not in ('pending', 'mapped', 'deferred'):
            raise ValueError('Invalid status')
        source, reference = row.get('source_location', ''), row.get('reference_location', '')
        if not isinstance(source, str) or not isinstance(reference, str):
            raise ValueError('Location must be a source key')
        if any(n and n not in sources for n in (source, reference)):
            raise ValueError('Unknown source location')
        if status == 'mapped' and not source:
            raise ValueError('Choose a geographical source location first')
        note = row.get('note', '')
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError('Note must contain at most 4000 characters')
        clean[p] = dict(status=status, source_location=source, reference_location=reference, note=note)
        if 'review_round' in row:
            if not isinstance(row['review_round'],str) or len(row['review_round'])>120:raise ValueError('Invalid review round')
            clean[p]['review_round']=row['review_round']
    return clean


def validate_document(doc, source_map, target_map, targets, sources):
    if not isinstance(doc, dict) or doc.get('schema') != SCHEMA:
        raise ValueError('Unsupported terrain review format')
    if doc.get('source_map_sha256') != source_map or doc.get('target_map_sha256') != target_map:
        raise ValueError('Terrain reviews belong to different physical maps')
    if any(k in doc for k in ('owners', 'countries', 'source_sha256')):
        raise ValueError('Reusable terrain references must not pin campaign ownership')
    return validate_entries(doc.get('entries'), targets, sources)


class TerrainReviewStore(ReviewStore):
    def __init__(self, directory, dataset):
        self.path = Path(directory)/'terrain_reviews.json'
        self.history = Path(directory)/'review-history'
        self.lock = threading.Lock()
        self.source_map = dataset['source_map_sha256']; self.target_map = dataset['target_map_sha256']
        self.targets = {p for c in dataset['components'] for p in c['provinces']}
        self.sources = set(dataset['sources'])
        self.doc = dict(schema=SCHEMA, source_map_sha256=self.source_map, target_map_sha256=self.target_map, revision=0, entries={})
        if self.path.exists():
            self.doc = json.loads(self.path.read_text(encoding='utf-8')); self.validate(self.doc)

    def validate(self, doc):
        return validate_document(doc, self.source_map, self.target_map, self.targets, self.sources)

    def save(self, revision, entries):
        # The parent persists via its location-specific validator, so keep the
        # atomic revision/history logic here with terrain-specific validation.
        from datetime import datetime, timezone
        with self.lock:
            if type(revision) is not int or revision != self.doc['revision']:
                raise RuntimeError('另一页面已保存。请先导出草稿，再刷新页面。')
            clean = validate_entries(entries, self.targets, self.sources)
            doc = dict(self.doc, entries={**self.doc['entries'], **clean}, revision=revision+1,
                       updated_at=datetime.now(timezone.utc).isoformat())
            text = json.dumps(doc, ensure_ascii=False, indent=2)
            self.history.mkdir(parents=True, exist_ok=True)
            old = self.history/f'{revision:06d}.json'
            if not old.exists(): old.write_text(json.dumps(self.doc, ensure_ascii=False, indent=2), encoding='utf-8')
            with (self.history/f'{revision+1:06d}.json').open('x', encoding='utf-8') as f: f.write(text)
            temp = self.path.with_suffix('.tmp'); temp.write_text(text, encoding='utf-8'); temp.replace(self.path)
            self.doc = doc
            return doc


def apply_references(entries, province_states, locations, uninhabitable, populations, seeds, natives, allowed_overrides=()):
    """Resolve current-save evidence only. Empty evidence stays explicitly unresolved."""
    mapping = {p: {r['reference_location'] or r['source_location']} for p, r in entries.items() if r['status'] == 'mapped'}
    overlap = (set(mapping) & seeds.keys()) - set(allowed_overrides)
    if overlap: raise ValueError('Terrain reference would override existing source evidence: '+min(overlap))
    derived, cultures, _ = source_seeds(province_states, mapping, locations, uninhabitable, populations)
    missing = []
    for p, names in mapping.items():
        if p not in derived:
            missing.append(dict(province=p, source_location=entries[p]['source_location'],
                                reference_location=entries[p]['reference_location'], reason='source_has_no_current_owner_or_native_population'))
        else:
            derived[p]['evidence_kind'] = derived[p]['kind']; derived[p]['kind'] = 'reviewed'
            derived[p]['geographical_source'] = entries[p]['source_location']
            derived[p]['review_type'] = 'terrain_reference_no_population_transfer'
    seeds.update(derived); natives.update(cultures)
    return missing
