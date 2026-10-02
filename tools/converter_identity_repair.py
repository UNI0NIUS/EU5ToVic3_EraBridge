"""Repair display text and explicitly requested native Jing homelands."""
from pathlib import Path
from collections import Counter
from converter_project import read, digest
from converter_identity_assets import labels
from build_m2_prototype import objects
from pdx_text import root


def restore_campaign_labels(mod, run):
    """Recover only missing keys from this campaign's verified political export."""
    mod, run = Path(mod), Path(run)
    base = run/'base/eu5_converted'
    report = read(run/'base/package_report.json')
    counts = {}
    for lang in ('english', 'simp_chinese'):
        for directory in (base/'localization'/lang, base/'localization/replace'/lang):
            for p in directory.glob('*.yml'):
                if report['output_sha256'].get(p.relative_to(base).as_posix()) != digest(p):
                    raise ValueError('Campaign localization evidence changed: '+str(p))
        current = labels(mod, lang)
        missing = {k:v for k,v in labels(base, lang).items() if k not in current}
        target = mod/'localization'/lang/('zz_converter_campaign_l_'+lang+'.yml')
        # Retain any previously repaired keys on repeated upgrades.
        if missing:
            target.parent.mkdir(parents=True, exist_ok=True)
            prefix = target.read_text(encoding='utf-8-sig') if target.exists() else 'l_'+lang+':\n'
            # load_localization returns already-escaped file contents.
            target.write_text(prefix+''.join(' '+k+':0 "'+v+'"\n' for k,v in sorted(missing.items())), encoding='utf-8-sig')
        counts[lang] = len(missing)
    verify_event_labels(mod)
    return counts


def verify_event_labels(mod):
    mod = Path(mod)
    keys = set()
    for p in (mod/'events').rglob('*.txt'):
        for _, event in objects(root(p.read_text(encoding='utf-8-sig'))):
            for field, value in event.entries():
                if field in ('title','desc','flavor') and isinstance(value,str) and value.startswith('eu5'):
                    keys.add(value)
                elif field=='option':
                    value=next((v for k,v in value.entries() if k=='name'),None)
                    if isinstance(value,str) and value.startswith('eu5'):keys.add(value)
    for lang in ('english', 'simp_chinese'):
        missing = keys-set(labels(mod, lang))
        if missing:
            raise ValueError('Missing event text: '+lang+'/'+', '.join(sorted(missing)))
    return len(keys)


def restore_jing_homelands(mod, game):
    from package_m4_population_test import parse_pops
    from v3_startup_validation import rewrite_homelands
    mod, game = Path(mod), Path(game)
    resident = Counter()
    for (s,t,c,r),n in parse_pops(mod/'common/history/pops/00_eu5_world.txt').items():
        if c == 'vietnamese':resident[s] += n
    native = set()
    for p in (game/'common/history/states').glob('*.txt'):
        container = root(p.read_text(encoding='utf-8-sig')).fields().get('STATES')
        if container is None:continue
        for s,o in objects(container):
            if any(k=='add_homeland' and v=='cu:vietnamese' for k,v in o.entries()):native.add(s.removeprefix('s:'))
    path = mod/'common/history/states/00_eu5_world.txt'
    content = path.read_text(encoding='utf-8-sig')
    home = {s.removeprefix('s:'):{v.removeprefix('cu:') for k,v in o.entries() if k=='add_homeland'}
            for s,o in objects(root(content).fields()['STATES'])}
    added = []
    for s in sorted(native & set(home)):
        if resident[s] and 'vietnamese' not in home[s]:
            home[s].add('vietnamese');added.append(s)
    if added:path.write_text(rewrite_homelands(content,home),encoding='utf-8-sig')
    return dict(added=added,native_core_states=sorted(native),resident_people={s:resident[s] for s in sorted(native)})


def repair(mod, game, run):
    return dict(campaign_labels_restored=restore_campaign_labels(mod,run),jing_homelands=restore_jing_homelands(mod,game))
