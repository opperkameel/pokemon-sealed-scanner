"""Write a single self-contained HTML report (open it in any browser)."""
import json

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sealed Pokémon Scanner</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1c1c1a;--mute:#6b6b66;--line:#e4e4df;--good:#137a3d;--goodbg:#e3f4ea;--bad:#a8321e;--accent:#2f5bd3;--warn:#8a6100;--warnbg:#fbf1d6}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;--mute:#9b9a94;--line:#33332f;--good:#5fd08b;--goodbg:#173323;--bad:#f08a75;--accent:#8aa8ff;--warn:#e8c36a;--warnbg:#3a2f12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:20px 16px 8px;max-width:1400px;margin:auto}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mute)}
main{max-width:1400px;margin:auto;padding:0 16px 40px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:140px}
.kpi b{display:block;font-size:20px}.kpi span{color:var(--mute);font-size:12px}
.tabs{display:flex;gap:6px;margin:10px 0}.tabs button{border:1px solid var(--line);background:var(--card);color:var(--ink);padding:7px 14px;border-radius:8px;cursor:pointer;font:inherit}
.tabs button.on{background:var(--ink);color:var(--bg)}
.filters{display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px;margin-bottom:10px}
.filters input,.filters select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink)}
.filters label{display:flex;gap:5px;align-items:center;color:var(--mute)}
.wrap{overflow:auto;max-height:calc(100vh - 120px);background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:980px}th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{position:sticky;top:0;z-index:2;background:var(--card);box-shadow:inset 0 -1px 0 var(--line);cursor:pointer;user-select:none;font-size:12px;color:var(--mute);text-transform:uppercase;letter-spacing:.03em}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}td.title{white-space:normal;min-width:260px;max-width:420px}
tr.hot td{background:var(--goodbg)}.pos{color:var(--good);font-weight:600}.neg{color:var(--bad)}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:5px;border:1px solid var(--line);color:var(--mute);margin-left:4px}
.tag.best{border-color:var(--good);color:var(--good)}.tag.pre{background:var(--warnbg);color:var(--warn);border-color:transparent}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.status{margin-top:18px;color:var(--mute);font-size:12px}.status .err{color:var(--bad)}
.note{color:var(--mute);font-size:12px;margin:6px 0 0}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap}
.runbox{display:flex;align-items:center;gap:10px}
#run{font:inherit;font-weight:600;padding:8px 16px;border-radius:8px;border:0;background:var(--accent);color:#fff;cursor:pointer}
#run:disabled{opacity:.55;cursor:default}
#runst{color:var(--mute);font-size:12px;max-width:340px}
</style></head><body>
<header class="top"><div><h1>Sealed Pokémon Scanner · EU</h1><div class="sub">Scanned __STAMP__ · __NSHOPS__ shops · FX: __FX__ · Landed cost = price + shipping</div></div>
<div class="runbox"><span id="runst"></span><button id="run">Run now</button></div></header>
<main>
<div class="kpis" id="kpis"></div>
<div class="tabs"><button data-v="offers" class="on">All offers</button><button data-v="best">Best price per product</button></div>
<div class="filters">
  <input id="q" placeholder="Search title / set…" size="22">
  <select id="ftype"><option value="">All types</option></select>
  <select id="flang"><option value="">All languages</option></select>
  <select id="fshop"><option value="">All shops</option></select>
  <label><input type="checkbox" id="fstock" checked> In stock only</label>
  <label><input type="checkbox" id="fpre"> Hide pre-orders</label>
  <label>Min margin <input type="number" id="fmin" value="" step="5" style="width:70px"> %</label>
