"""Validated, additive population-only location decisions; no border mutation."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading


def validate_entries(entries, missing, valid_provinces):
    if not isinstance(entries, dict) or len(entries) > len(missing):
        raise ValueError('Invalid review entries')
    clean = {}
    for name, row in entries.items():
        if name not in missing or not isinstance(row, dict):
            raise ValueError('Unknown or already geometrically mapped source location: ' + str(name))
        status = row.get('status')
        if status not in ('mapped', 'deferred', 'pending'):
            raise ValueError('Invalid review status')
        note = row.get('note', '')
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError('Note must be text, at most 4000 characters')
        parts = row.get('targets', [])
        if not isinstance(parts, list) or len(parts) > 100:
            raise ValueError('Invalid target list')
        targets, seen = [], set()
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError('Invalid target')
            province, weight = part.get('province'), part.get('weight', 1)
            if province not in valid_provinces or province in seen:
                raise ValueError('Unknown, non-land or duplicate target province: ' + str(province))
            if type(weight) is not int or not 1 <= weight <= 1_000_000:
                raise ValueError('Weights must be positive integers, at most 1000000')
            seen.add(province); targets.append({'province': province, 'weight': weight})
        if status == 'mapped' and not targets:
            raise ValueError('A mapped location needs at least one target province')
        clean[name] = {'status': status, 'targets': targets, 'note': note}
    return clean


def validate_document(doc, source_sha, map_sha, missing, valid_provinces):
    if not isinstance(doc, dict) or doc.get('schema') != 1:
        raise ValueError('Unsupported review format')
    if doc.get('source_sha256') != source_sha or doc.get('political_map_sha256') != map_sha:
        raise ValueError('Review belongs to another source campaign or political map')
    return validate_entries(doc.get('entries'), missing, valid_provinces)


class ReviewStore:
    def __init__(self, directory, dataset):
        self.path = Path(directory) / 'location_reviews.json'
        self.history = Path(directory) / 'review-history'
        self.lock = threading.Lock()
        self.source_sha = dataset['source_sha256']
        self.map_sha = dataset['political_map_sha256']
        self.missing = {r['id'] for r in dataset['locations']}
        self.valid = set(dataset['targets'])
        self.doc = {'schema': 1, 'source_sha256': self.source_sha, 'political_map_sha256': self.map_sha,
                    'revision': 0, 'entries': {}}
        if self.path.exists():
            self.doc = json.loads(self.path.read_text(encoding='utf-8'))
            self.validate(self.doc)

    def validate(self, doc):
        return validate_document(doc, self.source_sha, self.map_sha, self.missing, self.valid)

    def save(self, revision, entries):
        with self.lock:
            if type(revision) is not int or revision != self.doc['revision']:
                raise RuntimeError('Another page has saved changes. Export your draft or reload before saving.')
            clean = validate_entries(entries, self.missing, self.valid)
            doc = dict(self.doc, entries={**self.doc['entries'], **clean}, revision=revision+1,
                       updated_at=datetime.now(timezone.utc).isoformat())
            text = json.dumps(doc, ensure_ascii=False, indent=2)
            self.history.mkdir(parents=True, exist_ok=True)
            # Preserve both old and new snapshots before atomically committing.
            old = self.history / f'{revision:06d}.json'
            if not old.exists():
                old.write_text(json.dumps(self.doc, ensure_ascii=False, indent=2), encoding='utf-8')
            new = self.history / f'{revision+1:06d}.json'
            with new.open('x', encoding='utf-8') as f:
                f.write(text)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(text, encoding='utf-8')
            temp.replace(self.path)
            self.doc = doc
            return doc
