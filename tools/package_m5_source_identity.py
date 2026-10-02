"""Refresh source heraldry and rank, then preserve the V3 political identity overlay."""
import argparse
from datetime import datetime
from pathlib import Path
import re
import shutil
import html
from collections import Counter
from package_m5_dynamic_identity import ROOT, GAME, read, dump, digest, allowed as dynamic_allowed
from package_m5_flags import EU5, REPORT, POLITICS, ECONOMY, SAVE
from source_flag_context import enrich, RANK_TIERS
from m3_flags import FlagExporter, block
from pdx_text import root, Object
from build_m2_prototype import objects, replace_body, patch
from m5_dynamic_identity import apply, set_scalar
from verify_dynamic_identity import verify

def allowed(rel):
    return dynamic_allowed(rel) or rel.startswith(('common/country_definitions/',
        'common/coat_of_arms/coat_of_arms/','gfx/coat_of_arms/')) or rel=='common/named_colors/eu5_m3_flags.txt'

def build(output):
    installed=read(ROOT/'.local/economy/installation-latest.json');prior=Path(installed['package'])
    previous=read(prior/'package_report.json');base=Path(previous['mod_directory'])
    for rel,h in previous['output_sha256'].items():assert digest(base/rel)==h,rel
    assert not output.exists()
    mod=output/'eu5_economy_test';shutil.copytree(base,mod)
    config=ROOT/'config/personal/source_identity.json';cfg=read(config)
    world=read(REPORT);politics=read(POLITICS);economy=read(ECONOMY)
    assert cfg['source_sha256']==world['source_sha256']==politics['source_sha256']==economy['source_sha256']==digest(SAVE)
    rawfile=ROOT/'.local/m3/countries-raw.json'
    politics,ranks=enrich(politics,read(rawfile),economy,EU5,cfg['rank_overrides'])
    for sid,rank in cfg.get('confirmed_ranks',{}).items():assert ranks[sid]['rank']==rank,(sid,ranks[sid])
    with SAVE.open(encoding='utf-8') as handle:
        age=next((m[1] for line in handle if (m:=re.match(r'^current_age\s*=\s*(\w+)',line))),None)
    assert age
    exporter=FlagExporter(EU5);exporter.source_countries=politics['countries']
    flagfiles=list((mod/'common/flag_definitions').glob('*.txt'))
    definitions={k:o for path in flagfiles for k,o in objects(root(path.read_text(encoding='utf-8-sig')))}
    replacements={};audit=[]
    for tag,c in world['countries'].items():
        sid=c.get('source_id')
        if not sid:continue
        src=politics['countries'][sid]
        old=[dict(o.entries())['coa'] for _,o in objects(definitions.get(tag,root('')))
             if dict(o.entries()).get('priority')=='100000']
        coa,key,attempts=exporter.resolve(src,c['source_tag'],age)
        changed=bool(old and coa and old[0]!=coa)
        if changed:replacements[tag]=(old[0],coa)
        audit.append({'tag':tag,'name':c['name_simp_chinese'],'source_id':sid,
            'rank':ranks[sid],'old_coa':old[0] if old else None,'resolved_source_flag':key,
            'new_coa':coa,'flag_changed':changed,'attempts':attempts,
            'unresolved':exporter.unresolved_candidates(src,c['source_tag'],age)})
    # Replace only imported opening art, fallback art, and embedded source panels.
    # Keep all existing generated colonial flags and their design choices.
    for path in flagfiles:
        text=path.read_text(encoding='utf-8-sig')
        edits=[]
        # Two countries may share base art but qualify for different variants.
        for tag,obj in objects(root(text)):
            if tag not in replacements:continue
            old,new_coa=replacements[tag]
            body=re.sub(r'\b(coa|subject_canton)\s*=\s*("?)'+re.escape(old)+r'\2\b',
                lambda m:f'{m[1]} = {m[2]}{new_coa}{m[2]}',obj.text())
            edits.append(replace_body(obj,body))
        new=patch(text,edits)
        if new!=text:path.write_text(new,encoding='utf-8-sig')
    coafile=mod/'common/coat_of_arms/coat_of_arms/zz_eu5_world.txt'
    text=coafile.read_text(encoding='utf-8-sig');known=dict(objects(root(text)))
    text+='\n'+''.join(block(k,v) for k,v in exporter.imported.items() if k not in known)
    coafile.write_text(text,encoding='utf-8-sig')
    colorfile=mod/'common/named_colors/eu5_m3_flags.txt'
    colors=dict(dict(objects(root(colorfile.read_text(encoding='utf-8-sig'))))['colors'].entries())
    # Preserve the existing color file verbatim except for missing named colors.
    text=colorfile.read_text(encoding='utf-8-sig');obj=dict(objects(root(text)))['colors']
    additions=''.join(f'\neu5_m3_{k} = {exporter.colors[k]}' for k in sorted(exporter.used_colors) if 'eu5_m3_'+k not in colors)
    if additions:colorfile.write_text(patch(text,[(obj.end,obj.end,additions+'\n')]),encoding='utf-8-sig')
    for rel,src in exporter.assets.items():
        dest=mod/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    for key,body in exporter.imported.items():
        for kind,name in re.findall(r'\b(pattern|texture)\s*=\s*"([^"\n]+)"',body):
            folders=['patterns'] if kind=='pattern' else ['colored_emblems','textured_emblems']
            assert any((mod/'gfx/coat_of_arms'/folder/name).is_file() for folder in folders),(key,name)
        for parent in re.findall(r'\bparent\s*=\s*"([^"]+)"',body):assert parent in exporter.imported or parent in known,parent
    tiers={row['tag']:RANK_TIERS[row['rank']['rank']] for row in audit if row['rank']['rank'] in RANK_TIERS}
    tier_changes=[]
    for path in (mod/'common/country_definitions').glob('*.txt'):
        text=path.read_text(encoding='utf-8-sig');edits=[]
        for tag,obj in objects(root(text)):
            if tag not in tiers:continue
            old=dict(obj.entries()).get('tier')
            if old!=tiers[tag]:
                edits.append(replace_body(obj,set_scalar(obj.text(),'tier',tiers[tag])))
                tier_changes.append({'tag':tag,'old':old,'new':tiers[tag]})
        if edits:path.write_text(patch(text,edits),encoding='utf-8-sig')
    identity=apply(mod,GAME,world);identity_check=verify(mod,GAME,identity)
    final_flags={k:o for path in flagfiles for k,o in objects(root(path.read_text(encoding='utf-8-sig')))}
    for row in audit:
        if not row['old_coa']:continue
        expected=row['new_coa'] or row['old_coa']
        opening=[dict(o.entries())['coa'] for _,o in objects(final_flags[row['tag']]) if dict(o.entries()).get('priority')=='100000']
        assert opening==[expected],(row['tag'],opening,expected)
    first={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    apply(mod,GAME,world)
    assert first=={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    bytag={r['tag']:r for r in audit}
    for tag,key in {'CHI':'CHI_Ming_dragon','ENG':'ENG_monarchy','SPA':'SPA'}.items():
        assert bytag[tag]['resolved_source_flag']==key,(tag,bytag[tag]['resolved_source_flag'])
    defs={k:o for p in (mod/'common/country_definitions').glob('*.txt') for k,o in objects(root(p.read_text(encoding='utf-8-sig')))}
    for tag,tier in tiers.items():assert dict(defs[tag].entries())['tier']==tier
    meta=read(mod/'.metadata/metadata.json');m=re.fullmatch(r'0\.5\.(\d+)-m5-test(\d+)',installed['version']);assert m
    meta['version']=f'0.5.{int(m[1])+1}-m5-test{int(m[2])+1}';dump(mod/'.metadata/metadata.json',meta)
    current={p.relative_to(mod).as_posix():digest(p) for p in mod.rglob('*') if p.is_file()}
    changed=[p for p,h in current.items() if previous['output_sha256'].get(p)!=h]
    assert set(previous['output_sha256'])<=set(current)
    assert all(allowed(p) for p in changed)
    summary={'countries':len(audit),'flags_changed':sum(r['flag_changed'] for r in audit),
             'tier_changes':len(tier_changes),'rank_basis':dict(Counter(r['rank']['basis'] for r in audit)),
             'countries_with_unresolved_flag_conditions':sum(bool(r['unresolved']) for r in audit)}
    dump(output/'source_identity.json',{'summary':summary,'countries':audit,'tier_changes':tier_changes,
        'source_age':age,'rank_policy':'Explicit campaign observations, then named current rank, then last dated rank history. Numeric level and great_power_rank are not interpreted as country tier.'})
    dump(output/'dynamic_identity.json',identity)
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in [r['tag'],r['name'],r['rank']['rank'],r['rank']['basis'],r['resolved_source_flag'],r['flag_changed'],len(r['unresolved'])])+'</tr>' for r in audit)
    (output/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>源旗帜与国家等级修正</title><style>body{font:16px system-ui;margin:24px}td,th{padding:8px;border:1px solid #ccc}table{border-collapse:collapse}</style><h1>源旗帜与国家等级 · '+meta['version']+'</h1><p>明朝龙旗、英格兰三狮旗、西班牙勃艮第旗。英国为帝国级；法国、罗马尼亚、沃里尼亚、基辅为王国级，与用户确认和源等级历史一致，无须人工覆盖。按命名等级和带日期的历史选择，数值 level 不冒充已解码等级。仍有未知的王朝、领土等条件，不能声称全部源旗帜已完整还原。V3 动态政治身份已重新应用并验证。国家 tier 变更请开新局检查。</p><pre>'+html.escape(str(summary))+'</pre><table><tr><th>TAG</th><th>国家</th><th>源等级</th><th>依据</th><th>旗帜</th><th>变更</th><th>未知条件</th></tr>'+rows+'</table>',encoding='utf-8')
    inputs=[prior/'package_report.json',REPORT,POLITICS,ECONOMY,rawfile,config,Path(__file__),ROOT/'tools/m3_flags.py',ROOT/'tools/source_flag_context.py',ROOT/'tools/m5_dynamic_identity.py',ROOT/'tools/verify_dynamic_identity.py',EU5/'in_game/map_data/definitions.txt']
    inputs+=list((EU5/'main_menu/common/flag_definitions').glob('*.txt'))+list((EU5/'main_menu/common/scripted_triggers').glob('*coa*.txt'))
    report={'status':'m5_source_identity_static_verified_runtime_pending','version':meta['version'],'mod_name':meta['name'],
        'mod_directory':str(mod),'prior_package':str(prior),'update_scope':'m5_source_identity','new_campaign_required':True,
        'changed_files':changed,'output_sha256':current,'input_sha256':{str(p.resolve()):digest(p) for p in inputs}}
    dump(output/'package_report.json',report)
    dump(output/'verification.json',{'status':'passed_static_runtime_pending','literacy':read(prior/'verification.json')['literacy'],
        'source_identity':{'status':'passed','tiers_readback':True,'three_reference_flags':True},'dynamic_identity':identity_check,
        'unrelated_files_byte_identical':True,'idempotent':True,'package_report_sha256':digest(output/'package_report.json'),
        'audit_sha256':{n:digest(output/n) for n in ['source_identity.json','dynamic_identity.json','review.html']}})
    print({'package':str(output),'version':meta['version'],**summary})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'.local/economy/packages'/('m5-source-identity-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
    build(p.parse_args().output.resolve())
