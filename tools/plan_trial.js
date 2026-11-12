// The plan page and your trial: the 3D page keeps, in this browser, an index of the trials made in its 2D plan (walls,
// doors, rooms with their areas, the pieces placed and the design's pieces cleared). Here each plan that has one gets a
// bar: Design or Your trial, and Edit in 2D (the 3D page opened straight into its 2D plan). Your trial is drawn over the
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
    '.ptr .pgone{stroke:#C0392B;stroke-width:1.5;opacity:.7}';
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
  function bar(svg,k,e){ var id='ptbar-'+k, b=document.getElementById(id); if(!b){ b=document.createElement('div'); b.id=id; b.className='ptbar'; svg.parentNode.insertBefore(b,svg); }
    var link=P3D+'?plan='+encodeURIComponent(k)+'&edit=1';
    if(!e){ b.innerHTML='<span class="pts">Try it yourself: move walls and doors, and furnish the rooms, in a 2D plan that shows in the 3D. It stays in this browser; the design does not change.</span><a href="'+link+'">Edit this plan in 2D ↗</a>'; return; }
    var parts=[]; if(e.sum)parts.push(esc(e.sum.replace(/^Your trial of [^:]*: /,''))); if(e.pcs&&e.pcs.length)parts.push(e.pcs.length+(e.pcs.length===1?' piece':' pieces')+' placed'); if(e.gone&&e.gone.length)parts.push(e.gone.length+' of the design\'s cleared');
    var on=MODE[k]==='trial';
    b.innerHTML='<span class="pts"><b>Your trial</b>, in this browser: '+parts.join(' · ')+'</span><span class="seg" role="group" aria-label="Show"><button type="button" data-m="design" aria-pressed="'+!on+'">Design</button><button type="button" data-m="trial" aria-pressed="'+on+'">Your trial</button></span><a href="'+link+'">Edit in 2D ↗</a>';
    [].forEach.call(b.querySelectorAll('[data-m]'),function(x){ x.addEventListener('click',function(){ MODE[k]=x.getAttribute('data-m'); try{ sessionStorage.setItem(KEY+'-mode',JSON.stringify(MODE)); }catch(er){} all(); }); }); }
  function all(){ var idx=read(); [].forEach.call(document.querySelectorAll('svg.plan[id^="plan-"]'),function(svg){ var k=svg.id.slice(5), e=idx[k]; bar(svg,k,e); draw(svg,k,e); }); }
  all(); window.addEventListener('storage',function(ev){ if(ev.key===KEY)all(); });
  window.APT_PLAN_TRIAL={redraw:all};
})();
