'use strict';
const $=id=>document.getElementById(id), fmt=n=>n==null?'未知':new Intl.NumberFormat('zh-CN',{maximumFractionDigits:0}).format(n), pct=n=>n==null?'未知':(n*100).toFixed(1)+'%';
const percentKeys=new Set(['workforce_share','staffing','unemployment_threshold','food_shortfall_threshold']);
const riskNames={arable:'低耕地',unemployment:'严重失业',food:'食物不足'};
let pickingTarget=false,closed=false;
let token='',project=null,preview=null,defaults=null,selected=null,view='country',filter='all',busy=false,lastJob='',pendingMerge=null,toastTimer;
let mapImage=null,highlight=null,highlightBox=null,marker=null,scale=1,offset={x:0,y:0},drag=null,mapVersion=0,selectionVersion=0;
const canvas=$('map'),ctx=canvas.getContext('2d');
function notify(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6500)}
async function api(path,body){const r=await fetch('/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Converter-Token':token},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||r.statusText);return d}
function guard(fn){return async(...args)=>{try{await fn(...args)}catch(e){notify(e.message)}}}
function status(job){busy=job.status==='running';$('status').textContent=job.message;$('statusDot').className=busy?'busy':job.status==='failed'?'failed':'';
for(const id of ['export','apply','downloadProject','restore'])$(id).disabled=busy||!project;$('undo').disabled=busy||!project?.merges.length;$('merge').disabled=busy||!$('mergeTarget').value;
$('load').disabled=busy;$('convert').disabled=busy;
if(job.result?.directory){$('outputLink').hidden=false;$('outputLink').textContent='打开本次候选包';$('outputLink').title=job.result.directory;$('outputLink').onclick=guard(async()=>{const d=await api('load',{package:job.result.directory,game:project?.game||$('convertGame').value||defaults.game,name:'转换结果 · '+new Date().toLocaleDateString()});mapImage=null;selected=null;highlight=null;status(d.job)})}
}
function adopt(data){project=data.project;preview=data.preview;status(data.job);if(!project||!preview)return;
$('projectName').textContent=project.name+' · '+preview.source_date;$('empty').hidden=true;
for(const [key,value] of Object.entries(project.settings)){const el=$('settings').elements.namedItem(key);if(el)el.value=percentKeys.has(key)?Math.round(value*100):value}
const s=preview.summary;$('statWorld').textContent=fmt(s.countries)+' / '+fmt(s.regions);$('statArable').textContent=fmt(s.arable_alerts||0);$('statJobs').textContent=fmt(s.unemployment_alerts||0);$('statFood').textContent=fmt(s.food_alerts||0);
document.querySelector('[data-filter="arable"]').textContent='耕地 ≤ '+project.settings.small_arable;
$('assumptions').replaceChildren(...preview.assumptions.map(text=>{const p=document.createElement('p');p.textContent=text;return p}));
$('mergeCount').textContent=project.merges.length;$('mergeHistory').replaceChildren(...project.merges.map(o=>{const li=document.createElement('li');li.textContent=`${o.source} → ${o.target} · ${o.kind==='country'?'整个国家':o.state}`;return li}));
if(selected&&!preview.rows.some(r=>r.id===selected)){selected=null;highlight=null;marker=null}
renderTable();renderSelection();loadMap();
}
function badges(row){const box=document.createElement('div');box.className='badges';for(const key of row.risks){const tag=document.createElement('span');tag.className='badge '+key;tag.textContent=riskNames[key];box.append(tag)}return box}
function renderTable(){if(!preview)return;const query=$('search').value.trim().toLowerCase();let rows=preview.rows.filter(r=>(filter==='every'||filter==='all'&&r.risks.length||r.risks.includes(filter))&&[r.state,r.country,r.state_name,r.country_name].join(' ').toLowerCase().includes(query));
rows.sort((a,b)=>b.risks.length-a.risks.length||(b.food_shortfall||0)-(a.food_shortfall||0)||a.id.localeCompare(b.id));$('riskCount').textContent=rows.length;
$('riskRows').replaceChildren(...rows.slice(0,250).map(r=>{const tr=document.createElement('tr');if(r.id===selected)tr.className='selected';tr.onclick=guard(()=>select(r.id,true));
const name=document.createElement('td');name.append(document.createTextNode(r.state_name));const small=document.createElement('small');small.textContent=r.country_name+' · '+r.country;name.append(small);tr.append(name);
for(const text of [fmt(r.population),fmt(r.arable),pct(r.estimated_unemployment),pct(r.food_shortfall)]){const td=document.createElement('td');td.textContent=text;tr.append(td)}const td=document.createElement('td');td.append(badges(r));tr.append(td);return tr}));
$('more').textContent=rows.length>250?`显示前 250 项，共 ${fmt(rows.length)} 项；可搜索缩小范围。`:rows.length?'点击一行，在地图中定位。':'没有符合当前筛选条件的地区。';}
function rowById(id){return preview?.rows.find(r=>r.id===id)}
function renderSelection(){const r=rowById(selected);$('selection').hidden=!r;$('selectionEmpty').hidden=!!r;if(!r)return;
$('selectedTag').textContent=r.state+' / '+r.country;$('selectedName').textContent=r.state_name;$('selectedCountry').textContent=r.country_name;$('selectedRisks').replaceChildren(badges(r));
const pairs=[['人口',fmt(r.population)],['分得耕地',fmt(r.arable)],['地块数',fmt(r.province_count)],['估算岗位容量',fmt(r.job_capacity)],['严重失业缺口',pct(r.estimated_unemployment)],['本地食物缺口',pct(r.food_shortfall)],['全国食物缺口',pct(r.country_food_shortfall)]];
$('metrics').replaceChildren(...pairs.flatMap(([k,v])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=k;dd.textContent=v;return[dt,dd]}));fillTargets();}
function fillTargets(){const r=rowById(selected);if(!r)return;const kind=$('mergeKind').value;let choices=[];
if(kind==='region')choices=r.neighbors.map(rowById).filter(v=>v&&v.state===r.state&&v.country!==r.country);
else{const adjacent=new Set(preview.rows.filter(v=>v.country===r.country).flatMap(v=>v.neighbors));choices=[...adjacent].map(rowById).filter(v=>v&&v.country!==r.country)}
const tags=new Map();for(const c of choices)if(!tags.has(c.country))tags.set(c.country,c);const old=$('mergeTarget').value;
$('mergeTarget').replaceChildren(...[...tags.values()].sort((a,b)=>a.country_name.localeCompare(b.country_name,'zh-CN')).map(c=>{const o=document.createElement('option');o.value=c.country;o.textContent=c.country_name+' · '+c.country;return o}));
if(tags.has(old))$('mergeTarget').value=old;compare();}
function compare(){const source=rowById(selected),target=$('mergeTarget').value;if(!source)return;$('merge').disabled=busy||!target;
if(!target){$('mergeComparison').textContent='当前范围没有可用的相邻目标。可以切换“整个国家合并”查看跨州相邻国家。';return}
const rows=preview.rows.filter(r=>$('mergeKind').value==='region'?r.state===source.state&&[source.country,target].includes(r.country):[source.country,target].includes(r.country));
const pop=rows.reduce((n,r)=>n+r.population,0),land=rows.reduce((n,r)=>n+r.arable,0),capacity=rows.some(r=>r.job_capacity==null)?null:rows.reduce((n,r)=>n+r.job_capacity,0);
$('mergeComparison').textContent=`涉及 ${fmt(pop)} 人，现有耕地合计 ${fmt(land)}，现有岗位容量 ${fmt(capacity)}。合并后会按保留国家的法律重新计算自给农业；跨州岗位无法自动互通。`;}
async function select(id,focus=false){if(pickingTarget){const r=rowById(id),option=[...$('mergeTarget').options].find(o=>o.value===r?.country);if(!option){notify('该地区不属于当前可合并的相邻目标，请重新点选');return}$('mergeTarget').value=option.value;pickingTarget=false;$('pickTarget').textContent='在地图上点选目标';compare();notify('已选择目标：'+option.textContent);return}selected=id;renderTable();renderSelection();const version=++selectionVersion;const d=await api('region?id='+encodeURIComponent(id));if(version!==selectionVersion)return;
const img=await image(d.image);if(version!==selectionVersion)return;highlight=img;highlightBox=d.box;marker=d.xy;if(focus){const [x,y,w,h]=d.focus;scale=Math.min(3,Math.max(fitScale(),Math.min(canvas.clientWidth/(w+160),canvas.clientHeight/(h+160))));offset={x:canvas.clientWidth/2-(x+w/2)*scale,y:canvas.clientHeight/2-(y+h/2)*scale}}draw();}
function image(src){return new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(Error('地图图像载入失败'));img.src=src})}
async function loadMap(){const version=++mapVersion;try{const img=await image('/api/map?view='+view+'&revision='+project.revision+'&project='+project.id);if(version!==mapVersion)return;const first=!mapImage;mapImage=img;if(first)home();else draw();$('mapLegend').lastElementChild.textContent=view==='country'?'国家归属 · 金色为选区':'珊瑚色：触发提醒 · 灰色：数据未知 · 金色：选区'}catch(e){notify(e.message)}}
function fitScale(){return Math.min(canvas.clientWidth/8192,canvas.clientHeight/4096)}
function home(){scale=fitScale();offset={x:(canvas.clientWidth-8192*scale)/2,y:(canvas.clientHeight-4096*scale)/2};draw()}
function resize(){const dpr=window.devicePixelRatio||1;canvas.width=canvas.clientWidth*dpr;canvas.height=canvas.clientHeight*dpr;draw()}
function draw(){const dpr=window.devicePixelRatio||1;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,canvas.clientWidth,canvas.clientHeight);if(!mapImage)return;ctx.imageSmoothingEnabled=false;ctx.drawImage(mapImage,offset.x,offset.y,8192*scale,4096*scale);
if(highlight&&highlightBox){const[x,y,w,h]=highlightBox;ctx.drawImage(highlight,offset.x+x*scale,offset.y+y*scale,w*scale,h*scale)}
if(marker){ctx.strokeStyle='#ffe3a0';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(offset.x+marker[0]*scale,offset.y+marker[1]*scale,8,0,Math.PI*2);ctx.stroke()}}
function zoom(factor,x=canvas.clientWidth/2,y=canvas.clientHeight/2){const next=Math.min(12,Math.max(fitScale()*.65,scale*factor));offset={x:x-(x-offset.x)*next/scale,y:y-(y-offset.y)*next/scale};scale=next;draw()}
canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.18:1/1.18,e.clientX-r.left,e.clientY-r.top)},{passive:false});
canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;canvas.setPointerCapture(e.pointerId);drag={x:e.clientX,y:e.clientY,ox:offset.x,oy:offset.y,moved:false}});
canvas.addEventListener('pointermove',e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.moved||=Math.abs(dx)+Math.abs(dy)>4;offset={x:drag.ox+dx,y:drag.oy+dy};draw()});
canvas.addEventListener('pointerup',guard(async e=>{const d=drag;drag=null;if(!d||d.moved||!preview)return;const r=canvas.getBoundingClientRect();const hit=await api(`hit?x=${(e.clientX-r.left-offset.x)/scale}&y=${(e.clientY-r.top-offset.y)/scale}`);if(hit.id)await select(hit.id)}));
canvas.addEventListener('pointercancel',()=>drag=null);canvas.addEventListener('keydown',e=>{const keys={ArrowLeft:[30,0],ArrowRight:[-30,0],ArrowUp:[0,30],ArrowDown:[0,-30]};if(keys[e.key]){e.preventDefault();offset.x+=keys[e.key][0];offset.y+=keys[e.key][1];draw()}});
new ResizeObserver(resize).observe($('mapContainer'));
async function openDialog(){const d=await api('session');defaults=d.defaults;$('savedProjects').replaceChildren(new Option('新建项目',''),...defaults.projects.map(p=>new Option(p.name,p.id)));$('candidates').replaceChildren(new Option('手动选择目录',''),...defaults.candidates.map(p=>new Option((p.date?p.date+' · ':'')+p.name,p.path)));$('gameInput').value=defaults.game;$('openError').textContent='';$('newFields').hidden=false;if(defaults.candidates.length){$('candidates').value=defaults.candidates[0].path;$('packageInput').value=defaults.candidates[0].path}$('openDialog').showModal()}
$('openProject').onclick=guard(openDialog);$('emptyOpen').onclick=guard(openDialog);$('candidates').onchange=()=>$('packageInput').value=$('candidates').value;$('savedProjects').onchange=()=>$('newFields').hidden=!!$('savedProjects').value;
for(const b of document.querySelectorAll('[data-close]'))b.onclick=()=>$(b.dataset.close).close();
for(const b of document.querySelectorAll('[data-pick]'))b.onclick=guard(async()=>{const d=await api('pick',{kind:b.dataset.kind||'file'});if(d.path)$(b.dataset.pick).value=d.path});
$('load').onclick=async()=>{try{$('load').disabled=true;const d=await api('load',{id:$('savedProjects').value,name:$('nameInput').value,package:$('packageInput').value,game:$('gameInput').value});mapImage=null;highlight=null;selected=null;$('openDialog').close();status(d.job)}catch(e){$('openError').textContent=e.message;$('load').disabled=false}};
$('settings').onsubmit=guard(async e=>{e.preventDefault();const data={};for(const [k,v]of new FormData(e.target)){data[k]=Number(v)/(percentKeys.has(k)?100:1)}adopt(await api('settings',{revision:project.revision,settings:data}));if(selected)await select(selected);notify('参数已保存，风险已重新计算')});
$('search').oninput=renderTable;$('filters').onclick=e=>{const b=e.target.closest('button');if(!b)return;filter=b.dataset.filter;for(const el of $('filters').children)el.classList.toggle('active',el===b);renderTable()};
$('layers').onclick=e=>{const b=e.target.closest('button');if(!b)return;view=b.dataset.view;for(const el of $('layers').children)el.classList.toggle('active',el===b);if(project)loadMap()};
$('zoomIn').onclick=()=>zoom(1.4);$('zoomOut').onclick=()=>zoom(1/1.4);$('home').onclick=home;$('mergeKind').onchange=fillTargets;$('mergeTarget').onchange=compare;
$('merge').onclick=()=>{const row=rowById(selected),target=$('mergeTarget').value;if(!target||!row)return;pendingMerge={kind:$('mergeKind').value,source:row.country,target};if(pendingMerge.kind==='region')pendingMerge.state=row.state;$('confirmText').textContent=`将 ${row.country_name}（${row.country}）的${pendingMerge.kind==='country'?'全部领土':row.state_name+'地区'}并入 ${$('mergeTarget').selectedOptions[0].textContent}。`;$('confirmDialog').showModal()};
$('confirmMerge').onclick=guard(async()=>{const d=await api('merge',{revision:project.revision,operation:pendingMerge});const next=pendingMerge.kind==='region'?pendingMerge.state+'|'+pendingMerge.target:null;$('confirmDialog').close();adopt(d);if(next)await select(next,true);notify('合并决定已保存，可以撤销')});
$('undo').onclick=guard(async()=>{adopt(await api('undo',{revision:project.revision}));notify('最近一次合并已撤销')});
$('restore').onclick=guard(async()=>{if(!confirm('恢复初始参数并清空本项目的合并决定？历史记录仍会保留。'))return;adopt(await api('restore',{revision:project.revision}));notify('初始方案已恢复')});
$('downloadProject').onclick=()=>{const blob=new Blob([JSON.stringify(project,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='conversion-project.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
$('export').onclick=guard(async()=>{const d=await api('export',{revision:project.revision});status(d.job)});
$('newConvert').onclick=()=>{$('eu5Input').value=defaults.eu5;$('convertGame').value=project?.game||defaults.game;$('rulesInput').value=defaults.workspace.replace(/\\/g,'/')+'/rules/manifest.json';$('convertError').textContent='';$('convertDialog').showModal()};
$('convert').onclick=async()=>{try{const d=await api('convert',{save:$('saveInput').value,eu5:$('eu5Input').value,game:$('convertGame').value,rules:$('rulesInput').value,mods:$('modsInput').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)});$('convertDialog').close();status(d.job)}catch(e){$('convertError').textContent=e.message}};
async function poll(){if(closed)return;try{const d=await api('status');if(closed)return;status(d.job);if(d.job.status!=='running'&&d.job.id&&lastJob!==d.job.id){lastJob=d.job.id;if(d.project_id&&(d.project_id!==project?.id||d.revision!==project?.revision))adopt(await api('project'));if(d.job.status==='failed')notify(d.job.message);if(d.job.result?.directory)notify('已生成独立候选包：'+d.job.result.directory)}}catch(e){if(!closed)$('status').textContent='无法连接本机服务，请重新启动转换工作台。'}finally{if(!closed)setTimeout(poll,1600)}}
guard(async()=>{const d=await api('session');token=d.token;defaults=d.defaults;adopt(d);poll()})();

$('quit').onclick=guard(async()=>{await api('shutdown',{});closed=true;$('status').textContent='软件已退出，可以关闭此页面。';notify('转换工作台已退出')});

$('pickTarget').onclick=()=>{pickingTarget=!pickingTarget;$('pickTarget').textContent=pickingTarget?'取消地图选目标':'在地图上点选目标';if(pickingTarget)notify('现在点击地图中的相邻国家，或点击列表中的目标地区')};
