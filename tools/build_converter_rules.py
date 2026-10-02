"""Freeze reusable map/culture/economy policies; exclude campaign histories."""
import argparse
from pathlib import Path
import shutil
from converter_project import read,write,digest

def build(root,out,asset_package,context,baseline,identity_package=None,game=None):
    root,out=Path(root).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Rules directory already exists')
    package=Path(asset_package);report=read(package/'package_report.json');assets=Path(report['mod_directory'])
    if not assets.is_absolute():assets=package/assets
    out.mkdir(parents=True)
    shutil.copytree(root/'config/personal',out/'config/personal')
    shutil.copytree(root/'config/geography',out/'config/geography')
    for directory in ('common/cultures','common/religions','common/discrimination_traits','common/discrimination_trait_groups','gfx/interface/icons/religion_icons','localization'):
        if (assets/directory).exists():shutil.copytree(assets/directory,out/'assets'/directory)
    # Only identity labels are reusable. Generated E*/U*/R* country tags can
    # denote a different country in the next save.
    from economy_model import definitions
    import re
    allowed=set().union(*(set(definitions(out/'assets/common'/k)) for k in ('cultures','religions','discrimination_traits','discrimination_trait_groups')))
    if game:
        allowed.update(set().union(*(set(definitions(Path(game)/'common'/k)) for k in ('cultures','religions','discrimination_traits','discrimination_trait_groups'))))
    for p in (out/'assets/localization').rglob('*.yml'):
        lines=[]
        for line in p.read_text(encoding='utf-8-sig').splitlines():
            m=re.match(r'\s*([\w.-]+):\d*\s+"',line)
            if not m or m[1] in allowed:lines.append(line)
        p.write_text('\n'.join(lines)+'\n',encoding='utf-8-sig')
    mapping=read(root/'config/personal/m3_world.json')['culture_aliases']
    mapping.update(read(context)['mapping']);write(out/'culture_mapping.json',mapping)
    geography=read(out/'config/geography/reviewed_location_links.json')
    reviews=read(root/'.local/m3/terrain-workstation-1337/terrain_reviews.json')
    extra=root/'.local/m3/terrain-workstation-1337-rereview'
    overrides=[]
    if (extra/'terrain_reviews.json').exists():
        more=read(extra/'terrain_reviews.json');scope=read(extra/'review_scope.json')
        # Only explicitly confirmed geography references are reusable; no country IDs or populations.
        entries={p:r for p,r in more['entries'].items() if r.get('review_round')==scope['review_round']}
        reviews['entries'].update(entries);overrides=sorted(set(entries)&set(scope['provinces']))
    write(out/'terrain_reviews.json',reviews)
    # Campaign-bound identity/owner overrides do not belong in the general profile.
    profile=read(out/'config/personal/m3_world.json')
    for key in ('source_flag_overrides','country_tag_overrides','uncolonized_region_overrides','fallback_country_overrides','province_anchor_overrides','unmapped_state_anchors'):profile[key]={}
    write(out/'config/personal/m3_world.json',profile)
    manifest=dict(schema=1,kind='explicit_reusable_converter_rules',source_map_sha256=geography['source_map_sha256'],target_map_sha256=geography['target_map_sha256'],
                  baseline=str(Path(baseline).resolve()),baseline_sha256=digest(baseline),terrain_override_provinces=overrides,
                  notes=['Culture aliases are matched by source keys, never old country IDs.',
                         'Assets include definitions and localization only; no campaign country/population/territory history.',
                         'Source-empty island/template rules remain explicit reviewed policies; unknown evidence blocks export.'],
                  files={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()})
    write(out/'manifest.json',manifest)
    if identity_package is not None:
        if game is None:raise ValueError('Identity upgrade requires the target game directory')
        from update_converter_identity_rules import upgrade
        upgraded=out.with_name(out.name+'-identity-upgrade')
        upgrade(root,out,identity_package,upgraded,game)
        backup=out.with_name(out.name+'-before-identity')
        if backup.exists():raise ValueError('Identity backup already exists')
        out.rename(backup);upgraded.rename(out)
        manifest=read(out/'manifest.json')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','out','asset-package','context','baseline'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--identity-package',type=Path);p.add_argument('--game',type=Path)
    a=p.parse_args();build(a.root,a.out,a.asset_package,a.context,a.baseline,a.identity_package,a.game)
