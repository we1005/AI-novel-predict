const app = document.getElementById('app');
const crumb = document.getElementById('crumb');
const menuBtn = document.getElementById('menuBtn');
const esc = s => (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const J = async u => (await fetch(u)).json();
let META=null, METAID=null;

async function meta(id){ if(METAID===id&&META) return META; META=await J(`data/${id}/meta.json`); METAID=id; return META; }

function setCrumb(html){ crumb.innerHTML = html; }
function showMenu(v){ menuBtn.style.display = v ? 'inline-block':'none'; }
window.toggleToc=()=>document.querySelector('.toc')?.classList.toggle('open');

// ---------- bookshelf ----------
async function viewShelf(){
  showMenu(false); setCrumb('');
  const books = await J('data/books.json');
  app.innerHTML = `<div class="wrap">
    <div class="hero"><h1>墨笔书阁</h1>
      <p>原著典藏 · AI 续写补全 — 点开书脊,自此处续读到结局</p></div>
    <div class="shelf">${books.map(b=>`
      <div class="book" onclick="location.hash='#/book/${b.id}'">
        <div class="cover" style="background:linear-gradient(160deg,${b.color},#3a1410)">
          <h3>${esc(b.title)}</h3>
          <div class="author">${esc(b.author)}</div>
          <div class="tag">${esc(b.continuation||'')}</div>
        </div>
        <div class="meta">共 ${b.total} 章 · 点击进入</div>
      </div>`).join('')}</div>
  </div>`;
}

// ---------- book intro ----------
async function viewBook(id){
  showMenu(false);
  const m = await meta(id);
  setCrumb(`<b>${esc(m.title)}</b> · 简介`);
  const lastRead = localStorage.getItem('mb_last_'+id);
  const phaseHtml = (m.phases||[]).map(p=>`
    <div class="phase"><span class="rng">第${p.start}–${p.end}章</span>
      <span class="nm">${esc(p.name)}</span>
      <span class="badge cont">续写</span></div>`).join('');
  app.innerHTML = `<div class="wrap intro">
    <div class="title">${esc(m.title)}</div>
    <div class="by">${esc(m.author)}</div>
    <div class="blurb">${esc(m.blurb)}</div>
    <div class="stats">
      <div class="stat"><div class="n">${m.total}</div><div class="k">总章节</div></div>
      <div class="stat"><div class="n">${m.n_original}</div><div class="k">原著（第1–${m.original_section.end}章）</div></div>
      <div class="stat"><div class="n">${m.n_continuation}</div><div class="k">AI 续写（第${m.continuation_start}章起）</div></div>
    </div>
    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <button class="btn" onclick="location.hash='#/read/${id}/1'">从头阅读</button>
      <button class="btn ghost" onclick="location.hash='#/read/${id}/${m.continuation_start}'">直达续写起点（第${m.continuation_start}章）</button>
      ${lastRead?`<button class="btn ghost" onclick="location.hash='#/read/${id}/${lastRead}'">继续上次（第${lastRead}章）</button>`:''}
    </div>
    <div class="sec-h">剧情脉络 · 大纲</div>
    <div class="phase"><span class="rng">第1–${m.original_section.end}章</span>
      <span class="nm">${esc(m.original_section.name)} —— 西泽尔的崛起与诸般伏笔的埋设</span>
      <span class="badge orig">原著</span></div>
    ${phaseHtml}
    <p class="muted" style="font-size:13px;margin-top:14px">绿色「续写」为墨笔多 Agent 引擎按原作者文风补全的部分（第 ${m.continuation_start}–${m.total} 章），承接原著伏笔直至终局。</p>
  </div>`;
}

// ---------- reader ----------
function tocGroups(m){
  const g=[{name:`原著 · 第1–${m.original_section.end}章`,items:[]}];
  (m.phases||[]).forEach(p=>g.push({name:`续写 · ${p.name}`,start:p.start,end:p.end,items:[]}));
  m.toc.forEach(t=>{
    if(t.kind==='original') g[0].items.push(t);
    else { const grp=g.find(x=>x.start&&t.i>=x.start&&t.i<=x.end)||g[g.length-1]; grp.items.push(t); }
  });
  return g;
}
async function viewRead(id, ci){
  ci=+ci; const m = await meta(id); showMenu(true);
  setCrumb(`<span style="cursor:pointer" onclick="location.hash='#/book/${id}'">${esc(m.title)}</span> · 阅读`);
  localStorage.setItem('mb_last_'+id, ci);
  const groups=tocGroups(m);
  const tocHtml = groups.map(g=>`<div class="grp">${esc(g.name)}</div>`+
    g.items.map(t=>`<a href="#/read/${id}/${t.i}" data-i="${t.i}" class="${t.i===ci?'on':''}">${esc(t.title)}${t.kind==='continuation'?'<span class="c">续</span>':''}</a>`).join('')
  ).join('');
  app.innerHTML = `<div class="reader">
    <nav class="toc" id="toc">${tocHtml}</nav>
    <div class="read-main"><div class="read-col" id="col"><div class="loading">载入章节…</div></div>
      <div class="nav" id="pager"></div></div>
  </div>`;
  // scroll active toc into view
  const onEl=document.querySelector('.toc a.on'); if(onEl) onEl.scrollIntoView({block:'center'});
  try{
    const c = await J(`data/${id}/ch/${ci}.json`);
    const paras = c.text.split(/\n+/).filter(s=>s.trim()).map(p=>`<p>${esc(p.trim())}</p>`).join('');
    document.getElementById('col').innerHTML =
      `<h2>${esc(c.title)}</h2><div class="ktag ${c.kind}">${c.kind==='continuation'?'✦ AI 续写章节':'原著章节'}</div>${paras}`;
    const idx=m.toc.findIndex(t=>t.i===ci);
    const prev=idx>0?m.toc[idx-1].i:null, next=idx<m.toc.length-1?m.toc[idx+1].i:null;
    document.getElementById('pager').innerHTML =
      `<button ${prev?'':'disabled'} onclick="${prev?`location.hash='#/read/${id}/${prev}'`:''}">‹ 上一章</button>
       <button ${next?'':'disabled'} onclick="${next?`location.hash='#/read/${id}/${next}'`:''}">下一章 ›</button>`;
    window.scrollTo(0,0);
    document.querySelector('.toc')?.classList.remove('open');
  }catch(e){ document.getElementById('col').innerHTML='<p class="muted">章节载入失败。</p>'; }
}

// ---------- router ----------
async function route(){
  const h=location.hash.slice(1)||'/';
  const p=h.split('/').filter(Boolean);
  try{
    if(p[0]==='book') return viewBook(p[1]);
    if(p[0]==='read') return viewRead(p[1], p[2]);
    return viewShelf();
  }catch(e){ app.innerHTML=`<div class="wrap"><p class="loading">出错了：${esc(String(e))}</p></div>`; }
}
window.addEventListener('hashchange', route);
route();
