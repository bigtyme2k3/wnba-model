from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_MARKER = "sprint25-best-bets-cleanup-style"
SCRIPT_MARKER = "sprint25-best-bets-cleanup-script"

STYLE = r'''<style id="sprint25-best-bets-cleanup-style">
.bestHeader{display:flex;justify-content:space-between;gap:14px;align-items:end;margin-bottom:14px}.bestGrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.bestCard{border:1px solid var(--line);background:#08111e;border-radius:18px;padding:16px}.bestRank{font-size:12px;color:var(--muted);letter-spacing:.14em;text-transform:uppercase}.bestScore{font-size:30px;font-weight:900;color:var(--green)}.bestTier{display:inline-block;border:1px solid #2f466b;border-radius:999px;padding:4px 9px;margin-top:6px}.bestWhy{margin:10px 0 0;padding-left:18px;color:#b8c5db;font-size:13px}.bestWhy li{margin:5px 0}.bestMeta{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}@media(max-width:800px){.bestGrid{grid-template-columns:1fr}.bestHeader{display:block}}
</style>'''

SCRIPT = r'''<script id="sprint25-best-bets-cleanup-script">
(function(){
 const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
 const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
 const key=r=>[r.player||'',r.game||'',r.stat||'',r.signal||r.side||'',r.line??r.consensus_line??''].join('|').toLowerCase();
 const scoreBet=r=>{
   const line=num(r.line??r.consensus_line),proj=num(r.projection??r.pred),prob=num(r.model_probability??r.probability??r.win_probability),edge=(line!==null&&proj!==null)?Math.abs(proj-line):0;
   const l5=num(r.l5_hit_rate??r.recent_hit_rate??r.hit_rate_l5),l10=num(r.l10_hit_rate??r.hit_rate_l10),books=num(r.book_count),price=num(r.odds??r.best_price??(String(r.signal||r.side).toUpperCase()==='UNDER'?r.best_under_price:r.best_over_price));
   let s=50;
   s+=clamp(edge*2.2,0,18);
   if(prob!==null)s+=clamp((prob-(prob>1?50:.5))*(prob>1?.35:35),-8,16);
   if(l5!==null)s+=clamp(((l5>1?l5/100:l5)-.5)*24,-6,10);
   if(l10!==null)s+=clamp(((l10>1?l10/100:l10)-.5)*18,-5,8);
   if(books!==null)s+=clamp((books-1)*2,0,5);
   if(price!==null&&price>=-135&&price<=140)s+=3;
   const status=String(r.availability_status||r.injury_status||'').toUpperCase();
   if(['OUT','DOUBTFUL'].includes(status))s=0; else if(['QUESTIONABLE','UNKNOWN'].includes(status))s-=12;
   return Math.round(clamp(s,0,92));
 };
 const tier=s=>s>=82?'TOP PLAY':s>=74?'STRONG':s>=66?'WATCH':'LEAN';
 const reasons=r=>{
   const out=[];const line=num(r.line??r.consensus_line),proj=num(r.projection??r.pred),books=num(r.book_count);
   if(line!==null&&proj!==null)out.push(`Projection edge ${Math.abs(proj-line).toFixed(1)} versus line`);
   if(num(r.l5_hit_rate??r.recent_hit_rate)!=null)out.push('Recent form included in score');
   if(books&&books>1)out.push(`${books} sportsbook feeds available`);
   const st=String(r.availability_status||r.injury_status||'').toUpperCase();if(st)out.push(`Availability: ${st}`);
   return out.slice(0,3);
 };
 const ranked=()=>{
   const src=A(DATA.master?.best_bets).length?A(DATA.master?.best_bets):A(DATA.master?.props);
   const map=new Map();
   src.forEach(r=>{const k=key(r),s=scoreBet(r),prev=map.get(k);if(!prev||s>prev._score)map.set(k,{...r,_score:s});});
   return [...map.values()].filter(r=>r._score>=60).sort((a,b)=>b._score-a._score).slice(0,12);
 };
 window.best=function(){
   const rows=ranked();
   return `<div class="section"><div class="bestHeader"><div><h2 class="mono">Best Bets Shortlist</h2><div class="small mono">Deduplicated across books. Scores are capped at 92 and reflect projection edge, market price, recent evidence, book coverage and availability.</div></div><div class="badge mono">Top ${rows.length}</div></div><div class="bestGrid">${rows.map((r,i)=>`<div class="bestCard"><div class="row"><div><div class="bestRank mono">#${i+1} · ${E(tier(r._score))}</div><h2 class="mono">${E(r.player||'Game market')} ${E(r.stat||'')} ${E(r.signal||r.side||'')}</h2></div><div class="bestScore mono">${E(r._score)}</div></div><div class="small mono">${E(r.game||'-')} · ${E(r.book||r.best_book||r.best_over_book||r.best_under_book||'Best available')}</div><div class="bestMeta"><span class="chip mono">Line ${E(S(r.line??r.consensus_line))}</span><span class="chip mono">Proj ${E(S(r.projection??r.pred))}</span><span class="chip mono">${E(tier(r._score))}</span></div><ul class="bestWhy">${reasons(r).map(x=>`<li>${E(x)}</li>`).join('')}</ul></div>`).join('')||'<div class="empty mono">No bets cleared the current shortlist threshold.</div>'}</div></div>`;
 };
 try{render('games')}catch(e){}
})();
</script>'''


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    if STYLE_MARKER not in html:
        html = html.replace("</head>", STYLE + "</head>", 1)
    if SCRIPT_MARKER not in html:
        html = html.replace("</body>", SCRIPT + "</body>", 1)
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Sprint 25 Best Bets cleanup applied")


if __name__ == "__main__":
    main()
