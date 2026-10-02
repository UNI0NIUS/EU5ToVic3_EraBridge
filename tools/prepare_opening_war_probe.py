"""Prepare an isolated native V3 test userdir; never change the installed playset."""
from pathlib import Path
import argparse,json,shutil
from opening_wars import effect_block


def prepare(package, output, peace=None):
    if output.exists():raise ValueError('Use a fresh runtime directory')
    output.mkdir(parents=True)
    settings=Path.home()/'Documents/Paradox Interactive/Victoria 3/pdx_settings.json'
    shutil.copy2(settings,output/settings.name)
    overlay=output/'probe_mod'
    def write(rel,text):
        p=overlay/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8-sig')
    write('.metadata/metadata.json',json.dumps({'name':'EU5 isolated runtime snapshot','id':'eu5_war_probe','version':'1.0','short_description':'Isolated test only','tags':[],'relationships':[],'game_custom_data':{'multiplayer_synchronized':True},'supported_game_version':'1.13.*'}))
    tests='eu5_capture_opening = { success = { always = no } fail = { game_date > 1836.1.1 } }\n'
    if peace:
        rows=json.loads((package/'war_mapping.json').read_text(encoding='utf-8-sig'))
        effects='\n'.join('c:'+winner+' ?= { every_diplomatic_play = { limit = { is_diplomatic_play_type = '+r['play_type']+' } resolve_play_for = c:'+winner+' } }' for r in rows for winner in (r['attackers'] if peace=='initiator' else r['defenders']))
        write('events/eu5_probe.txt','namespace = eu5_probe\neu5_probe.1 = { type = country_event hidden = yes immediate = { '+effects+' } }')
        write('common/history/global/99_eu5_probe.txt','GLOBAL = { c:ITA = { trigger_event = { id = eu5_probe.1 days = 4 } } }')
        tests+='eu5_capture_peace = { success = { always = no } fail = { game_date > 1836.1.6 } }\n'
    write('tools/scripted_tests/eu5_snapshot.txt','last_date = "1836.1.9"\n'+effect_block('tests',tests))
    (output/'content_load.json').write_text(json.dumps({'disabledDLC':[],'enabledMods':[{'path':str(package/'eu5_economy_test')},{'path':str(overlay)}],'enabledUGC':[]},indent=2),encoding='utf-8')
    print(output)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--peace',choices=('initiator','target'))
    a=p.parse_args();prepare(a.package.resolve(),a.output.resolve(),a.peace)
