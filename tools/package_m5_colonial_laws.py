"""Bounded colonial-law patch on the latest installed M5; installation is separate."""
from datetime import datetime
from pathlib import Path
import html
import json
import re
import shutil

from build_m2_prototype import patch, replace_body
from deploy_political_rules import countries
from m3_world import digest
from package_m4_population_test import GAME
from package_m5_culture_refinement import files

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT/'config/personal/m5_colonial_law_corrections.json'
HISTORY = 'common/history/countries/00_eu5_world.txt'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p, data): p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def build():
    installation = read(ROOT/'.local/m5/installation-latest.json')
    assert installation == read(ROOT/'.local/economy/installation-latest.json')
    prior = Path(installation['package']); previous = read(prior/'package_report.json')
    base = Path(installation['target'])
    assert files(base) == previous['output_sha256'], 'Installed baseline changed'
    policy = read(POLICY)
    output = ROOT/'.local/economy/packages'/('m5-colonial-laws-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    mod = output/'eu5_economy_test'; shutil.copytree(base, mod)
    text = (mod/HISTORY).read_text(encoding='utf-8-sig'); bodies = countries(text)
    changes = []
    for tag,spec in policy['countries'].items():
        body = bodies[tag].text()
        law_pattern = r'(?m)^(\s*activate_law\s*=\s*law_type:)'+re.escape(spec['old_law'])+r'\s*$'
        body,n = re.subn(law_pattern,lambda m:m[1]+spec['law'],body)
        assert n==1, ('Unexpected existing law',tag,n)
        institution_pattern = r'(?m)^\s*set_institution_investment_level\s*=\s*\{\s*institution\s*=\s*institution_colonial_affairs\s+level\s*=\s*'+str(spec['old_institution_level'])+r'\s*\}\s*$'
        body,n = re.subn(institution_pattern,'',body)
        assert n==1, ('Unexpected existing institution',tag,n)
        changes.append(replace_body(bodies[tag], body))
    (mod/HISTORY).write_text(patch(text,changes),encoding='utf-8-sig')
    meta = read(mod/'.metadata/metadata.json')
    a,b,c,t = map(int,re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-m5-test(\d+)',installation['version']).groups())
    meta['version']=f'{a}.{b}.{c+1}-m5-test{t+1}'; write(mod/'.metadata/metadata.json',meta)
    write(output/'policy.snapshot.json',policy)
    # Preserve original population provenance for later packages without redoing calibration.
    assert (prior/'original_population.txt').exists()
    shutil.copy2(prior/'original_population.txt',output/'original_population.txt')
    inputs=[POLICY,Path(__file__),ROOT/'tools/verify_m5_colonial_laws.py',ROOT/'tools/build_political_rules_report.py',
            ROOT/'tools/update_m5_integrated_test.ps1',ROOT/'.local/m3/politics.json',
            prior/'package_report.json',Path(previous['political_run'])/'conversion_report.json',
            Path(previous['political_run'])/'province_owners.json',ROOT/'.local/m3/cache/tribal_land_edges.json',
            GAME/'common/laws/01_colonial_affairs.txt',GAME/'common/defines/00_defines.txt',
            GAME/'map_data/provinces.png',GAME/'map_data/adjacencies.csv',GAME/'map_data/default.map']
    current=files(mod)
    changed=sorted(k for k,v in current.items() if previous['output_sha256'].get(k)!=v)
    assert set(changed)=={HISTORY,'.metadata/metadata.json'}
    report={k:previous[k] for k in ['political_run','demographic_run','population_mode','population_calibrated','source_population_conserved']}
    report.update(status='colonial_laws_candidate',update_scope='m5_colonial_laws',version=meta['version'],mod_name=meta['name'],
        mod_directory=str(mod),prior_package=str(prior),new_campaign_required=True,changed_files=changed,
        input_sha256={str(p.resolve()):digest(p) for p in inputs},output_sha256=current,
        original_population_sha256=digest(output/'original_population.txt'),
        colonial_law_policy=str(output/'policy.snapshot.json'))
    write(output/'package_report.json',report)
    from verify_m5_colonial_laws import verify
    verified=verify(output)
    page='''<!doctype html><meta charset="utf-8"><title>M5 殖民法律修正</title>
<style>body{font:17px/1.8 system-ui;max-width:1050px;margin:32px auto;background:#f1f5f9;color:#23364a}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #cbd5e1}pre{white-space:pre-wrap}</style>
<h1>M5 殖民法律修正 · '''+meta['version']+'''</h1>
<p>修复把建筑型贸易公司当作领土殖民属国、自动授予殖民机构的证据错误。</p>
<table><tr><th>国家</th><th>修正前</th><th>修正后</th></tr><tr><td>克什米尔 KAS</td><td>殖民剥削／2级</td><td>无殖民事务／无机构</td></tr><tr><td>高丽 KOR</td><td>殖民剥削／2级</td><td>无殖民事务／无机构</td></tr></table>
<p>保留现有技术、行政建筑及其余主要国家法律。无殖民事务原版自带本土接纳度+10；移除殖民机构减少其行政需求，不声称全局经济预算已经实测。</p>
<p>俄罗斯／满洲按最新国界和现有主流文化本土检查，未取得满足原版边疆立法条件的见证，因此保持原法律；未改文化本土或放宽原版触发器。</p>
<p>人口、居民身份、识字率、国界、本土、经济文件及外交关系均保持。请新开档测试，游戏内运行验证尚待完成。</p>
<p><a href="verification.json">独立验证</a> · <a href="colonial_law_evidence.json">源关系与边疆检查</a> · <a href="policy.snapshot.json">显式政策</a> · <a href="installation.json">安装结果</a></p><pre>'''+html.escape(json.dumps(verified['colonial_laws'],ensure_ascii=False,indent=2))+'</pre>'
    (output/'index.html').write_text(page,encoding='utf-8')
    write(ROOT/'.local/m5/colonial-law-package-latest.json',dict(package=str(output),version=meta['version']))
    print(json.dumps(dict(package=str(output),version=meta['version'],verification=verified['colonial_laws']),ensure_ascii=False,indent=2))


if __name__=='__main__': build()
