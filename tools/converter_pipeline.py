"""Explicit input/output orchestration; no installation and no prior campaign history."""
import argparse
from datetime import datetime
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback
from types import SimpleNamespace
import uuid
from converter_project import read, write, digest

def run_conversion(root, workspace, request, progress=None, cancel=None):
    root,workspace=Path(root).resolve(),Path(workspace).resolve()
    # Commands come from fixed application code, never a project-supplied command line.
    for key in ('save','eu5','game','rules'):
        if not request.get(key) or not Path(request[key]).exists():raise ValueError('路径不存在：'+key)
    run=workspace/'runs'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    run.mkdir(parents=True,exist_ok=False)
    request={**request,'run':str(run.resolve()),'root':str(root.resolve())}
    write(run/'request.json',request)
    with (run/'conversion.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--worker',str(run/'request.json')],stdout=log,stderr=subprocess.STDOUT,cwd=root,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while True:
            if cancel is not None and cancel.is_set():
                if os.name=='nt':
                    # Only this task's worker and its child importer processes are stopped.
                    stopped=subprocess.run([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'),'/PID',str(process.pid),'/T','/F'],capture_output=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    if stopped.returncode and process.poll() is None:process.terminate()
                else:process.terminate()
                process.wait(timeout=15)
                write(run/'status.json',dict(status='cancelled',stage='用户停止转换'))
                raise RuntimeError('转换已停止；未完成的任务保留在 '+str(run))
            try:
                code=process.wait(timeout=2);break
            except subprocess.TimeoutExpired:
                if progress and (run/'status.json').exists():progress(read(run/'status.json').get('stage','正在启动'))
    if code:
        detail=read(run/'status.json') if (run/'status.json').exists() else {}
        raise ValueError(str(detail.get('error','转换失败'))+'；日志：'+str(run/'conversion.log'))
    return dict(directory=str(run/'complete'),log=str(run/'conversion.log'),run=str(run))

def validate_rules(path,game,eu5):
    path=Path(path);manifest=read(path)
    if manifest.get('schema')!=1:raise ValueError('Unsupported rules manifest')
    for rel,sha in manifest['files'].items():
        p=(path.parent/rel).resolve()
        if not p.is_relative_to(path.parent.resolve()):raise ValueError('Rules path escapes its directory')
        if digest(p)!=sha:raise ValueError('Rules changed since manifest: '+rel)
    for name,p in [('source_map_sha256',eu5/'in_game/map_data/locations.png'),('target_map_sha256',game/'map_data/provinces.png')]:
        if digest(p)!=manifest[name]:raise ValueError('Rules do not match installed map: '+name)
    baseline=Path(manifest['baseline'])
    if not baseline.is_absolute():baseline=path.parent/baseline
    if digest(baseline)!=manifest['baseline_sha256']:raise ValueError('V3 baseline changed')
    return manifest,baseline.resolve()

def worker(request):
    root=Path(request['root']);run=Path(request['run']);save=Path(request['save']).resolve();game=Path(request['game']).resolve()
    installation=Path(request['eu5']).resolve();eu5=installation/'game' if (installation/'game').exists() else installation
    if eu5==installation:installation=installation.parent
    original_save=save;original_sha=digest(save);sha=original_sha
    manifest,baseline=validate_rules(request['rules'],game,eu5)
    rules=run/'rules';shutil.copytree(Path(request['rules']).parent,rules)
    # All stage policies are frozen in this run. Resolve external reference once.
    manifest['baseline']=str(baseline);write(rules/'manifest.json',manifest)
    executable=root/'build/Release-Windows/EU5ToVic3/EU5ToVic3Converter.exe'
    bundled=root/'native/EU5ToVic3Converter.exe'
    if bundled.exists():executable=bundled
    def stage(name,fn):
        print('\nSTAGE '+name,flush=True);write(run/'status.json',dict(status='running',stage=name,source_sha256=sha))
        result=fn();print('DONE '+name,flush=True);return result
    def audit():
        from converter_import import audit as import_audit
        import_audit(executable,original_save,installation,run,request)
    stage('C++ import audit',audit);auditpath=run/'source/audit/import_report.json';auditdoc=read(auditpath)
    save=run/'source/decoded.eu5';sha=digest(save)
    write(run/'source/provenance.json',dict(original_save=str(original_save),original_sha256=original_sha,decoded_sha256=sha))
    import extract_m3_politics as politics
    stage('Source politics',lambda:write(run/'source/politics.json',politics.extract(save,auditdoc)))
    import extract_m4_population as population
    stage('Source population',lambda:population.extract(save,auditpath,run/'source/population'))
    import extract_m4_literacy as literacy
    stage('Source literacy',lambda:literacy.extract(save,run/'source/population',run/'source/literacy'))
    for name,module in [('economy','extract_economy_source'),('military','extract_military_source'),('navy','extract_naval_source')]:
        m=importlib.import_module(module)
        stage('Source '+name,lambda m=m,name=name:m.extract(save,auditpath if name=='economy' else eu5,run/'source'/(name+'.json')))
    import extract_war_source
    stage('Source wars',lambda:extract_war_source.extract(save,run/'source/wars.json',sha))
    import converter_source_world as world
    for key,value in dict(ROOT=rules,RUN=run,GAME=game,EU5=eu5,AUDIT=auditpath,ASSETS=rules/'assets').items():setattr(world,key,value)
    # Reusable stage code takes only this worker's explicit context.
    stage('Source territory and political base',world.build)
    import converter_source_population
    stage('Population, cultures and literacy',converter_source_population.build)
    import extract_political_features as features
    def evidence():
        p=run/'source/politics.json'
        write(run/'source/political-features/features.json',features.extract(save,read(p)))
        catalogs={'eu5':{},'v3':{}}
        for kind in ('laws','government_reforms','advances','estate_privileges','societal_values','institution'):catalogs['eu5'][kind]=features.catalog(eu5/'in_game/common'/kind)
        for kind in ('laws','institutions','technology/technologies'):catalogs['v3'][kind]=features.catalog(game/'common'/kind)
        write(run/'source/political-features/definitions.json',catalogs)
    stage('Political evidence',evidence)
    import build_political_rules_report as lawreport
    args=SimpleNamespace(politics=run/'source/politics.json',evidence=run/'source/political-features',mapping=run/'political/conversion_report.json',
                         population=run/'source/population',literacy=run/'source/literacy',output=run/'political-rules',historical_context=False,
                         audit=auditpath,economy=run/'source/economy.json',v3=game)
    stage('Political rule evaluation',lambda:lawreport.build(args))
    import converter_source_politics
    stage('Laws and technology',converter_source_politics.build)
    import build_economy
    stage('Economic conversion',lambda:build_economy.build(run/'source/economy.json',run/'base',game,eu5,baseline,rules/'config/personal/economy.json',run/'economy'))
    import complete_economy
    stage('Economic capacity, administration and military',lambda:complete_economy.build(run/'economy',run/'base',run/'source/economy.json',run/'source/military.json',game,eu5,rules/'config/personal/economy_capacity.json',run/'capacity',run/'source/navy.json'))
    import converter_source_complete
    stage('Supply chain, land and opening wars',converter_source_complete.build)
    finalize(request,stage)

def finalize(request,stage):
    """Validate and seal a completed world; always recheck immutable source inputs."""
    import converter_source_world as world
    run=Path(request['run']);game=Path(request['game']).resolve()
    installation=Path(request['eu5']).resolve();eu5=installation/'game' if (installation/'game').exists() else installation
    auditdoc=read(run/'source/audit/import_report.json');provenance=read(run/'source/provenance.json')
    save=run/'source/decoded.eu5';sha=provenance['decoded_sha256']
    original_save=Path(provenance['original_save']);original_sha=provenance['original_sha256']
    package=run/'complete';mod=package/'eu5_converted'
    from v3_startup_validation import validate_state_history,culture_modifiers,flag_assets
    from economy_model import definitions
    from converter_world import STATES
    stage('Startup script validation',lambda:validate_state_history((mod/STATES).read_text(encoding='utf-8-sig'),set(definitions(game/'common/cultures'))|set(definitions(mod/'common/cultures'))))
    culture_modifiers(game,mod,write=True);flag_assets(game,mod,eu5)
    from converter_command_capacity import install as install_command_capacity
    write(package/'command_capacity_verification.json',install_command_capacity(game,mod))
    from converter_startup_compatibility import apply as startup_compatibility
    if (run/'rules/identity_policy.json').exists():
        from verify_converter_identity import verify_output
        stage('Identity and population readback',lambda:write(package/'identity_verification.json',verify_output(run,game)))
        from converter_identity_audit import verify as verify_identity
        from converter_identity_assets import sync
        stage('Current culture labels and religion colors',lambda:write(package/'identity_asset_verification.json',sync(mod,run/'rules/assets')))
        from converter_identity_repair import repair
        stage('Campaign text and Jing homelands',lambda:write(package/'identity_repair.json',repair(mod,game,run)))
        stage('Country labels and icons',lambda:write(package/'country_identity_verification.json',verify_identity(mod,game,read(run/'political/conversion_report.json')['countries'])))
    stage('Starting laws, localization and opening wars',lambda:write(package/'startup_compatibility.json',startup_compatibility(mod,game,run)))
    if digest(save)!=sha or digest(original_save)!=original_sha:raise ValueError('Source save changed during conversion')
    name='EU5 Converted '+auditdoc['date'];metadata=mod/'.metadata/metadata.json'
    if metadata.exists():
        info=read(metadata);info.update(name=name,id='eu5-converted-'+sha[:12],version='0.12.2',short_description='World converted from EU5 '+auditdoc['date']+'; runtime verification pending.')
        write(metadata,info)
    report=dict(status='passed_static_runtime_pending',source_date=auditdoc['date'],source_sha256=sha,mod_directory=str(mod),
                mod_name=name,version='0.12.2',
                political_run=str(run/'political'),demographic_run=str(run/'demographic'),runtime_verified=False,
                output_sha256=world.files(mod),rules_sha256=digest(Path(request['rules'])),summary=read(package/'summary.json'))
    from converter_refresh import REVISION
    from converter_startup_compatibility import REVISION as STARTUP_REVISION
    from converter_source_claims import REVISION as CLAIMS_REVISION
    report['source_claims_revision']=CLAIMS_REVISION
    report['startup_compatibility_revision']=STARTUP_REVISION
    report.update(source_run=str(run.resolve()),refresh_signature=REVISION+':'+digest(Path(request['rules'])),identity_policy=read(run/'rules/identity_policy.json')['revision'] if (run/'rules/identity_policy.json').exists() else None)
    write(package/'package_report.json',report)
    (package/'eu5_converted.mod').write_text(f'name="EU5 Converted {auditdoc["date"]}"\nversion="0.12.2"\nsupported_version="1.13.*"\npath="mod/eu5_converted"\n',encoding='utf-8-sig')
    write(run/'status.json',dict(status='completed_static_runtime_pending',directory=str(package),source_sha256=sha))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--worker',type=Path,required=True);a=p.parse_args();req=read(a.worker)
    try:worker(req)
    except Exception as e:
        state=read(Path(req['run'])/'status.json') if (Path(req['run'])/'status.json').exists() else {}
        write(Path(req['run'])/'status.json',dict(state,status='failed',error=str(e)))
        traceback.print_exc();sys.exit(1)
