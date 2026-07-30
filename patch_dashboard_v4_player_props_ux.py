from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "v4-player-props-ux-style"
SCRIPT_ID = "v4-player-props-ux-script"

STYLE = r'''<style id="v4-player-props-ux-style">
.propsUxSummary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.propsUxMetric{border:1px solid var(--line);background:#091321;border-radius:14px;padding:12px}.propsUxMetric strong{display:block;color:var(--green);font-size:22px;margin-top:4px}.propsUxTop{border:1px solid rgba(0,227,155,.45);background:linear-gradient(180deg,rgba(0,227,155,.08),#08101c);border-radius:16px;padding:14px;margin-bottom:14px}.propsUxTopPick{font-size:22px;font-weight:900;color:var(--green);margin-top:4px}.propsUxTools{display:grid;grid-template-columns:1.2fr repeat(4,minmax(120px,.7fr));gap:10px;margin:10px 0 14px}.propsUxTools input,.propsUxTools select{width:100%;height:44px;background:#07101d;border:1px solid var(--line);color:#fff;border-radius:12px;padding:10px}.propsUxMeta{display:flex;justify-content:space-between;gap:10px;align-items:center;margin:8px 0;color:var(--muted);font-size:11px}.propsUxTable{overflow:auto;border:1px solid var(--line);border-radius:16px}.propsUxHead,.propsUxRow{display:grid;grid-template-columns:minmax(190px,1.3fr) 65px 70px 95px 95px 90px 90px 80px;gap:10px;align-items:center;min-width:930px}.propsUxHead{padding:12px;background:#070b13;color:#7f8da7;text-transform:uppercase;font-size:11px;letter-spacing:.08em}.propsUxHead button{border:0;background:transparent;color:inherit;font:inherit;font-weight:800;cursor:pointer;padding:0;text-align:left}.propsUxHead button.active{color:var(--green)}.propsUxRow{padding:13px 12px;border-top:1px solid #152034}.propsUxPlayer{font-weight:900}.propsUxSub{color:var(--muted);font-size:11px;margin-top:3px}.propsUxSignal{font-weight:900;color:var(--green)}.propsUxBad{color:var(--red)}.propsUxCards{display:none}.propsUxCard{border:1px solid var(--line);background:#08101c;border-radius:14px;padding:13px}.propsUxCardTop{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.propsUxCardPick{font-size:18px;font-weight:900;color:var(--green)}.propsUxCardGrid{display:grid;grid-template-columns:1fr 1fr;gap:0 14px;margin-top:9px}.propsUxCardLine{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid #152034;font-size:12px}.propsUxBadge{display:inline-flex;border:1px solid rgba(0,227,155,.45);background:rgba(0,227,155,.12);color:var(--green);border-radius:999px;padding:4px 8px;font-size:10px;font-weight:900}.propsUxEmpty{text-align:center;color:var(--muted);padding:35px}
@media(max-width:900px){.propsUxSummary{grid-template-columns:1fr 1fr}.propsUxTools{grid-template-columns:1fr 1fr}.propsUxTools input{grid-column:1/-1}.propsUxTable{display:none}.propsUxCards{display:grid;gap:10px}.propsUxCardGrid{grid-template-columns:1fr}.propsUxMeta{align-items:flex-start;flex-direction:column}}
@media(max-width:520px){.propsUxTools{grid-template-columns:1fr}.propsUxTools input{grid-column:auto}}
</style>'''

