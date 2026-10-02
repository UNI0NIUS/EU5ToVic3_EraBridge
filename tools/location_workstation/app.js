'use strict';
const $ = id => document.getElementById(id);
const fmt = n => new Intl.NumberFormat('zh-CN', {maximumFractionDigits: 2}).format(n);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const label = {pending:'未处理', mapped:'已完成', deferred:'暂缓'};
let data, reviews, token, current, chosen=[], dirty=false, saving=false, maps={}, drafts={}, draftKey, activeReference=null;
let filtered=[], highlightCache=new Map(), toastTimer, searchTimer, selectedVersion=0;

async function api(path, body) {
  const options=body ? {method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':token},body:JSON.stringify(body)} : {};
  const r=await fetch(path,options), result=await r.json();
  if(!r.ok) throw new Error(result.error || `请求失败 ${r.status}`);
  return result;
}
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,6500); }
function state(id) { return reviews.entries[id]?.status || 'pending'; }
function remember() {
  if(!current || !dirty) return;
  drafts[current.id]={targets:structuredClone(chosen),note:$('note').value};
  try { localStorage.setItem(draftKey,JSON.stringify(drafts)); } catch { $('save-state').textContent='浏览器草稿缓存不可用，请及时保存到本机。'; }
}
function markDirty() { dirty=true; $('save-state').textContent='有未保存修改 · 已暂存浏览器草稿'; remember(); }
function clearDraft(id) { delete drafts[id]; try {localStorage.setItem(draftKey,JSON.stringify(drafts));} catch {} }
function renderQueue() {
  const q=$('search').value.trim().toLowerCase(), f=$('filter').value;
  filtered=data.locations.filter(r=>(f==='all'||state(r.id)===f)&&(!q||[r.id,r.name,r.english,r.owner_name,r.region].join(' ').toLowerCase().includes(q)));
  if($('sort').value==='name') filtered.sort((a,b)=>a.name.localeCompare(b.name,'zh'));
  if($('sort').value==='region') filtered.sort((a,b)=>a.region.localeCompare(b.region,'zh')||b.centipersons-a.centipersons);
  $('count').textContent=filtered.length;
  $('queue-list').innerHTML=filtered.length ? filtered.map(r=>`<button class="queue-item ${current?.id===r.id?'active':''}" data-id="${esc(r.id)}"><strong>${esc(r.name)} ${state(r.id)==='mapped'?'✓':state(r.id)==='deferred'?'◷':''}</strong><div class="row-meta"><span>${esc(r.owner_name)}</span><span class="pop">${fmt(r.centipersons/100)} 人</span></div><small>${esc(r.id)}</small></button>`).join('') : '<div class="empty">当前筛选下没有地点。可切换处理状态或清除搜索。</div>';
  $('queue-list').querySelectorAll('button').forEach(b=>b.onclick=()=>selectLocation(b.dataset.id));
  const complete=data.locations.filter(r=>state(r.id)==='mapped'), donePop=complete.reduce((n,r)=>n+r.centipersons,0);
  $('progress').textContent=`已完成 ${complete.length} / ${data.locations.length} · ${fmt(donePop/100)} 人已定位`;
  $('bar').style.width=`${100*complete.length/data.locations.length}%`;
  $('remaining').textContent=`尚待确认 ${data.locations.length-complete.length} 处 · ${fmt((data.total_centipersons-donePop)/100)} 人`;
}
async function highlight(kind,key) {
  const cacheKey=kind+':'+key;
  if(!highlightCache.has(cacheKey)) highlightCache.set(cacheKey,(async()=>{
    const h=await api(`/api/highlight?map=${kind}&key=${encodeURIComponent(key)}`);
    if(!h.box) return null;
    const image=new Image(); image.src=h.image; await image.decode(); return {...h,image};
  })().catch(e=>{highlightCache.delete(cacheKey);throw e;}));
  return highlightCache.get(cacheKey);
}
class MapView {
  constructor(kind,image) {
    this.kind=kind;this.canvas=$(kind+'-map');this.ctx=this.canvas.getContext('2d');this.image=image;this.center=[image.width/2,image.height/2];this.scale=1;this.layers=[];this.pointer=null;
    const c=this.canvas;
    new ResizeObserver(()=>this.resize()).observe(c.parentElement);
    c.addEventListener('wheel',e=>{e.preventDefault();const p=this.event(e),before=this.world(p);this.scale=Math.min(24,Math.max(.045,this.scale*Math.exp(-e.deltaY*.0015)));const after=this.world(p);this.center[0]+=before[0]-after[0];this.center[1]+=before[1]-after[1];this.draw();},{passive:false});
    c.onpointerdown=e=>{if(e.button!==0)return;c.setPointerCapture(e.pointerId);this.pointer={start:this.event(e),center:[...this.center],moved:false};};
    c.onpointermove=e=>{const p=this.event(e);if(this.pointer){const dx=p[0]-this.pointer.start[0],dy=p[1]-this.pointer.start[1];if(Math.hypot(dx,dy)>4)this.pointer.moved=true;this.center=[this.pointer.center[0]-dx/this.scale,this.pointer.center[1]-dy/this.scale];this.draw();}else{clearTimeout(this.hoverTimer);this.hoverTimer=setTimeout(()=>this.hit(p,false),160);}};
    c.onpointerup=e=>{if(!this.pointer)return;const p=this.event(e),moved=this.pointer.moved;this.pointer=null;if(!moved)this.hit(p,true);};
    c.onpointercancel=()=>this.pointer=null;
    c.onkeydown=e=>{const d=60/this.scale;if(e.key==='ArrowLeft')this.center[0]-=d;else if(e.key==='ArrowRight')this.center[0]+=d;else if(e.key==='ArrowUp')this.center[1]-=d;else if(e.key==='ArrowDown')this.center[1]+=d;else if(e.key==='+'||e.key==='=')this.zoom(1.4);else if(e.key==='-')this.zoom(1/1.4);else return;e.preventDefault();this.draw();};
  }
  event(e){const r=this.canvas.getBoundingClientRect();return [e.clientX-r.left,e.clientY-r.top];}
  world(p){return [(p[0]-this.width/2)/this.scale+this.center[0],(p[1]-this.height/2)/this.scale+this.center[1]];}
  screen(p){return [(p[0]-this.center[0])*this.scale+this.width/2,(p[1]-this.center[1])*this.scale+this.height/2];}
  resize(){const r=this.canvas.getBoundingClientRect();this.width=r.width;this.height=r.height;const d=devicePixelRatio||1;this.canvas.width=Math.round(r.width*d);this.canvas.height=Math.round(r.height*d);this.ctx.setTransform(d,0,0,d,0,0);this.draw();}
  zoom(f){this.scale=Math.max(.045,Math.min(24,this.scale*f));this.draw();}
  focus(xy,span=260){this.center=[...xy];this.scale=Math.min(this.width,this.height)/span;this.draw();}
  worldView(){this.center=[this.image.width/2,this.image.height/2];this.scale=Math.min(this.width/this.image.width,this.height/this.image.height);this.draw();}
  async hit(p,click){
    const [x,y]=this.world(p);if(x<0||y<0||x>=this.image.width||y>=this.image.height)return;
    const version=selectedVersion;
    try{const {key}=await api(`/api/hit?map=${this.kind}&x=${x}&y=${y}`);if(version!==selectedVersion)return;
      if(!key){$(this.kind+'-tip').textContent='海域 / 非目标陆地';return;}
      if(this.kind==='target'){const r=data.targets[key];$(this.kind+'-tip').textContent=`${r.state_name} · ${r.owner_name} · ${key}`;if(click)toggleTarget(key);}
      else{const r=data.sources[key];$('source-tip').textContent=`${r.name} · ${key}${r.targets.length?' · 已有 '+r.targets.length+' 个对应':' · 尚无对应'}`;if(click){if(data.locations.some(l=>l.id===key))selectLocation(key);else showReference(key);}}
    }catch(e){if(click)toast(e.message);}
  }
  dot(xy,text,color,radius=3){const [x,y]=this.screen(xy),c=this.ctx;if(x<0||y<0||x>this.width||y>this.height)return;c.beginPath();c.arc(x,y,radius,0,Math.PI*2);c.fillStyle=color;c.fill();c.strokeStyle='#102131';c.lineWidth=2;c.stroke();if(text){c.font='12px "Microsoft YaHei", sans-serif';const width=c.measureText(text).width,box=[x+7,y-20,width,17];if(radius<6&&this.labelBoxes.some(b=>box[0]<b[0]+b[2]&&box[0]+box[2]>b[0]&&box[1]<b[1]+b[3]&&box[1]+box[3]>b[1]))return;this.labelBoxes.push(box);c.lineWidth=4;c.strokeStyle='#102131';c.strokeText(text,x+7,y-7);c.fillStyle=color;c.fillText(text,x+7,y-7);}}
  draw(){if(!this.width)return;this.labelBoxes=[];const c=this.ctx;c.clearRect(0,0,this.width,this.height);c.fillStyle='#102739';c.fillRect(0,0,this.width,this.height);c.imageSmoothingEnabled=this.scale<1;
    const [x,y]=this.screen([0,0]);c.drawImage(this.image,x,y,this.image.width*this.scale,this.image.height*this.scale);
    for(const h of this.layers){if(!h)continue;const [hx,hy]=this.screen(h.box);c.drawImage(h.image,hx,hy,h.box[2]*this.scale,h.box[3]*this.scale);}
    if(!current)return;
    if(this.kind==='source'){
      this.dot(current.xy,current.name,'#ffc44b',6);
      for(const key of current.neighbors){const r=data.sources[key];this.dot(r.xy,this.scale>.5?r.name:'',key===activeReference?'#ffffff':'#69c4f2');}
      if(activeReference&&!current.neighbors.includes(activeReference)){const r=data.sources[activeReference];this.dot(r.xy,r.name,'#fff');}
    }else{
      for(const key of current.candidates){const r=data.targets[key];this.dot(r.xy,'','#7394a8',2);}
      if(activeReference)for(const key of data.sources[activeReference].targets){const r=data.targets[key];if(r)this.dot(r.xy,r.state_name,'#69c4f2',5);}
      for(const part of chosen){const r=data.targets[part.province];this.dot(r.xy,r.state_name,'#ffc44b',6);}
    }
  }
}
async function refreshHighlights(){const version=selectedVersion;try{const [source,targets]=await Promise.all([highlight('source',current.id),Promise.all(chosen.map(p=>highlight('target',p.province)))]);if(version!==selectedVersion)return;maps.source.layers=[source];maps.target.layers=targets;maps.source.draw();maps.target.draw();}catch(e){toast('地图高亮加载失败：'+e.message);}}
function selectLocation(id){
  if(!maps.source||saving)return;remember();current=data.locations.find(r=>r.id===id);if(!current)return;selectedVersion++;activeReference=null;
  const saved=reviews.entries[id],draft=drafts[id];chosen=structuredClone(draft?.targets||saved?.targets||[]);$('note').value=draft?.note??saved?.note??'';dirty=!!draft;
  $('crumb').textContent=current.region;$('location-title').textContent=current.name;
  $('location-meta').textContent=`${current.english} · ${current.id} ｜ ${current.owner_name} ｜ ${fmt(current.centipersons/100)} 人`;
  $('culture-summary').textContent='源文化：'+current.cultures.map(c=>`${c.name} ${fmt(c.centipersons/100)} 人`).join(' · ');
  $('record-status').textContent=label[state(id)];$('save-state').textContent=draft?'已恢复浏览器内未保存草稿':saved?'已保存到本机 · 可继续修改':'选择目标省份后保存';
  $('reference-info').textContent='选择参照地点可查看对应州和省份。';$('target-search').value='';$('target-results').innerHTML='';
  $('source-tip').textContent='拖动平移 · 滚轮缩放 · 点击查看参照';$('target-tip').textContent='附近参照推算的视野，需人工确认';
  $('neighbors').innerHTML=current.neighbors.map(n=>`<button class="chip" data-ref="${esc(n)}">${esc(data.sources[n].name)}<small>${esc(n)}</small></button>`).join('');
  $('neighbors').querySelectorAll('button').forEach(b=>b.onclick=()=>showReference(b.dataset.ref));
  renderCandidates();renderSelected();renderQueue();maps.source.layers=[];maps.target.layers=[];
  maps.source.focus(current.xy,90);const target=chosen.length?data.targets[chosen[0].province].xy:current.guess;maps.target.focus(target,130);refreshHighlights();
}
function renderCandidates(){
  $('candidates').innerHTML=current.candidates.map(p=>`<button class="chip ${chosen.some(c=>c.province===p)?'active':''}" data-province="${p}">${esc(data.targets[p].state_name)}<small>${p}</small></button>`).join('');
  $('candidates').querySelectorAll('button').forEach(b=>b.onclick=()=>{toggleTarget(b.dataset.province);maps.target.focus(data.targets[b.dataset.province].xy,120);});
}
function showReference(key){activeReference=key;const r=data.sources[key];if(!r)return;
  $('reference-info').textContent=`${r.name}（${key}） → ${r.targets.map(p=>`${data.targets[p]?.state_name||''} ${p}`).join('、')||'暂无现有映射'}`;
  if(r.targets.length){const xy=r.targets.reduce((a,p)=>[a[0]+data.targets[p].xy[0]/r.targets.length,a[1]+data.targets[p].xy[1]/r.targets.length],[0,0]);maps.target.focus(xy,140);}
  const center=[(current.xy[0]+r.xy[0])/2,(current.xy[1]+r.xy[1])/2],distance=Math.hypot(current.xy[0]-r.xy[0],current.xy[1]-r.xy[1]);maps.source.focus(center,Math.max(160,distance*1.7));
  $('neighbors').querySelectorAll('button').forEach(b=>b.classList.toggle('active',b.dataset.ref===key));maps.source.draw();maps.target.draw();
}
function renderSelected(){
  $('selected-count').textContent=chosen.length;
  const total=chosen.reduce((n,c)=>n+c.weight,0);
  $('selected').innerHTML=chosen.length?chosen.map(part=>{const r=data.targets[part.province];return `<div class="selected-card"><div class="top"><div><strong>${esc(r.state_name)}</strong><small>${esc(r.owner_name)} · ${part.province}</small></div><button class="remove" data-remove="${part.province}" aria-label="移除 ${part.province}">×</button></div><div class="weight"><span>权重</span><input type="number" min="1" max="1000000" step="1" value="${part.weight}" data-weight="${part.province}" aria-label="${part.province} 分配权重"><span>${fmt(100*part.weight/total)}%</span><button class="text-button" data-focus="${part.province}">定位</button></div></div>`;}).join(''):'<div class="empty">尚未选择。点击右侧地图地块，或选择附近候选。</div>';
  $('selected').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>toggleTarget(b.dataset.remove));
  $('selected').querySelectorAll('[data-focus]').forEach(b=>b.onclick=()=>maps.target.focus(data.targets[b.dataset.focus].xy,100));
  $('selected').querySelectorAll('[data-weight]').forEach(input=>input.onchange=()=>{const n=Number(input.value);if(!Number.isInteger(n)||n<1||n>1000000){toast('权重须为 1 到 1000000 的整数');renderSelected();return;}chosen.find(c=>c.province===input.dataset.weight).weight=n;markDirty();renderSelected();});
  const different=chosen.filter(c=>data.targets[c.province].owner_name!==current.owner_name);
  $('owner-warning').hidden=!different.length;
  $('owner-warning').textContent='目标包含不同统治者的省份，请核对边界：'+[...new Set(different.map(c=>data.targets[c.province].owner_name))].join('、')+'。保存后按现有 V3 国界接收人口。';
  $('save').disabled=$('save-next').disabled=saving||!chosen.length;
}
function toggleTarget(key){if(!current||saving)return;const i=chosen.findIndex(c=>c.province===key);if(i>=0)chosen.splice(i,1);else chosen.push({province:key,weight:1});selectedVersion++;markDirty();renderSelected();renderCandidates();refreshHighlights();maps.target.draw();}
function navigate(step){const list=filtered.length?filtered:data.locations;let index=list.findIndex(r=>r.id===current?.id);if(index<0)index=step>0?-1:list.length;const next=list[index+step];if(next)selectLocation(next.id);else toast(step>0?'已到当前列表末尾':'已到当前列表开头');}
async function save(status,advance){
  if(!current||saving)return;if(status==='mapped'&&!chosen.length)return toast('请先选择至少一个目标省份。');
  const id=current.id, index=filtered.findIndex(r=>r.id===id), next=filtered[index+1]?.id;
  saving=true;document.querySelector('.editor').inert=true;document.querySelectorAll('.editor-actions button').forEach(b=>b.disabled=true);$('save-state').textContent='正在写入本机…';
  try{reviews=await api('/api/save',{revision:reviews.revision,entries:{[id]:{status,targets:structuredClone(chosen),note:$('note').value}}});clearDraft(id);dirty=false;renderQueue();$('record-status').textContent=label[status];$('save-state').textContent=`已保存到本机 · 第 ${reviews.revision} 次保存`;toast(status==='mapped'?'已保存对应关系':status==='deferred'?'已暂缓，可从“暂缓”列表继续':'已重新标为未处理');saving=false;if(advance){const other=next||filtered.find(r=>r.id!==id)?.id;if(other)selectLocation(other);else toast('当前列表已处理完，可切换筛选查看其他地点。');}}
  catch(e){$('save-state').textContent='保存失败；草稿仍在浏览器中';toast('保存失败：'+e.message);remember();}
  finally{saving=false;document.querySelector('.editor').inert=false;document.querySelectorAll('.editor-actions button').forEach(b=>b.disabled=false);renderSelected();}
}
function searchTargets(){const q=$('target-search').value.trim().toLowerCase();if(q.length<2){$('target-results').innerHTML='';return;}
  const rows=Object.entries(data.targets).filter(([p,r])=>[p,r.state,r.state_name,r.owner,r.owner_name].join(' ').toLowerCase().includes(q)).sort((a,b)=>Math.hypot(a[1].xy[0]-current.guess[0],a[1].xy[1]-current.guess[1])-Math.hypot(b[1].xy[0]-current.guess[0],b[1].xy[1]-current.guess[1])).slice(0,24);
  $('target-results').innerHTML=rows.length?rows.map(([p,r])=>`<button data-result="${p}">${esc(r.state_name)} · ${esc(r.owner_name)}<small>${p} · 点击定位并添加</small></button>`).join(''):'<div class="empty">没有找到对应省份。</div>';
  $('target-results').querySelectorAll('button').forEach(b=>b.onclick=()=>{const p=b.dataset.result;if(!chosen.some(c=>c.province===p))toggleTarget(p);maps.target.focus(data.targets[p].xy,100);});
}
function exportFile(document,name){const url=URL.createObjectURL(new Blob([JSON.stringify(document,null,2)],{type:'application/json'})),a=documentCreateAnchor(url,name);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);}
function documentCreateAnchor(url,name){const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);return a;}
async function init(){
  try{
    const [dataset,session]=await Promise.all([api('/api/data'),api('/api/session')]);data=dataset;reviews=session.reviews;token=session.token;draftKey='eu5-location-drafts:'+data.source_sha256+':'+data.political_map_sha256;
    try{drafts=JSON.parse(localStorage.getItem(draftKey)||'{}');}catch{drafts={};}
    for(const kind of ['source','target']){const image=new Image();image.src=`/${kind}-map.png`;await image.decode();maps[kind]=new MapView(kind,image);maps[kind].resize();}
    for(const id of ['search','filter','sort'])$(id).addEventListener('input',renderQueue);
    $('note').oninput=markDirty;$('previous').onclick=()=>navigate(-1);$('next').onclick=()=>navigate(1);
    $('save-next').onclick=()=>save('mapped',true);$('save').onclick=()=>save('mapped',false);$('defer').onclick=()=>save('deferred',true);$('reset').onclick=()=>save('pending',false);
    $('clear').onclick=()=>{chosen=[];selectedVersion++;markDirty();renderSelected();renderCandidates();refreshHighlights();};
    $('target-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(searchTargets,180);};
    $('export').onclick=async()=>{try{const doc=await api('/api/export');exportFile(doc,`eu5-location-reviews-r${doc.revision}.json`);toast('已导出已保存的对应关系。未保存草稿不包含在备份中。');}catch(e){toast(e.message);}};
    $('import').onclick=()=>$('import-file').click();$('import-file').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{const doc=JSON.parse(await file.text());reviews=await api('/api/import',{revision:reviews.revision,document:doc});for(const id of Object.keys(doc.entries||{}))clearDraft(id);dirty=false;renderQueue();selectLocation(current.id);toast('备份已校验并合并到本机；原记录留有历史快照。');}catch(error){toast('导入失败：'+error.message);}finally{e.target.value='';}};
    $('help').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();
    document.querySelectorAll('[data-map]').forEach(b=>b.onclick=()=>{const m=maps[b.dataset.map],action=b.dataset.action;if(action==='in')m.zoom(1.5);else if(action==='out')m.zoom(1/1.5);else if(action==='world')m.worldView();else m.focus(b.dataset.map==='source'?current.xy:(chosen.length?data.targets[chosen[0].province].xy:current.guess),b.dataset.map==='source'?90:130);});
    window.addEventListener('beforeunload',remember);
    renderQueue();selectLocation(filtered[0]?.id||data.locations[0].id);
  }catch(e){$('location-title').textContent='加载失败';$('location-meta').textContent=e.message;$('progress').textContent='请确认本地工作站服务仍在运行';toast(e.message);}
}
init();
