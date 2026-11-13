// The plan page and your trial: the 3D page keeps, in this browser, an index of the trials made in its 2D plan (walls,
// doors, rooms with their areas, the pieces placed and the design's pieces cleared). Here each plan that has one gets a
// bar: the design stays as drawn; Edit makes a copy (its own tab) and opens the plan editor full screen over this page. Your trial is drawn over the
// design, faded under it, in the plan's own centimetres. It follows the 3D page live when both are open.
// Built into the page by tools/build_plans.py (trial_script); fSym is the 3D page's own plan symbol code.
(function(){
  var KEY='__PREFIX__-trials', P3D='__PAGE3D__', NS='http://www.w3.org/2000/svg', MODE={};
  __FSYM__
  function read(){ try{ return JSON.parse(localStorage.getItem(KEY)||'{}')||{}; }catch(e){ return {}; } }
  function el(tag,a,parent){ var e=document.createElementNS(NS,tag); for(var k in a)e.setAttribute(k,a[k]); if(parent)parent.appendChild(e); return e; }
  function esc(t){ return String(t).replace(/[&<>"]/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  try{ MODE=JSON.parse(sessionStorage.getItem(KEY+'-mode')||'{}')||{}; }catch(e){}
  var css=document.createElement('style'); css.textContent=
    '.ptbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;margin:0 0 10px;padding:9px 12px;border-radius:10px;border:1px solid var(--line,#D8D5CF);background:var(--sheet,#FBFAF7);font:500 13px/1.4 var(--sans,system-ui,sans-serif);color:var(--ink,#1D2125)}'+
    '.ptbar b{font-weight:600}.ptbar .pts{color:var(--muted,#666C71);flex:1 1 260px;min-width:0}'+
    '.ptbar .seg{display:inline-flex;border:1px solid var(--line,#D8D5CF);border-radius:8px;overflow:hidden}.ptbar .seg button{appearance:none;border:0;background:transparent;color:inherit;font:600 12.5px var(--sans,system-ui,sans-serif);padding:6px 11px;cursor:pointer}'+
    '.ptbar .seg button[aria-pressed=true]{background:var(--accent,#2E5A74);color:#fff}.ptbar a{font-weight:600;color:var(--accent,#2E5A74);text-decoration:none;white-space:nowrap}.ptbar a:hover{text-decoration:underline}'+
    '.ptbar button:focus-visible,.ptbar a:focus-visible{outline:2px solid var(--accent,#2E5A74);outline-offset:2px}'+
    'svg.trialwalls g.labels,svg.trialwalls g.callouts,svg.trialwalls g.dims,svg.trialwalls g.cams,svg.trialwalls g.sight,svg.trialwalls g.glabels{display:none}'+
    'svg.trialon g.placed{display:none}svg.trialon:not(.trialwalls) g.furn{opacity:.35}'+
    '.ptr .ptf{fill:var(--sheet,#FBFAF7);opacity:.88}.ptr .ptw{fill:#2B2F33}.ptr .ptw.ch{fill:var(--accent,#2E5A74)}.ptr .ptw.lk{fill:#6B6F73}'+
    '.ptr .ptg{stroke:#7FA7BF;stroke-width:3}.ptr .ptx{fill:rgba(192,57,43,.1);stroke:#C0392B;stroke-width:1.5;stroke-dasharray:6 4}'+
    '.ptr .ptl{stroke:#2B2F33;stroke-width:2;fill:none}.ptr .pta{stroke:#2B2F33;stroke-width:1;fill:none;stroke-dasharray:5 4}'+
    '.ptr .ptn,.ptr .ptd{paint-order:stroke;stroke:#FBFAF7;stroke-width:5px;stroke-linejoin:round}.ptr .ptn{font:600 22px var(--sans,system-ui,sans-serif);fill:#1D2125;text-anchor:middle}.ptr .ptd{font:500 15px var(--mono,ui-monospace,monospace);fill:#4A4F54;text-anchor:middle}'+
    '.ptr .pf{fill:#FBFAF7;stroke:#4A4F54;stroke-width:1.3}.ptr .pfl{fill:none;stroke:#7A8085;stroke-width:1}.ptr .pfd{fill:#7A8085;opacity:.55}.ptr .pfs{fill:#EAF0F3;stroke:#7A8085;stroke-width:1}'+
    '.ptr .pfr{fill:rgba(102,108,113,.08);stroke:#7A8085;stroke-width:1;stroke-dasharray:4 3}.ptr .pfh{fill:none;stroke:#7A8085;stroke-width:1.2;stroke-dasharray:6 4}.ptr .pfg{fill:#DCE5D2;stroke:#5E7F4A;stroke-width:1}'+
    '.ptr .pgone{stroke:#C0392B;stroke-width:1.5;opacity:.7}'+
    '.ptbar .pted{appearance:none;border:0;border-radius:8px;background:var(--accent,#2E5A74);color:#fff;font:600 13px var(--sans,system-ui,sans-serif);padding:7px 14px;cursor:pointer;white-space:nowrap}.ptbar .pted:hover{filter:brightness(1.08)}'+
    '.ptbar .ptm{display:inline-flex;flex-wrap:wrap;gap:6px;align-items:center}.ptbar .ptm button{appearance:none;border:1px solid var(--line,#D8D5CF);background:transparent;color:var(--ink,#1D2125);font:600 12.5px var(--sans,system-ui,sans-serif);padding:6px 10px;border-radius:8px;cursor:pointer}.ptbar .ptm button.ptdel{border-color:#B03A2E;color:#B03A2E}.ptbar .ptm input{font:500 13px var(--sans,system-ui,sans-serif);padding:6px 8px;border:1px solid var(--line,#D8D5CF);border-radius:6px;min-width:0;width:220px;max-width:100%;background:var(--sheet,#FBFAF7);color:var(--ink,#1D2125)}'+
    '.ptbar .ptsel{font:inherit;font-size:13px;padding:5px 8px;border:1px solid var(--line,#ccc);border-radius:6px;background:var(--paper,#fff);color:inherit;max-width:16em}.ptcx{appearance:none;border:0;border-right:1px solid var(--line,#ddd);background:transparent;color:var(--muted,#777);font:600 18px/1 sans-serif;padding:0 10px;cursor:pointer;align-self:stretch}.ptcx:hover,.ptcx:focus-visible{color:#B23A2E}.tab.ptct small{color:var(--accent,#2E5A74)}.tab.ptct[aria-selected="true"] small{color:var(--paper,#F2F1ED)}'+
    '.ptedit{position:fixed;inset:0;z-index:9999;background:var(--paper,#F2F1ED);display:grid}.ptedit iframe{border:0;width:100%;height:100%}'+
    '.ptedit .ptload{position:absolute;inset:0;display:grid;place-content:center;justify-items:center;gap:10px;font:600 14px var(--sans,system-ui,sans-serif);color:var(--muted,#666C71);pointer-events:none}.ptedit .ptalt{pointer-events:auto;color:var(--accent,#2E5A74)}';
  document.head.appendChild(css);
  function draw(svg,k,e){ var old=svg.querySelector('g.ptr'); if(old)old.remove(); var on=!!e&&MODE[k]==='trial', walls=on&&!!e.lines; svg.classList.toggle('trialon',on); svg.classList.toggle('trialwalls',walls); if(!on)return;
    var vb=svg.viewBox.baseVal, g=el('g',{class:'ptr'},svg);
    if(walls)el('rect',{x:vb.x,y:vb.y,width:vb.width,height:vb.height,class:'ptf'},g); else { var lb=svg.querySelector('g.labels'); if(lb)svg.appendChild(lb); }   // the room names stay on top   // walls changed: the design faded under the trial, its labels make way; else only its furniture fades
    (e.was||[]).forEach(function(b){ el('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],class:'ptx'},g); });   // walls the trial takes out
    (e.gone||[]).forEach(function(p){ var hw=Math.min(p.w,60)/2, hd=Math.min(p.d,60)/2; el('line',{x1:p.x-hw,y1:p.y-hd,x2:p.x+hw,y2:p.y+hd,class:'pgone'},g); el('line',{x1:p.x-hw,y1:p.y+hd,x2:p.x+hw,y2:p.y-hd,class:'pgone'},g); });
    (e.pcs||[]).forEach(function(p){ var pg=el('g',{transform:'translate('+p.x+' '+p.y+') rotate('+(p.r||0)+')'},g); pg.innerHTML=fSym({w:p.w,d:p.d,h:p.h,y:p.y0||0,m:p.m},p.t);
      var tt=el('title',{},pg); tt.textContent=p.n+' · '+p.w+' × '+p.d+' cm'; });
    (e.lines||[]).forEach(function(L){ var cls='ptw'+(L.nw||L.moved?' ch':'')+(L.lock?' lk':''), a=L.a[0];
      function seg(a0,a1){ if(a1-a0<.5)return; var b=L.o==='h'?[a0,L.c[0],a1,L.c[1]]:[L.c[0],a0,L.c[1],a1]; el('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],class:cls},g); }
      (L.ops||[]).slice().sort(function(p,q){ return p[0]-q[0]; }).forEach(function(op){ if(op[0]>a)seg(a,op[0]); a=Math.max(a,op[1]);
        if(op[2]==='win'||op[2]==='gl'){ var m=(L.c[0]+L.c[1])/2; el('line',L.o==='h'?{x1:op[0],y1:m,x2:op[1],y2:m,class:'ptg'}:{x1:m,y1:op[0],x2:m,y2:op[1],class:'ptg'},g); } });
      if(L.a[1]>a)seg(a,L.a[1]); });
    (e.doors||[]).forEach(function(d){ if(d.slide){ var m=(d.c[0]+d.c[1])/2; el('line',d.o==='h'?{x1:d.op[0],y1:m,x2:d.op[1],y2:m,class:'ptl'}:{x1:m,y1:d.op[0],x2:m,y2:d.op[1],class:'ptl'},g); return; }
      var h=d.h, l=d.l, s=d.s, z=(l[0]-h[0])*(s[1]-h[1])-(l[1]-h[1])*(s[0]-h[0]);
      el('line',{x1:h[0],y1:h[1],x2:l[0],y2:l[1],class:'ptl'},g); el('path',{d:'M'+l[0]+' '+l[1]+' A'+d.w+' '+d.w+' 0 0 '+(z>0?1:0)+' '+s[0]+' '+s[1],class:'pta'},g); }); 
    (e.rooms||[]).forEach(function(r){ var cx=(r.r[0]+r.r[2])/2, cy=(r.r[1]+r.r[3])/2, rw=r.r[2]-r.r[0]-10, f1=Math.min(22,rw/(r.n.length*.6)), dt=r.a.toFixed(1)+' m² · '+r.w+' × '+r.d, f2=Math.min(15,rw/(dt.length*.6));
      var t=el('text',{x:cx,y:cy-4,class:'ptn','font-size':Math.max(9,f1)},g); t.textContent=r.n; var t2=el('text',{x:cx,y:cy+f2+6,class:'ptd','font-size':Math.max(8,f2)},g); t2.textContent=dt; });
  }
  // the four designs stay as drawn: Edit works on a copy, made the first time, with a tab of its own beside the designs
  var CKEY='__PREFIX__-copies', FKEY='__PREFIX__-furnish', CUR={};
  try{ CUR=JSON.parse(sessionStorage.getItem(KEY+'-cur')||'{}')||{}; }catch(e){}
  function copies(){ try{ return (JSON.parse(localStorage.getItem(CKEY)||'[]')||[]).filter(function(c){ return c&&c.id&&c.from; }); }catch(e){ return []; } }
  function saveCopies(l){ try{ localStorage.setItem(CKEY,JSON.stringify(l)); }catch(e){} }
  function saveCur(){ try{ sessionStorage.setItem(KEY+'-cur',JSON.stringify(CUR)); }catch(e){} }
  function designName(k){ var t=document.getElementById('tab-'+k); if(!t)return k==='existing'?'the plan as built':'the plan'; var sm=t.querySelector('small'), sub=sm?sm.textContent:'', main=t.textContent.replace(sub,'').trim(), rv=(sub.match(/Rev [\d.]+/)||[])[0];
    return rv?rv+' · '+main:main; }
  function newCopy(from){ var l=copies(), used={}; l.forEach(function(c){ used[c.id]=1; }); var n=1; while(used['copy-'+from+'-'+n])n++;
    var c={id:'copy-'+from+'-'+n,from:from,name:(n>1?'Copy '+n+' of ':'Copy of ')+designName(from),at:new Date().toISOString()}; l.push(c); saveCopies(l); return c; }
  function copyOf(id){ return copies().filter(function(c){ return c.id===id; })[0]; }
  function dropCopy(id){ var l=copies().filter(function(c){ return c.id!==id; }); saveCopies(l);
    try{ for(var i=localStorage.length-1;i>=0;i--){ var kk=localStorage.key(i); if(kk&&kk.indexOf('apt3d-trial2-'+id+'-')===0)localStorage.removeItem(kk); }
      var fl=JSON.parse(localStorage.getItem(FKEY)||'null'); if(fl&&fl[id]){ delete fl[id]; localStorage.setItem(FKEY,JSON.stringify(fl)); }
      var ix=read(); if(ix[id]){ delete ix[id]; localStorage.setItem(KEY,JSON.stringify(ix)); } }catch(e){} }
  function pick(from,id){ var t=document.getElementById('tab-'+from); if(t&&ACT!==from)t.click(); ACT=from; if(id)CUR[from]=id; else delete CUR[from]; saveCur(); all(); }
  var ACT=null;   // the design on show: its own tab looks unpicked while one of its copies is shown
  function tabsUI(){ var orig=[].slice.call(document.querySelectorAll('.tab[data-plan]')); if(!orig.length)return; var box=orig[0].parentNode;
    orig.forEach(function(t){ if(t.getAttribute('aria-selected')==='true')ACT=t.getAttribute('data-plan'); });
    [].forEach.call(box.querySelectorAll('.ptct,.ptcx'),function(x){ x.remove(); });
    copies().forEach(function(c){ var t=document.getElementById('tab-'+c.from); if(!t)return; var b=document.createElement('button'); b.type='button'; b.className='tab ptct'; b.setAttribute('role','tab');
      var on=CUR[c.from]===c.id&&ACT===c.from; b.setAttribute('aria-selected',String(on)); b.innerHTML='<small>'+(/^Copy \d+ of /.test(c.name)?esc(c.name.split(' of ')[0]):'Your copy')+'</small>'; b.appendChild(document.createTextNode(c.name.replace(/^Copy (\d+ )?of /,''))); b.title=c.name;
      b.addEventListener('click',function(){ pick(c.from,c.id); }); box.appendChild(b);
      var x=document.createElement('button'); x.type='button'; x.className='ptcx'; x.textContent='×'; x.title='Delete '+c.name; x.setAttribute('aria-label','Delete '+c.name);   // delete a copy from its tab: asks first, in its bar
      x.addEventListener('click',function(){ pick(c.from,c.id); setTimeout(function(){ var d=document.querySelector('#ptbar-'+c.from+' [data-a="del"]'); if(d){ d.click(); var bb=document.getElementById('ptbar-'+c.from); if(bb&&bb.scrollIntoView)bb.scrollIntoView({block:'nearest'}); } },40); }); box.appendChild(x); });
    orig.forEach(function(t){ var k=t.getAttribute('data-plan'); if(k===ACT&&CUR[k])t.setAttribute('aria-selected','false'); }); }   // a copy shown: its tab is the one picked
  function bar(svg,k){ var id='ptbar-'+k, b=document.getElementById(id); if(!b){ b=document.createElement('div'); b.id=id; b.className='ptbar'; svg.parentNode.insertBefore(b,svg); }
    var cid=CUR[k], c=cid&&copyOf(cid), mine=copies().filter(function(q){ return q.from===k; });
    if(!c){ b.innerHTML='<span class="pts">'+(k==='existing'?'<b>The plan as built</b>, as measured: it stays as it is.':'<b>The design</b>, as drawn: it stays as it is.')+' Edit starts a new copy to work on'+(mine.length?' (you have '+mine.length+(mine.length===1?' copy':' copies')+', in the tabs)':'')+'.</span><button type="button" class="pted">Edit</button>';
      b.querySelector('.pted').addEventListener('click',function(){ var cc=newCopy(k); pick(k,cc.id); edit(cc.id); }); chooser(b,k,mine,null); return; }
    var e=read()[c.id], parts=[]; if(e&&e.sum)parts.push(esc(e.sum.replace(/^Your trial of [^:]*: /,''))); if(e&&e.pcs&&e.pcs.length)parts.push(e.pcs.length+(e.pcs.length===1?' piece':' pieces')+' placed'); if(e&&e.gone&&e.gone.length)parts.push(e.gone.length+' of the design\'s cleared');
    b.innerHTML='<span class="pts"><b></b>, your copy of '+esc(designName(k))+', in this browser: '+(parts.join(' · ')||'no changes yet')+'</span><button type="button" class="pted">Edit</button><span class="ptm"><button type="button" data-a="des">Show the design</button><button type="button" data-a="ren">Rename</button><button type="button" data-a="new">New copy</button><button type="button" data-a="del">Delete</button></span>';
    b.querySelector('b').textContent=c.name; b.querySelector('.pted').addEventListener('click',function(){ edit(c.id); }); chooser(b,k,mine,c.id);
    b.querySelector('[data-a="des"]').addEventListener('click',function(){ pick(k,null); });
    b.querySelector('[data-a="new"]').addEventListener('click',function(){ var n=newCopy(k); pick(k,n.id); edit(n.id); });
    b.querySelector('[data-a="ren"]').addEventListener('click',function(){ var m=b.querySelector('.ptm'); m.innerHTML='<input type="text" aria-label="Name of the copy" maxlength="60"><button type="button" data-a="ok">Save</button><button type="button" data-a="no">Cancel</button>';
      var inp=m.querySelector('input'); inp.value=c.name; inp.focus(); inp.select();
      function ok(){ var v=inp.value.trim(); if(v){ var l=copies(); l.forEach(function(q){ if(q.id===c.id)q.name=v; }); saveCopies(l); var ix=read(); if(ix[c.id]){ ix[c.id].name=v; try{ localStorage.setItem(KEY,JSON.stringify(ix)); }catch(er){} } } all(); }
      inp.addEventListener('keydown',function(ev){ if(ev.key==='Enter')ok(); if(ev.key==='Escape')all(); }); m.querySelector('[data-a="ok"]').addEventListener('click',ok); m.querySelector('[data-a="no"]').addEventListener('click',all); });
    b.querySelector('[data-a="del"]').addEventListener('click',function(){ var m=b.querySelector('.ptm'); m.innerHTML='<span>Delete it, with its changes?</span><button type="button" data-a="yes" class="ptdel">Delete</button><button type="button" data-a="no">Keep</button>';
      m.querySelector('[data-a="yes"]').addEventListener('click',function(){ dropCopy(c.id); pick(k,null); }); m.querySelector('[data-a="no"]').addEventListener('click',all); }); }
  function chooser(b,k,mine,cid){ if(document.querySelector('.tab[data-plan]')||mine.length<(cid?2:1))return;   // a page without tabs: its copies in a list
    var s=document.createElement('select'); s.className='ptsel'; s.setAttribute('aria-label','Show');
    s.innerHTML='<option value="">The design</option>'+mine.map(function(q){ return '<option value="'+esc(q.id)+'">'+esc(q.name)+'</option>'; }).join(''); s.value=cid||'';
    s.addEventListener('change',function(){ pick(k,s.value||null); }); b.insertBefore(s,b.querySelector('.pted')); }
  function all(){ var idx=read(); tabsUI(); [].forEach.call(document.querySelectorAll('svg.plan[id^="plan-"]'),function(svg){ var k=svg.id.slice(5); if(CUR[k]&&!copyOf(CUR[k]))delete CUR[k]; var e=CUR[k]?(idx[CUR[k]]||{}):null; MODE[k]=CUR[k]?'trial':'design'; bar(svg,k); draw(svg,k,e); }); }
  [].forEach.call(document.querySelectorAll('.tab[data-plan]'),function(t){ t.addEventListener('click',function(ev){ if(ev.isTrusted){ delete CUR[t.getAttribute('data-plan')]; saveCur(); } setTimeout(all,0); }); });   // a design's tab: the design
  // Edit: the plan editor, full screen over this page, in the plan page's own look; Done comes back here with your copy shown
  var ED=null;
  function edit(k){ if(ED)return; var cp=copyOf(k); if(!cp){ cp=newCopy(k); pick(k,cp.id); } k=cp.id;   // a design is never edited: Edit on it starts a new copy
    ED=document.createElement('div'); ED.className='ptedit'; ED.setAttribute('role','dialog'); ED.setAttribute('aria-label','Editing '+cp.name);
    ED.innerHTML='<p class="ptload">Opening '+esc(cp.name)+' for editing…<a class="ptalt" hidden></a></p>'; var alt=ED.querySelector('.ptalt'); alt.href=P3D+'?plan='+encodeURIComponent(k)+'&edit=1'; alt.textContent='Not opening? Edit it on its own page'; setTimeout(function(){ if(alt.parentNode)alt.hidden=false; },7000); var f=document.createElement('iframe'); f.title='Plan editor'; f.src=P3D+'?plan='+encodeURIComponent(k)+'&edit=1&embed=1';
    window.addEventListener('message',function rdy(ev){ if(ev.data&&ev.data.apt==='edit-ready'){ var l=ED&&ED.querySelector('.ptload'); if(l)l.remove(); window.removeEventListener('message',rdy); } });   // the loading note stays until the editor says it is open
    ED.appendChild(f); document.body.appendChild(ED); document.documentElement.style.overflow='hidden'; ED.k=k; f.focus(); }
  function closeEdit(k){ if(!ED)return; ED.remove(); ED=null; document.documentElement.style.overflow=''; var cp=copyOf(k);
    if(cp)pick(cp.from,cp.id); else all();      // back on the copy that was edited
    var sv=document.getElementById('plan-'+(cp?cp.from:k)); if(sv&&sv.scrollIntoView)sv.scrollIntoView({block:'center'}); }
  window.addEventListener('message',function(ev){ var d=ev.data||{}; if(!ED||!d.apt)return;
    if(d.apt==='edit-done')closeEdit(d.plan||ED.k); else if(d.apt==='open3d')location.href=P3D+'?plan='+encodeURIComponent(d.plan||ED.k); });
  (function(){ try{ if(localStorage.getItem(CKEY+'-v1'))return; var idx=read(), fl=JSON.parse(localStorage.getItem(FKEY)||'null')||{}, ch=false;   // once: trials made on the designs become copies of them
    [].forEach.call(document.querySelectorAll('svg.plan[id^="plan-"]'),function(svg){ var k=svg.id.slice(5), pre='apt3d-trial2-'+k+'-', tk=null; for(var i=0;i<localStorage.length;i++){ var kk=localStorage.key(i); if(kk&&kk.indexOf(pre)===0)tk=kk; }
      var f=Array.isArray(fl[k])&&fl[k].length?fl[k]:null; if(!tk&&!f&&!idx[k])return; var c=newCopy(k);
      if(tk){ localStorage.setItem('apt3d-trial2-'+c.id+'-'+tk.slice(pre.length),localStorage.getItem(tk)); localStorage.removeItem(tk); } if(f)fl[c.id]=f; delete fl[k]; if(idx[k]){ idx[c.id]=idx[k]; idx[c.id].name=c.name; delete idx[k]; } ch=true; });
    if(ch){ localStorage.setItem(FKEY,JSON.stringify(fl)); localStorage.setItem(KEY,JSON.stringify(idx)); } localStorage.setItem(CKEY+'-v1','1'); }catch(e){} })();
  all(); window.addEventListener('storage',function(ev){ if(ev.key===KEY||ev.key===CKEY)all(); });
  try{ var q=new URLSearchParams(location.search).get('edit'); if(q){ var qc=copyOf(q), qf=qc?qc.from:q, tq=document.getElementById('tab-'+qf); if(tq)tq.click(); setTimeout(function(){ edit(q); },60); } }catch(e){}   // from the 3D page's 2D button
  window.APT_PLAN_TRIAL={redraw:all,edit:edit,copies:copies};
})();