</div>
<div class="wrap"><table><thead id="th"></thead><tbody id="tb"></tbody></table></div>
<p class="note"><b>CM trend / CM low</b> come from Cardmarket's official daily price guide. They mix all languages and all sellers, so they are a reference, not an English offer from a trusted seller. Click to check the real English listings on Cardmarket.</p>
<p class="note">Margin = sell price × (1 − __FEE__ fee) − €__FIXED__ − landed cost. "shops median" = median price across at least 3 shops that have it in stock; "verify listing" = less than half the market price, check before buying; set your own sell prices in <code>data/sell_prices.csv</code> for accurate margins.</p>
<div class="status" id="status"></div>
</main>
<script>
const STAMP=__STAMPJS__, RUN_URL=__RUNURL__, ROWS=__ROWS__, STATUS=__STATUS__, HL=__HL__;
const $=id=>document.getElementById(id);
const eur=v=>v==null?'–':'€'+v.toFixed(2);
const pct=v=>v==null?'–':(v*100).toFixed(0)+'%';
const cls=v=>v==null?'':(v>0?'pos':'neg');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let view='offers', sortKey='margin_pct', sortDir=-1;
for(const [id,key] of [['ftype','type'],['flang','language'],['fshop','shop']]){
  [...new Set(ROWS.map(r=>r[key]))].sort().forEach(v=>$(id).insertAdjacentHTML('beforeend',`<option>${esc(v)}</option>`));
}
const COLS={
 offers:[['title','Product'],['set','Set'],['type','Type'],['language','Lang'],['shop','Shop'],['price_eur','Price','n'],['landed_eur','Landed','n'],['market_median_eur','Shops median','n'],['cm_trend_eur','CM trend','n'],['cm_low_eur','CM low','n'],['sell_eur','Sell','n'],['margin_eur','Margin €','n'],['margin_pct','Margin %','n']],
 best:[['set','Set'],['type','Type'],['language','Lang'],['shop','Cheapest shop'],['landed_eur','Best landed','n'],['market_median_eur','Shops median','n'],['shops_in_stock','# shops','n'],['cm_trend_eur','CM trend','n'],['cm_low_eur','CM low','n'],['sell_eur','Sell','n'],['margin_eur','Margin €','n'],['margin_pct','Margin %','n']]
};
function filtered(){
  const q=$('q').value.toLowerCase(), t=$('ftype').value, l=$('flang').value, s=$('fshop').value;
  const stock=$('fstock').checked, pre=$('fpre').checked, min=parseFloat($('fmin').value);
  let rows=ROWS.filter(r=>(!q||(r.title+' '+r.set).toLowerCase().includes(q))&&(!t||r.type===t)&&(!l||r.language===l)&&(!s||r.shop===s)
    &&(!stock||r.in_stock)&&(!pre||!r.preorder)&&(isNaN(min)||(r.margin_pct!=null&&r.margin_pct*100>=min)));
  if(view==='best') rows=rows.filter(r=>r.best_in_europe);
  return rows.sort((a,b)=>{const x=a[sortKey],y=b[sortKey];if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*sortDir;});
}
function render(){
  $('th').innerHTML='<tr>'+COLS[view].map(([k,l,n])=>`<th data-k="${k}" class="${n?'num':''}">${l}${k===sortKey?(sortDir>0?' ▲':' ▼'):''}</th>`).join('')+'</tr>';
  const rows=filtered();
  $('tb').innerHTML=rows.map(r=>{
    const hot=r.in_stock&&r.margin_pct!=null&&r.margin_pct>=HL;
    return `<tr class="${hot?'hot':''}">`+COLS[view].map(([k,,n])=>{
      let v=r[k];
      if(k==='title') return `<td class="title"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(v)}</a>${r.best_in_europe?'<span class="tag best">cheapest in EU</span>':''}${r.preorder?'<span class="tag pre">pre-order</span>':''}${r.in_stock?'':'<span class="tag">out of stock</span>'}${r.check?'<span class="tag pre" title="Far below market: verify set, language and quantity before buying">verify listing</span>':''}</td>`;
      if(k==='shop') return `<td>${view==='best'?`<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(v)}</a>`:esc(v)} <span class="tag">${esc(r.country)}</span></td>`;
      if(k==='sell_eur') return `<td class="num">${eur(v)}${r.sell_source?`<span class="tag">${r.sell_source}</span>`:''}</td>`;
      if(k.endsWith('_pct')) return `<td class="num ${cls(v)}">${pct(v)}</td>`;
      if(k==='margin_eur') return `<td class="num ${cls(v)}">${eur(v)}</td>`;
      if(k.startsWith('cm_')&&v!=null) return `<td class="num"><a href="${esc(r.cm_url)}" target="_blank" rel="noopener">${eur(v)}</a></td>`;
      if(k.endsWith('_eur')) return `<td class="num">${eur(v)}</td>`;
      return `<td class="${n?'num':''}">${esc(v??'–')}</td>`;
    }).join('')+'</tr>';
  }).join('')||`<tr><td colspan="12" style="text-align:center;padding:30px;color:var(--mute)">No offers match these filters.</td></tr>`;
  const inStock=ROWS.filter(r=>r.in_stock), deals=inStock.filter(r=>r.margin_pct!=null&&r.margin_pct>=HL);
  $('kpis').innerHTML=[[ROWS.length,'sealed offers found'],[inStock.length,'in stock'],[new Set(ROWS.filter(r=>r.best_in_europe).map(r=>r.group)).size,'products compared'],[deals.length,`deals ≥ ${Math.round(HL*100)}% margin`],[rows.length,'shown']]
    .map(([v,l])=>`<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join('');
}
$('th').addEventListener('click',e=>{const k=e.target.closest('th')?.dataset.k;if(!k)return;sortDir=k===sortKey?-sortDir:-1;sortKey=k;render();});
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));view=b.dataset.v;render();});
['q','ftype','flang','fshop','fstock','fpre','fmin'].forEach(id=>$(id).addEventListener('input',render));
$('status').innerHTML='Shops: '+STATUS.map(s=>s.ok?`${esc(s.shop)} (${s.sealed}/${s.listings})`:`<span class="err">${esc(s.shop)} failed: ${esc(s.error)}</span>`).join(' · ');
render();

// "Run now": works when the report is opened through the local app (python3 app.py).
const runBtn=$('run'), runSt=$('runst');
async function status(){ const r=await fetch('/api/status',{cache:'no-store'}); if(!r.ok) throw 0; return r.json(); }
async function poll(){
  try{
    const s=await status();
    if(s.running){
      runBtn.disabled=true; runBtn.textContent='Scanning…';
      runSt.textContent=(s.log.filter(l=>l.trim()).slice(-1)[0]||'Starting…').trim();
      setTimeout(poll,2000);
    } else if(runBtn.disabled && s.exit_code!==null){
      if(s.exit_code===0){ runSt.textContent='Done, loading new results…'; location.reload(); }
      else { runBtn.disabled=false; runBtn.textContent='Run now'; runSt.textContent='Scan failed: '+(s.log.slice(-1)[0]||''); }
    }
  }catch(e){
    runBtn.disabled=true;
    runSt.textContent='To scan from here, start the app: python3 app.py';
  }
}
runBtn.onclick=async()=>{
  runBtn.disabled=true; runBtn.textContent='Scanning…'; runSt.textContent='Starting…';
  try{ await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}); }catch(e){}
  setTimeout(poll,1000);
};
const isLocalApp=['127.0.0.1','localhost'].includes(location.hostname);
if(!isLocalApp && RUN_URL && location.protocol.startsWith('http')){
  // Hosted version: "Run now" starts the GitHub workflow through the GitHub API.
  // It needs a GitHub token that the owner pastes once; it is kept only in this browser (localStorage).
  const REPO=RUN_URL.split('github.com/')[1].split('/actions')[0], OWNER=REPO.split('/')[0];
  const API='https://api.github.com/repos/'+REPO+'/actions';
  const KEY='scanner_github_token';
  const getTok=()=>{try{return localStorage.getItem(KEY)||''}catch(e){return ''}};
  const setTok=v=>{try{v?localStorage.setItem(KEY,v):localStorage.removeItem(KEY)}catch(e){}};
  const gh=(path,opt={})=>fetch(API+path,{...opt,cache:'no-store',headers:{'Accept':'application/vnd.github+json','Authorization':'Bearer '+getTok(),...(opt.headers||{})}});

  const panel=document.createElement('div');
  panel.style.cssText='display:none;max-width:1400px;margin:0 auto 6px;padding:0 16px';
  panel.innerHTML=`<div style="background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px">
    <b>One-time setup on this device</b>
    <ol style="margin:8px 0;padding-left:20px;line-height:1.7">
      <li><a id="tokLink" target="_blank" rel="noopener">Create a GitHub token</a> (opens GitHub). Under <i>Repository access</i> choose <b>Only select repositories</b> → <b>${esc(REPO.split('/')[1])}</b>.
      Under <i>Permissions</i> set <b>Actions</b> to <b>Read and write</b>. Click <b>Generate token</b> and copy it.</li>
      <li>Paste it here: <input id="tokIn" type="password" placeholder="github_pat_…" style="font:inherit;padding:5px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);width:260px">
      <button id="tokSave" style="font:inherit;padding:5px 12px;border-radius:6px;border:1px solid var(--line);background:var(--ink);color:var(--bg);cursor:pointer">Save &amp; run</button></li>
    </ol>
    <span style="color:var(--mute);font-size:12px">The token is stored only in this browser. It can only start scans of this repository. <a href="#" id="tokCancel">Cancel</a></span>
  </div>`;
  document.querySelector('header').after(panel);
  $('tokLink').href='https://github.com/settings/personal-access-tokens/new?name=Pokemon+scanner+Run+now&description=Run+now+button+of+the+scanner+report&target_name='+encodeURIComponent(OWNER)+'&expires_in=365&actions=write';
  $('tokCancel').onclick=e=>{e.preventDefault();panel.style.display='none';runSt.textContent='';};
  $('tokSave').onclick=()=>{const v=$('tokIn').value.trim(); if(!v) return; setTok(v); $('tokIn').value=''; panel.style.display='none'; startRun();};

  let since=0;
  function busy(msg){ runBtn.disabled=true; runBtn.textContent='Scanning…'; runSt.textContent=msg; }
  function idle(msg){ runBtn.disabled=false; runBtn.textContent='Run now'; runSt.innerHTML=msg||''; }
  function badToken(status){
    setTok('');
    idle(status===401?'Your GitHub token is invalid or expired. Click Run now to add a new one.'
                     :'Your GitHub token may not start scans (needs Actions: Read and write on this repository). Click Run now to add a new one.');
  }
  async function startRun(){
    if(!getTok()){ panel.style.display='block'; runSt.textContent='Set up once to start scans from here.'; return; }
    busy('Starting scan on GitHub…');
    try{
      since=Date.now()-60000;
      const r=await gh('/workflows/scan.yml/dispatches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ref:'main'})});
      if(r.status===401||r.status===403||r.status===404) return badToken(r.status);
      if(!r.ok) return idle('GitHub refused the request ('+r.status+'). <a href="'+RUN_URL+'" target="_blank" rel="noopener">Open GitHub</a>');
      setTimeout(track,4000);
    }catch(e){ idle('Could not reach GitHub. Check your connection and try again.'); }
  }
  async function track(){
    try{
      const r=await gh('/runs?per_page=5');
      if(r.status===401||r.status===403) return badToken(r.status);
      const run=((await r.json()).workflow_runs||[]).find(x=>new Date(x.created_at).getTime()>=since);
      if(!run){ busy('Waiting for GitHub to start the scan…'); return setTimeout(track,5000); }
      if(run.status!=='completed'){
        const secs=Math.round((Date.now()-new Date(run.run_started_at||run.created_at).getTime())/1000);
        busy(run.status==='in_progress'?`Scanning all shops… ${Math.floor(secs/60)}:${String(secs%60).padStart(2,'0')} (takes ~2–3 min)`:'Queued at GitHub…');
        return setTimeout(track,8000);
      }
      if(run.conclusion==='success'){ busy('Done, loading new results…'); return checkNewer(true); }
      idle(`Scan failed. <a href="${esc(run.html_url)}" target="_blank" rel="noopener">See details on GitHub</a>`);
    }catch(e){ setTimeout(track,10000); }
  }
  runBtn.onclick=startRun;

  // GitHub Pages lets browsers cache the page for 10 min. Check a tiny file (bypassing caches)
  // and load the fresh page as soon as a newer scan is published.
  async function checkNewer(fast){
    try{
      const r=await fetch('scan.json?t='+Date.now(),{cache:'no-store'});
      if(r.ok){ const s=await r.json(); if(s.stamp && s.stamp!==STAMP){ location.replace(location.pathname+'?v='+encodeURIComponent(s.stamp)); return; } }
    }catch(e){}
    setTimeout(()=>checkNewer(fast),fast?5000:30000);
  }
  checkNewer();
  // A scan already running (e.g. the morning one, or started on another device)? Show its progress.
  if(getTok()){ since=Date.now()-15*60000; gh('/runs?per_page=1').then(r=>r.ok?r.json():null).then(d=>{
    const run=d&&d.workflow_runs&&d.workflow_runs[0]; if(run&&run.status!=='completed'){ since=new Date(run.created_at).getTime(); track(); }
  }).catch(()=>{}); }
} else if(location.protocol==='file:' || !isLocalApp){ runBtn.disabled=true; runSt.textContent='To scan from here, start the app: python3 app.py'; }
else poll();
</script></body></html>"""


def _js(data):
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def write_report(path, rows, status, cfg, stamp, fx_source, run_url=""):
    path.parent.mkdir(exist_ok=True)
    html = (TEMPLATE
            .replace("__ROWS__", _js(rows))
            .replace("__STATUS__", _js(sorted(status, key=lambda s: s["shop"])))
            .replace("__RUNURL__", _js(run_url))
            .replace("__STAMPJS__", _js(stamp))
            .replace("__HL__", str(cfg["min_margin_pct_highlight"]))
            .replace("__STAMP__", stamp)
            .replace("__NSHOPS__", str(len(status)))
            .replace("__FX__", fx_source)
            .replace("__FEE__", f"{cfg['selling']['fee_pct']:.0%}")
            .replace("__FIXED__", f"{cfg['selling']['fixed_cost_eur']:.2f}"))
    path.write_text(html, encoding="utf-8")
