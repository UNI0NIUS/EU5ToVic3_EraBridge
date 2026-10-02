'use strict';
const $ = id => document.getElementById(id);
const empty = () => ({source_location:'',reference_location:'',note:''});
let data,session,doc,current,selected=new Set(),picked='',form=empty(),maps={},epoch=0,storageKey='',forms={},busy=false,adjudications={};
const label = n => n ? `${data.sources[n]?.name || n} · ${n}` : '';
const rowFor = p => doc.entries[p] || {status:'pending',...empty()};
const reviewFingerprint = r => JSON.stringify([r.status||'pending',r.source_location||'',r.reference_location||'',r.note||'',r.review_round||'']);
const adjudicated = c => {const a=adjudications[c?.component];return Boolean(a?.status==='approved' && Object.entries(a.baseline_review_rows||{}).every(([p,r])=>reviewFingerprint(r)===reviewFingerprint(doc.entries[p]||{})));};
const confirmed = (p,c=current) => adjudicated(c) || rowFor(p).status==='mapped' && (!data.review_round || c?.review_scope!=='empty_parts' || rowFor(p).review_round===data.review_round);
const statusName = r => r.status==='mapped' && current?.review_scope==='empty_parts' && r.review_round!==data.review_round ? '旧标注·待复核' : r.status==='mapped' ? (data.sources[r.reference_location||r.source_location]?.evidence?'已匹配':'缺归属证据') : r.status==='deferred'?'暂缓':'待审';
function message(text,error=false){$('message').textContent=text;$('message').classList.toggle('error',error);}
function element(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
async function api(path,body){const res=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':session.token},body:JSON.stringify(body)}:undefined);const v=await res.json();if(!res.ok)throw Error(v.error||res.statusText);return v;}
function remember(){if(!current)return;form.note=$('note').value;forms[current.component]={...form};try{localStorage.setItem(storageKey,JSON.stringify(forms));}catch{message('浏览器草稿缓存不可用；请使用保存按钮写入本地文件。',true);}assignment();}
function assignment(){
  $('chosen-source').textContent=label(form.source_location)||'尚未指定';$('chosen-reference').textContent=label(form.reference_location)||'默认使用地理对应';
  const r=data.sources[form.reference_location||form.source_location];
  $('evidence').textContent=!r?'归属与主体民族随输入存档重新读取；不转移人口。':r.evidence?`1337 可用证据：${r.owner!=='0'?r.owner_name:'无主地区 · '+r.culture+'主体民族'}。换存档时重新读取。`:'此源地点在 1337 没有可用归属/人口证据。可保存地理匹配，但还需选择归属参考才能补齐预检。';
  if(r && data.reference_population_by_location && current?.review_scope==='empty_parts'){const n=form.reference_location||form.source_location;const amount=current.states.reduce((v,state)=>v+(data.reference_population_by_location[n]?.[state]||0),0)/100;$('evidence').textContent+=` 映射民族：${r.mapped_culture||'无'}。参考地点在当前州分配人口：${amount.toLocaleString('zh-CN')}；归属参考本身不会新增人口。`;}
  $('save').disabled=Boolean(current?.readonly)||busy||!selected.size||!form.source_location;$('defer').disabled=Boolean(current?.readonly)||busy||!selected.size;$('reset').disabled=Boolean(current?.readonly)||busy||!selected.size;
}
function renderQueue(){
  const entries=Object.values(doc.entries),matched=entries.filter(r=>r.status==='mapped').length,evidence=entries.filter(r=>r.status==='mapped'&&data.sources[r.reference_location||r.source_location]?.evidence).length;
  $('progress').textContent=data.review_round ? `${data.summary.empty_state_parts} 个空分州 · ${data.summary.rereview_provinces} 个地块 · 本轮已确认 ${data.components.filter(c=>c.review_scope==='empty_parts').reduce((n,c)=>n+c.provinces.filter(p=>confirmed(p,c)).length,0)} · 旧记录 ${entries.length} 条` : `${data.components.length} 个连通片 · ${data.summary.unresolved_provinces} 个原始缺口 · 已保存匹配 ${matched} · 有归属证据 ${evidence}`;
  const search=$('filter').value.trim().toLowerCase(),status=$('status-filter').value;$('queue').replaceChildren();
  for(const c of data.components){
    const scope=$('scope-filter').value;if(scope!=='all' && (c.review_scope||'original')!==scope)continue;
    const n=c.provinces.filter(p=>confirmed(p,c)).length,done=n===c.provinces.length;
    if(search&&!`${c.state_names} ${c.states} ${c.provinces}`.toLowerCase().includes(search))continue;
    if(status==='pending'&&done||status==='mapped'&&!done||status==='deferred'&&!c.provinces.some(p=>rowFor(p).status==='deferred'))continue;
    const b=element('button',`${c.state_names.join(' / ')} · ${c.provinces.length} 块`,'queue-item'+(current===c?' active':''));
    b.append(element('small',`${c.issue?(c.issue.type_name||'')+' · '+c.issue.owner+' · '+c.issue.culture:c.component} · ${c.review_scope==='empty_parts'?'本轮确认':'已匹配'} ${n}/${c.provinces.length}`));b.onclick=()=>choose(c);$('queue').append(b);
  }
}
function renderProvinces(){
  $('selected-count').textContent=`已选 ${selected.size}/${current.provinces.length}`;$('provinces').replaceChildren();
  for(const p of current.provinces){const l=element('label'),cb=element('input');cb.type='checkbox';cb.checked=selected.has(p);cb.setAttribute('aria-label',`选择 ${p}`);cb.onchange=()=>toggle(p);l.append(cb,element('span',p),element('small',statusName(rowFor(p))));$('provinces').append(l);}
  $('target-caption').textContent=`${current.state_names.join(' / ')} · ${current.component} · ${selected.size} 块选中 / ${current.provinces.length} 块同片`;
  assignment();maps.target.draw();
}
function toggle(p){if(!current.provinces.includes(p))return;selected.has(p)?selected.delete(p):selected.add(p);if(selected.size===1){const only=[...selected][0],r=doc.entries[only];if(r){form={...r};$('note').value=form.note;remember();}}renderProvinces();}
async function choose(c){
  if(current)remember();current=c;epoch++;const v=epoch;selected=new Set(c.provinces);picked='';
  const rows=c.provinces.map(p=>rowFor(p)),same=rows.every(r=>r.source_location===rows[0].source_location&&r.reference_location===rows[0].reference_location&&r.note===rows[0].note);
  form={...(forms[c.component]||(same?rows[0]:empty()))};$('note').value=form.note||'';
  const decision=adjudications[c.component];$('adjudication').hidden=!decision;if(decision)$('adjudication').textContent=`${adjudicated(c)?'核准':'标注已变更，需重核'}：${decision.title}。${decision.reason}`;
  $('review-issue').hidden=!c.issue;if(c.issue){$('review-issue').textContent=`当前归属：${c.issue.type_name||''} · ${c.issue.current_owner_name||c.issue.owner_name}（${c.issue.current_owner||c.issue.owner}） · 民族：${c.issue.culture}。本轮起始分州人口 ${(c.issue.baseline_population||0).toLocaleString('zh-CN')}；当前分州人口 ${(c.issue.current_population||0).toLocaleString('zh-CN')}。原国家全国有 ${c.issue.country_population.toLocaleString('zh-CN')} 人。${c.issue.reason}。请选择要保留的地理对应与归属参考。`;}
  $('group-title').textContent=`${c.state_names.join(' / ')} · ${c.provinces.length} 个地块`;
  $('source-detail').textContent='点击源地图或搜索地点。';$('search').value='';$('search-results').replaceChildren();maps.source.overlay=null;maps.target.overlay=null;
  $('candidates').replaceChildren();for(const n of c.candidates)$('candidates').append(sourceButton(n));
  renderQueue();renderProvinces();focusTarget();focusSource();history.replaceState(null,'','#'+c.component);
  try{const ov=await api('/api/component?id='+c.component);const im=await overlayImage(ov);if(epoch===v){maps.target.overlay=im;maps.target.draw();}}catch(e){message('连通片轮廓加载失败：'+e.message,true);}
}
function sourceButton(n){const r=data.sources[n],b=element('button',label(n),'source-result');b.append(element('small',`${r.type_name||'源国家'} · ${r.owner==='0'?'无主':r.owner_name} · ${r.barren?'荒地':r.culture||'无人口证据'}`));b.onclick=()=>pickSource(n,true);return b;}
let pickVersion=0;
async function pickSource(n,focus=false){
  if(!data.sources[n])return;picked=n;const r=data.sources[n],v=++pickVersion;maps.source.overlay=null;
  $('source-detail').replaceChildren(element('strong',label(n)),element('p',`${r.type_name||''} · ${r.owner==='0'?'无主':r.owner_name+'（源国家 '+r.owner+'）'} · ${r.barren?'不可居住荒地':'可居住地点'}`),element('p',`人口 ${Number(r.population).toLocaleString('zh-CN',{maximumFractionDigits:2})} · 主体民族 ${r.culture||'无'} · 映射民族 ${r.mapped_culture||'未显示'}`));
  $('source-caption').textContent=`${label(n)} · ${r.evidence?'本存档有可用归属证据':'本存档无可用归属证据'}`;
  if(focus)maps.source.focus(r.xy,Math.max(maps.source.scale,1.4));maps.source.draw();
  try{const ov=await api('/api/highlight?map=source&key='+encodeURIComponent(n));const im=await overlayImage(ov);if(v===pickVersion){maps.source.overlay=im;maps.source.draw();}}catch(e){message(e.message,true);}
}
async function overlayImage(ov){if(!ov.box)return null;const img=new Image();img.src=ov.image;await img.decode();return {box:ov.box,img};}
function focusTarget(){const points=current.provinces.flatMap(p=>data.targets[p].view_points||[data.targets[p].xy]);maps.target.fit(points);}
function focusSource(){const n=form.source_location;maps.source.focus(n?data.sources[n].xy:current.source_guess,1.4);if(n)pickSource(n);else{$('source-caption').textContent='按邻近已映射地块定位；仅供导航，不代表审定对应。';maps.source.draw();}}
async function save(status){
  if(busy||current?.readonly||!selected.size)return;remember();const entries={};for(const p of selected){entries[p]=status==='pending'?{...empty(),status}:{...form,status};if(data.review_round)entries[p].review_round=data.review_round;}
  busy=true;assignment();
  try{doc=await api('/api/save',{revision:doc.revision,entries});$('save-status').textContent=`已保存 ${selected.size} 个地块 · 本地版本 ${doc.revision}`;message(`已写入本地 terrain_reviews.json，版本 ${doc.revision}。可继续补充其他地块。`);renderQueue();renderProvinces();}
  catch(e){message('保存失败：'+e.message,true);}finally{busy=false;assignment();}
}
function next(){const i=data.components.indexOf(current);for(let k=1;k<=data.components.length;k++){const c=data.components[(i+k)%data.components.length];if(($('scope-filter').value==='all'||(c.review_scope||'original')===$('scope-filter').value)&&c.provinces.some(p=>!confirmed(p,c))){choose(c);return;}}message('全部地块已有匹配记录；缺少源证据的记录仍需补充归属参考。');}

class MapView{
  constructor(kind,img){this.kind=kind;this.canvas=$(kind+'-map');this.ctx=this.canvas.getContext('2d');this.img=img;this.size=data[kind+'_size'];this.center=[...this.size].map(v=>v/2);this.scale=.12;this.overlay=null;
    const c=this.canvas;new ResizeObserver(()=>this.resize()).observe(c);
    c.addEventListener('wheel',e=>{e.preventDefault();const r=c.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top,old=this.scale;this.scale=Math.min(30,Math.max(.045,old*Math.exp(-e.deltaY*.0015)));this.center[0]+=(x-this.w/2)*(1/old-1/this.scale);this.center[1]+=(y-this.h/2)*(1/old-1/this.scale);this.normalize();this.draw();},{passive:false});
    c.onpointerdown=e=>{c.focus();this.drag={x:e.clientX,y:e.clientY,c:[...this.center],moved:false};c.setPointerCapture(e.pointerId);};
    c.onpointermove=e=>{if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(Math.abs(dx)+Math.abs(dy)>4)this.drag.moved=true;this.center=[this.drag.c[0]-dx/this.scale,this.drag.c[1]-dy/this.scale];this.normalize();this.draw();};
    c.onpointerup=e=>{const d=this.drag;this.drag=null;if(d&&!d.moved){const r=c.getBoundingClientRect();this.hit(e.clientX-r.left,e.clientY-r.top);}};
    c.onpointercancel=()=>{this.drag=null;};
    c.onkeydown=e=>{const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];if(delta){e.preventDefault();this.center[0]+=delta[0]*80/this.scale;this.center[1]+=delta[1]*80/this.scale;this.normalize();this.draw();}};
    this.resize();
  }
  normalize(){this.center[0]=(this.center[0]%this.size[0]+this.size[0])%this.size[0];this.center[1]=Math.max(0,Math.min(this.size[1],this.center[1]));}
  resize(){const r=this.canvas.getBoundingClientRect();this.w=r.width;this.h=r.height;const d=window.devicePixelRatio||1;this.canvas.width=Math.round(r.width*d);this.canvas.height=Math.round(r.height*d);this.ctx.setTransform(d,0,0,d,0,0);this.draw();}
  focus(xy,scale){this.center=[...xy];this.scale=scale;this.normalize();this.draw();}
  world(){this.focus(this.size.map(v=>v/2),Math.min(this.w/this.size[0],this.h/this.size[1])*.97);}
  fit(points){const width=this.size[0],a=points[0][0],xs=points.map(p=>a+((p[0]-a+width*1.5)%width)-width/2),ys=points.map(p=>p[1]),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);this.focus([(xmin+xmax)/2,(ymin+ymax)/2],Math.min(8,(this.w-65)/Math.max(55,xmax-xmin+40),(this.h-40)/Math.max(55,ymax-ymin+40)));}
  point(xy){let dx=xy[0]-this.center[0];dx=(dx+this.size[0]*1.5)%this.size[0]-this.size[0]/2;return [this.w/2+dx*this.scale,this.h/2+(xy[1]-this.center[1])*this.scale];}
  dot(xy,color,r=4,text=''){const [x,y]=this.point(xy),c=this.ctx;if(x < -20||x>this.w+20||y < -20||y>this.h+20)return;c.beginPath();c.arc(x,y,r,0,Math.PI*2);c.fillStyle='#13232bcc';c.fill();c.strokeStyle=color;c.lineWidth=2;c.stroke();if(text){c.font='11px "Microsoft YaHei"';c.lineWidth=3;c.strokeStyle='#10212d';c.strokeText(text,x+8,y-5);c.fillStyle=color;c.fillText(text,x+8,y-5);}}
  draw(){if(!this.w)return;const c=this.ctx,s=this.scale,[width,height]=this.size;c.clearRect(0,0,this.w,this.h);c.fillStyle='#142739';c.fillRect(0,0,this.w,this.h);c.imageSmoothingEnabled=false;
    const extent=Math.ceil(this.w/(width*s))+1;for(let k=-extent;k<=extent;k++){const x=this.w/2+(k*width-this.center[0])*s,y=this.h/2-this.center[1]*s;c.drawImage(this.img,x,y,width*s,height*s);if(this.overlay){const [bx,by,bw,bh]=this.overlay.box;c.drawImage(this.overlay.img,x+bx*s,y+by*s,bw*s,bh*s);}}
    if(!current)return;
    if(this.scale>.45){const used=[];const labels=this.kind==='target'?(data.target_labels||[]):(data.source_labels||[]);const named=new Set();for(const r of labels){const [x,y]=this.point(r.xy);if(x<10||x>this.w-15||y<15||y>this.h-15||named.has(r.text)||used.some(p=>Math.abs(p[0]-x)<145&&Math.abs(p[1]-y)<32))continue;c.font='11px "Microsoft YaHei"';c.lineWidth=3;c.strokeStyle='#17242c';c.strokeText(r.text,x,y);c.fillStyle='#f8f0da';c.fillText(r.text,x,y);used.push([x,y]);named.add(r.text);if(used.length>=18)break;}}
    if(this.kind==='target'){for(const p of current.provinces){const marks=data.targets[p].markers||[data.targets[p].xy];for(const xy of marks)this.dot(xy,selected.has(p)?'#69ffe8':'#fff',selected.has(p)?6:4,current.provinces.length===1||this.scale>4?p:'');}}
    else{if(form.source_location)this.dot(data.sources[form.source_location].xy,'#69ffe8',6,data.sources[form.source_location].name);if(form.reference_location)this.dot(data.sources[form.reference_location].xy,'#cbabff',6,data.sources[form.reference_location].name);if(picked)this.dot(data.sources[picked].xy,'#ffc44b',7,data.sources[picked].name);}
  }
  async hit(x,y){const v=epoch,w=this.size[0],px=((this.center[0]+(x-this.w/2)/this.scale)%w+w)%w,py=this.center[1]+(y-this.h/2)/this.scale;if(py<0||py>=this.size[1])return;
    try{const r=await api(`/api/hit?map=${this.kind}&x=${px}&y=${py}`);if(v!==epoch)return;if(!r.key){message('此处没有可选陆地；极小岛屿可使用搜索或地块列表定位。');return;}
      if(this.kind==='source')pickSource(r.key);else if(current.provinces.includes(r.key))toggle(r.key);else{const group=data.components.find(c=>c.provinces.includes(r.key));if(group)choose(group);else{const t=data.targets[r.key];$('target-caption').textContent=`${t.state_name} · ${r.key} · ${t.type_name||''} · ${t.owner_name} · ${t.kind==='land_inferred'?'沿陆地补全':'有源锚点'}`;message('该目标地块已有规划归属。可以切换左侧审查批次；本轮只编辑已列出的待审地块。');}}
    }catch(e){message(e.message,true);}
  }
}