SCRIPT = r'''<script id="v4-player-props-ux-script">
(function(){
  const arr=v=>Array.isArray(v)?v:[];
  const esc=v=>typeof window.E==='function'?window.E(v):String(v??'');
  const safe=(v,d='-')=>v===undefined||v===null||v===''?d:v;
  const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
  const state={sort:'score',dir:-1};
  const raw=()=>typeof window.propsRaw==='function'?arr(window.propsRaw()):arr((typeof DATA!=='undefined'&&DATA?.master?.props)||window.DATA?.master?.props);
  const side=r=>String(r.signal||r.side||'OVER').toUpperCase();
  const line=r=>safe(r.line??r.consensus_line);
  const score=r=>num(r.governed_score??r.calibrated_score??r.final_score??r.confidence)??0;
  const projection=r=>num(r.projection??r.pred??r.model_projection);
  const edge=r=>{const p=projection(r),l=num(line(r));if(p===null||l===null)return null;return Number((side(r)==='UNDER'?l-p:p-l).toFixed(2))};
  const book=r=>safe(r.best_book||r.book||r.best_over_book||r.best_under_book,'Book TBD');
  const price=r=>side(r)==='UNDER'?safe(r.best_under_price??r.under_price):safe(r.best_over_price??r.over_price);
  const history=r=>arr(r.last5_values).length?arr(r.last5_values):arr(r.last5).map(x=>num(x?.value)).filter(v=>v!==null);
  const hitRate=r=>{const vals=history(r),l=num(line(r));if(!vals.length||l===null)return null;const h=vals.filter(v=>side(r)==='UNDER'?v<l:v>l).length;return Math.round(h/vals.length*100)};
  const game=r=>safe(r.game,'Game TBD');
  const unique=rows=>{const m=new Map();for(const r of rows){const k=[r.player,r.stat,line(r),side(r),game(r),book(r)].join('|').toLowerCase();const old=m.get(k);if(!old||score(r)>score(old))m.set(k,r)}return [...m.values()]};
  const value=(r,key)=>key==='player'?String(r.player||'').toLowerCase():key==='stat'?String(r.stat||'').toLowerCase():key==='line'?(num(line(r))??-999):key==='edge'?(edge(r)??-999):key==='hit'?(hitRate(r)??-1):key==='price'?(num(price(r))??-9999):score(r);
  const sorted=rows=>[...rows].sort((a,b)=>{const x=value(a,state.sort),y=value(b,state.sort);return (typeof x==='string'?x.localeCompare(y):x-y)*state.dir});
  window.setPropsUxSort=function(key){if(state.sort===key)state.dir*=-1;else{state.sort=key;state.dir=key==='player'||key==='stat'?1:-1}window.props()};
  const sortButton=(key,label)=>`<button class="${state.sort===key?'active':''}" onclick="setPropsUxSort('${key}')">${label}${state.sort===key?(state.dir>0?' ▲':' ▼'):''}</button>`;
  const filters=()=>({q:String(document.getElementById('pxSearch')?.value||'').toLowerCase(),stat:String(document.getElementById('pxStat')?.value||''),side:String(document.getElementById('pxSide')?.value||''),book:String(document.getElementById('pxBook')?.value||''),game:String(document.getElementById('pxGame')?.value||'')});
  const filterRows=rows=>{const f=filters();return rows.filter(r=>(!f.q||JSON.stringify(r).toLowerCase().includes(f.q))&&(!f.stat||r.stat===f.stat)&&(!f.side||side(r)===f.side)&&(!f.book||book(r)===f.book)&&(!f.game||game(r)===f.game))};
  const options=(rows,key,fn=x=>x)=>[...new Set(rows.map(fn).filter(Boolean))].sort().map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');
  const topProp=rows=>{const candidates=rows.filter(r=>edge(r)!==null).sort((a,b)=>(score(b)+Math.max(edge(b),0)*3)-(score(a)+Math.max(edge(a),0)*3));const r=candidates[0];if(!r)return '';return `<div class="propsUxTop"><div class="label mono">Top player prop</div><div class="propsUxTopPick">${esc(r.player)} ${esc(side(r))} ${esc(r.stat)} ${esc(line(r))}</div><div class="small mono">${esc(game(r))} · ${esc(book(r))} ${esc(price(r))} · Projection ${esc(safe(projection(r)))} · Edge ${esc(safe(edge(r)))} · Score ${esc(score(r))}</div></div>`};
  const summary=rows=>{const bet=rows.filter(r=>score(r)>=70).length,books=new Set(rows.map(book)).size,players=new Set(rows.map(r=>r.player).filter(Boolean)).size;return `<div class="propsUxSummary"><div class="propsUxMetric"><div class="label mono">Unique props</div><strong class="mono">${rows.length}</strong></div><div class="propsUxMetric"><div class="label mono">Players</div><strong class="mono">${players}</strong></div><div class="propsUxMetric"><div class="label mono">Score 70+</div><strong class="mono">${bet}</strong></div><div class="propsUxMetric"><div class="label mono">Books</div><strong class="mono">${books}</strong></div></div>`};
  const row=r=>{const h=hitRate(r),e=edge(r);return `<div class="propsUxRow"><div><div class="propsUxPlayer">${esc(r.player)}</div><div class="propsUxSub mono">${esc(game(r))}</div></div><div class="propsUxSignal mono">${esc(r.stat)}</div><div class="mono">${esc(line(r))}</div><div><b>${esc(side(r))}</b><div class="propsUxSub mono">${esc(book(r))}</div></div><div class="mono">${esc(price(r))}</div><div class="mono">${esc(safe(projection(r)))}</div><div class="mono ${e!==null&&e<0?'propsUxBad':''}">${esc(safe(e))}</div><div class="mono ${h!==null&&h<50?'propsUxBad':''}">${h===null?'-':h+'%'}</div></div>`};
  const card=r=>{const h=hitRate(r),e=edge(r);return `<div class="propsUxCard"><div class="propsUxCardTop"><div><div class="propsUxPlayer">${esc(r.player)}</div><div class="propsUxSub mono">${esc(game(r))}</div></div><span class="propsUxBadge">${esc(score(r))}</span></div><div class="propsUxCardPick">${esc(side(r))} ${esc(r.stat)} ${esc(line(r))}</div><div class="propsUxCardGrid"><div class="propsUxCardLine"><span>Best book</span><b>${esc(book(r))} ${esc(price(r))}</b></div><div class="propsUxCardLine"><span>Projection</span><b>${esc(safe(projection(r)))}</b></div><div class="propsUxCardLine"><span>Edge</span><b class="${e!==null&&e<0?'propsUxBad':''}">${esc(safe(e))}</b></div><div class="propsUxCardLine"><span>L5 hit rate</span><b class="${h!==null&&h<50?'propsUxBad':''}">${h===null?'-':h+'%'}</b></div></div></div>`};
  window.props=function(){
    const all=unique(raw());
    const stats=options(all,'stat',r=>r.stat), sides=options(all,'side',side), books=options(all,'book',book), games=options(all,'game',game);
    const controls=`<div class="propsUxTools"><input id="pxSearch" placeholder="Search player, team or matchup" oninput="props()"><select id="pxStat" onchange="props()"><option value="">All stats</option>${stats}</select><select id="pxSide" onchange="props()"><option value="">All sides</option>${sides}</select><select id="pxBook" onchange="props()"><option value="">All books</option>${books}</select><select id="pxGame" onchange="props()"><option value="">All games</option>${games}</select></div>`;
    const selected={q:document.getElementById('pxSearch')?.value||'',stat:document.getElementById('pxStat')?.value||'',side:document.getElementById('pxSide')?.value||'',book:document.getElementById('pxBook')?.value||'',game:document.getElementById('pxGame')?.value||''};
    let rows=sorted(filterRows(all));
    const head=`<div class="propsUxHead"><div>${sortButton('player','Player')}</div><div>${sortButton('stat','Stat')}</div><div>${sortButton('line','Line')}</div><div>Pick</div><div>${sortButton('price','Price')}</div><div>Projection</div><div>${sortButton('edge','Edge')}</div><div>${sortButton('hit','L5 Hit')}</div></div>`;
    const html=`<div class="section"><h2 class="mono">Player Props</h2><div class="small mono">Ranked props with best available price, model projection, edge and recent hit rate.</div>${summary(all)}${topProp(all)}${controls}<div class="propsUxMeta mono"><span>Showing ${rows.length} of ${all.length} unique props</span><span>Sorted by ${esc(state.sort)}</span></div><div class="propsUxTable">${head}${rows.map(row).join('')||'<div class="propsUxEmpty mono">No props match these filters.</div>'}</div><div class="propsUxCards">${rows.map(card).join('')||'<div class="propsUxEmpty mono">No props match these filters.</div>'}</div></div>`;
    setTimeout(()=>{for(const [id,v] of Object.entries({pxSearch:selected.q,pxStat:selected.stat,pxSide:selected.side,pxBook:selected.book,pxGame:selected.game})){const el=document.getElementById(id);if(el)el.value=v}},0);
    return html;
  };
  window.PLAYER_PROPS_UX={version:'1.0',raw,unique};
})();
</script>'''


def replace_block(html: str, tag: str, marker: str, replacement: str) -> str:
    start = html.find(f'<{tag} id="{marker}">')
    if start < 0:
        return html
    end_tag = f'</{tag}>'
    end = html.find(end_tag, start)
    if end < 0:
        return html
    return html[:start] + replacement + html[end + len(end_tag):]


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    if f'id="{STYLE_ID}"' in html:
        html = replace_block(html, "style", STYLE_ID, STYLE)
    else:
        html = html.replace("</head>", STYLE + "\n</head>", 1)
    if f'id="{SCRIPT_ID}"' in html:
        html = replace_block(html, "script", SCRIPT_ID, SCRIPT)
    else:
        html = html.replace("</body>", SCRIPT + "\n</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Flagship Player Props UX applied")


if __name__ == "__main__":
    main()
