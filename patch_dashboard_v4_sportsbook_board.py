from __future__ import annotations

import json
from pathlib import Path

DASHBOARD = Path("docs/index.html")
CONSENSUS = Path("data/dashboard/wnba_sportsbook_consensus.json")
STYLE_MARKER = "sprint25-sportsbook-board-style"
SCRIPT_MARKER = "sprint25-sportsbook-board-script"

STYLE = r'''<style id="sprint25-sportsbook-board-style">
.bookKpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}.bookKpi{border:1px solid var(--line);background:#081321;border-radius:14px;padding:13px}.bookKpi b{display:block;color:var(--green);font-size:24px}.bookControls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:10px;margin:14px 0}.bookControls input,.bookControls select{width:100%;background:#07101d;color:#e8eef8;border:1px solid var(--line);border-radius:10px;padding:11px}.bookTable{overflow:auto}.bookTable table{min-width:1050px}.bestPrice{color:var(--green);font-weight:900}.bookBadge{display:inline-block;border:1px solid #2c405e;border-radius:999px;padding:3px 8px;margin:2px;font-size:10px}.singleFeed{color:#e0ae62}.multiBook{color:var(--green)}@media(max-width:800px){.bookKpis{grid-template-columns:1fr 1fr}.bookControls{grid-template-columns:1fr}}
</style>'''

SCRIPT = r'''<script id="sprint25-sportsbook-board-script">
(function(){
 const CONSENSUS=__CONSENSUS__;
 const state={query:'',game:'ALL',stat:'ALL'};
 const rows=()=>A(CONSENSUS?.markets);
 const gamesList=()=>[...new Set(rows().map(r=>r.game).filter(Boolean))].sort();
 const statsList=()=>[...new Set(rows().map(r=>r.stat).filter(Boolean))].sort();
 const price=v=>{if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)?`${n>0?'+':''}${n}`:'—'};
 const pct=v=>{if(v===null||v===undefined||v==='')return '—';const n=Number(v);return Number.isFinite(n)?`${(n*100).toFixed(1)}%`:'—'};
 const filtered=()=>rows().filter(r=>{
   const text=`${r.player||''} ${r.game||''} ${r.stat||''}`.toLowerCase();
   return (!state.query||text.includes(state.query))&&(state.game==='ALL'||r.game===state.game)&&(state.stat==='ALL'||r.stat===state.stat);
 }).sort((a,b)=>(b.book_count||0)-(a.book_count||0)||(b.line_range||0)-(a.line_range||0)).slice(0,250);
 const options=(values,current)=>`<option value="ALL">All</option>${values.map(v=>`<option value="${E(v)}" ${v===current?'selected':''}>${E(v)}</option>`).join('')}`;
 window.wireSportsbookBoard=function(){
   const search=document.getElementById('bookSearch'),gameSel=document.getElementById('bookGame'),statSel=document.getElementById('bookStat');
   if(search)search.oninput=e=>{state.query=e.target.value.toLowerCase();q('root').innerHTML=books();};
   if(gameSel)gameSel.onchange=e=>{state.game=e.target.value;q('root').innerHTML=books();};
   if(statSel)statSel.onchange=e=>{state.stat=e.target.value;q('root').innerHTML=books();};
 };
 window.books=function(){
   const s=CONSENSUS?.summary||{},list=filtered();
   setTimeout(window.wireSportsbookBoard,0);
   return `<div class="section"><h2 class="mono">Sportsbook Line Shopping</h2><div class="small mono">Consensus and best available prices from DraftKings, FanDuel and Fanatics. Individual book rows are shown only when supplied by the source artifact.</div>
   <div class="bookKpis"><div class="bookKpi mono"><span>Markets</span><b>${E(s.markets||0)}</b></div><div class="bookKpi mono"><span>Multi-book</span><b>${E(s.multi_book_markets||0)}</b></div><div class="bookKpi mono"><span>Single-feed</span><b>${E(s.single_feed_markets||0)}</b></div><div class="bookKpi mono"><span>Books</span><b>${E(A(s.books_detected).length)}</b></div></div>
   <div class="bookControls"><input id="bookSearch" placeholder="Search player, game or market" value="${E(state.query)}"><select id="bookGame">${options(gamesList(),state.game)}</select><select id="bookStat">${options(statsList(),state.stat)}</select></div>
   <div class="bookTable"><table><thead><tr><th>Player / Game</th><th>Stat</th><th>Consensus line</th><th>Best over</th><th>Best under</th><th>Consensus O/U</th><th>Books</th><th>Status</th></tr></thead><tbody>${list.map(r=>`<tr><td><b>${E(r.player||'Game market')}</b><div class="small mono">${E(r.game||'-')}</div></td><td>${E(r.stat||'-')}</td><td>${E(r.consensus_line??'-')}<div class="small mono">Range ${E(r.line_range??'-')}</div></td><td class="bestPrice">${E(price(r.best_over_price))}<div class="small mono">${E(r.best_over_book||'—')}</div></td><td class="bestPrice">${E(price(r.best_under_price))}<div class="small mono">${E(r.best_under_book||'—')}</div></td><td>${E(pct(r.consensus_over_probability))} / ${E(pct(r.consensus_under_probability))}</td><td>${A(r.books).map(b=>`<span class="bookBadge">${E(b)}</span>`).join('')}</td><td class="${r.status==='multi_book'?'multiBook':'singleFeed'}">${E(r.status||'-')}<div class="small mono">${E(r.book_count||0)} books</div></td></tr>`).join('')||'<tr><td colspan="8" class="empty mono">No matching sportsbook markets.</td></tr>'}</tbody></table></div></div>`;
 };
 try{render('games')}catch(e){}
})();
</script>'''


def load_consensus() -> dict:
    try:
        value = json.loads(CONSENSUS.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception as exc:
        print(f"[warn] unable to load sportsbook consensus: {exc}")
        return {}


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    if STYLE_MARKER not in html:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if SCRIPT_MARKER not in html:
        script = SCRIPT.replace("__CONSENSUS__", json.dumps(load_consensus(), separators=(",", ":"), ensure_ascii=False))
        html = html.replace("</body>", script + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Sprint 25 sportsbook line-shopping board applied")


if __name__ == "__main__":
    main()