async function init(){
  [data,session,adjudications]=await Promise.all([api('/api/data'),api('/api/session'),api('/api/adjudications')]);doc=session.reviews;
  storageKey='terrain-forms:'+data.source_map_sha256+':'+data.target_map_sha256+':'+(data.review_round||'original');
  if(!data.review_round){$('scope-filter').value='all';$('scope-filter').hidden=true;}
  try{forms=JSON.parse(localStorage.getItem(storageKey)||'{}');}catch{forms={};}
  for(const kind of ['source','target']){const im=new Image();im.src=`/${kind}-map.png`;await im.decode();maps[kind]=new MapView(kind,im);$(kind+'-world').onclick=()=>maps[kind].world();}
  $('scope-filter').onchange=()=>{renderQueue();const c=data.components.find(c=>$('scope-filter').value==='all'||(c.review_scope||'original')===$('scope-filter').value);if(c)choose(c);};$('filter').oninput=renderQueue;$('status-filter').onchange=renderQueue;
  $('source-focus').onclick=focusSource;$('target-focus').onclick=focusTarget;
  $('all').onclick=()=>{selected=new Set(current.provinces);renderProvinces();};$('none').onclick=()=>{selected.clear();renderProvinces();};
  $('search').oninput=()=>{const q=$('search').value.trim().toLowerCase();$('search-results').replaceChildren();if(!q)return;let count=0;for(const [n,r] of Object.entries(data.sources))if(`${n} ${r.name} ${r.english}`.toLowerCase().includes(q)){if(count++===30){$('search-results').append(element('p','结果超过 30 条，请细化关键词。','muted'));break;}$('search-results').append(sourceButton(n));}if(!count)$('search-results').append(element('p','没有找到地点。','muted'));};
  $('use-source').onclick=()=>{if(!picked){message('请先点击源地图或搜索结果。');return;}form.source_location=picked;remember();maps.source.draw();};
  $('use-reference').onclick=()=>{if(!picked){message('请先点击源地图或搜索结果。');return;}form.reference_location=picked;remember();maps.source.draw();};
  $('clear-reference').onclick=()=>{form.reference_location='';remember();maps.source.draw();};$('note').oninput=remember;
  $('save').onclick=()=>save('mapped');$('defer').onclick=()=>save('deferred');$('reset').onclick=()=>save('pending');$('next').onclick=next;
  $('refresh-review').onclick=async()=>{const key=current.component;[data,session,adjudications]=await Promise.all([api('/api/data'),api('/api/session'),api('/api/adjudications')]);doc=session.reviews;await choose(data.components.find(c=>c.component===key)||data.components[0]);message('核准记录与归属类型已刷新。');};
  setInterval(async()=>{if(busy)return;try{const a=await api('/api/adjudications');if(JSON.stringify(a)!==JSON.stringify(adjudications)){adjudications=a;renderQueue();const d=a[current.component];$('adjudication').hidden=!d;if(d)$('adjudication').textContent=`${adjudicated(current)?'核准':'标注已变更，需重核'}：${d.title}。${d.reason}`;}const next=await api('/api/session');if(next.reviews.revision!==doc.revision){session=next;doc=next.reviews;renderQueue();renderProvinces();}}catch{}},5000);
  $('help').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();
  $('export').onclick=()=>{const blob=new Blob([JSON.stringify(doc,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download='terrain_reviews.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message(`已导出已保存版本 ${doc.revision}；尚未点击保存的表单不在导出中。`);};
  $('import').onchange=async e=>{try{if(!e.target.files[0])return;const document=JSON.parse(await e.target.files[0].text());doc=await api('/api/import',{revision:doc.revision,document});renderQueue();renderProvinces();message(`导入完成，当前版本 ${doc.revision}。`);}catch(err){message('导入失败：'+err.message,true);}finally{e.target.value='';}};
  await choose(data.components.find(c=>c.component===location.hash.slice(1)||c.provinces.includes(location.hash.slice(1)))||data.components[0]);
  message(data.review_round?'本轮空分州复核已载入；旧标注保留。可重新选择后保存，也可沿用旧选择并点保存确认。候选模组等待复核完成后重建。':'已加载 1337 真实源证据。选择目标地块 → 指定源地点 → 保存匹配。');
}
init().catch(e=>message('工作站加载失败：'+e.message,true));
