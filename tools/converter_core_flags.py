"""Use the same EU5 heraldry importer for dormant and initially live countries."""
import shutil
from pathlib import Path
from m3_flags import FlagExporter, generated_flag
from build_m3_world import block
from build_m2_prototype import objects
from pdx_text import root


def install(mod,game,eu5,politics,dormant):
    importer=FlagExporter(eu5);importer.source_countries=politics['countries']
    existing={k:' '.join(o.text().split()) for base in (game,mod)
              for p in (base/'common/coat_of_arms/coat_of_arms').glob('*.txt')
              if p.name!='zzzz_eu5_core_countries.txt'
              for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    coas={};flags={};records=[]
    native={k for p in (game/'common/country_definitions').glob('*.txt') for k,_ in objects(root(p.read_text(encoding='utf-8-sig')))}
    for tag,c in sorted(dormant.items()):
        src=politics['countries'][c['source_id']]
        coa,key,attempts=importer.resolve(src,c['source_tag'],politics.get('current_age'))
        if coa:mode='imported_eu5_definition'
        elif tag in native:
            mode='reviewed_native_flag';records.append(dict(tag=tag,mode=mode,attempts=attempts));continue
        else:
            mode='generated_fallback';coa='eu5_core_fallback_'+tag
            coas[coa]=generated_flag(c['source_id']+':'+str(c['source_tag']),src.get('color') or [100,130,160],c['religion'])
        flags[tag]=block('flag_definition',f'coa = {coa}\nsubject_canton = {coa}\npriority = 1000\n')
        records.append(dict(tag=tag,source_id=c['source_id'],mode=mode,source_flag=key,coa=coa,attempts=attempts))
    for key,body in importer.imported.items():
        if key in existing:
            if existing[key]!=' '.join(body.split()):raise ValueError('Conflicting imported heraldry: '+key)
        else:coas[key]=body
    # Native TAG files must be overridden by filename; removing the old TAG
    # inside those copies prevents duplicate flag lists and wrong native flags.
    filename='zzzz_eu5_core_countries.txt'
    paths={p.name:p for base in (game,mod) for p in (base/'common/flag_definitions').glob('*.txt') if p.name!=filename}
    for name,p in paths.items():
        entries=list(objects(root(p.read_text(encoding='utf-8-sig'))))
        if any(k in flags for k,_ in entries):
            dest=mod/'common/flag_definitions'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(''.join(block(k,o.text()) for k,o in entries if k not in flags),encoding='utf-8-sig')
    def save(rel,value):
        p=mod/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value,encoding='utf-8-sig')
    save('common/flag_definitions/'+filename,''.join(block(k,v) for k,v in sorted(flags.items())))
    save('common/coat_of_arms/coat_of_arms/'+filename,''.join(block(k,v) for k,v in sorted(coas.items())))
    # Reuse the established color file, so named colors are defined only once.
    color_path=mod/'common/named_colors/eu5_m3_flags.txt'
    raw=color_path.read_text(encoding='utf-8-sig') if color_path.exists() else 'colors = {}'
    from build_m2_prototype import patch,replace_body
    outer=root(raw).fields()['colors'];known={k for k,_ in outer.entries() if k}
    addition=''.join('eu5_m3_'+k+' = '+importer.colors[k]+'\n' for k in sorted(importer.used_colors) if 'eu5_m3_'+k not in known)
    save('common/named_colors/eu5_m3_flags.txt',patch(raw,[replace_body(outer,outer.text()+'\n'+addition)]))
    for rel,source in importer.assets.items():
        target=mod/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    from v3_startup_validation import flag_assets
    repairs=flag_assets(game,mod,eu5)
    return dict(countries=records,texture_repairs=repairs,imported=sum(r['mode']=='imported_eu5_definition' for r in records),
                native=sum(r['mode']=='reviewed_native_flag' for r in records),fallback=sum(r['mode']=='generated_fallback' for r in records))
