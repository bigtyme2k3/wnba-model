from __future__ import annotations

from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_MARKER = "sprint25-best-bets-correlation-style"
SCRIPT_MARKER = "sprint25-best-bets-correlation-script"

STYLE = r'''<style id="sprint25-best-bets-correlation-style">
.bestPolicy{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 14px}.bestPolicy .chip{color:#b9c7df}.bestTier.top{color:var(--gold);border-color:#6f5822}.bestTier.strong{color:var(--green);border-color:#245c4b}.bestTier.watch{color:#9eb8ef}.bestTier.lean{color:#8793aa}.bestEvidence{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-top:12px}.bestEvidence div{border:1px solid #1e2c45;border-radius:10px;padding:8px}.bestEvidence b{display:block;font-size:15px}.bestEvidence span{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}@media(max-width:700px){.bestEvidence{grid-template-columns:1fr 1fr}}
</style>'''

SCRIPT = r'''<script id="sprint25-best-bets-correlation-script">
(function(){
 const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 const pct=v=>{const x=n(v);if(x===null)return null;return x>1?x/100:x};
 const side=r=>String(r.signal||r.side||'').toUpperCase();
 const stat=r=>String(r.stat||r.market||'').toUpperCase();
 const player=r=>String(r.player||'Game market');
 const game=r=>String(r.game||'');
 const line=r=>n(r.line??r.consensus_line);
 const proj=r=>n(r.projection??r.pred);
 const edge=r=>{const a=line(r),b=proj(r);return a!==null&&b!==null?Math.abs(b-a):0};
 const probability=r=>pct(r.model_probability??r.probability??r.win_probability);
 const recent=r=>pct(r.l10_hit_rate??r.hit_rate_l10??r.l5_hit_rate??r.recent_hit_rate??r.hit_rate_l5);
 const books=r=>n(r.book_count??r.books_count)??1;
 const status=r=>String(r.availability_status||r.injury_status||'').toUpperCase();
 const price=r=>n(r.odds??r.best_price??(side(r)==='UNDER'?r.best_under_price:r.best_over_price));
 const family=r=>{const s=stat(r);if(['PTS','POINTS'].includes(s))return 'SCORING';if(['REB','REBOUNDS'].includes(s))return 'REBOUNDING';if(['AST','ASSISTS'].includes(s))return 'PLAYMAKING';if(['3PM','THREES','3PT'].includes(s))return 'THREES';if(['PR','PA','RA','PRA'].includes(s))return 'COMBO';return s||'OTHER'};
 const exactKey=r=>[player(r),game(r),stat(r),side(r),line(r)??''].join('|').toLowerCase();
 const overlapKey=r=>[player(r),game(r),family(r),side(r)].join('|').toLowerCase();
 const normalizedScore=r=>{
   let s=n(r._score??r.display_score??r.final_score??r.confidence)??50;
   s=Math.min(92,Math.max(0,s));
   const pr=probability(r),rh=recent(r),bk=books(r),st=status(r),e=edge(r),od=price(r);
   if(pr!==null)s+=Math.max(-5,Math.min(6,(pr-.55)*30));
   if(rh!==null)s+=Math.max(-4,Math.min(5,(rh-.55)*20));
   if(bk>=3)s+=2; else if(bk<=1)s-=3;
   if(od!==null&&(od<-160||od>180))s-=2;
   if(['OUT','DOUBTFUL'].includes(st))return 0;
   if(['QUESTIONABLE','UNKNOWN'].includes(st))s-=9;
   if(e<2)s-=4;
   return Math.round(Math.max(0,Math.min(92,s)));
 };
 const evidenceCount=r=>{
   let c=0;if(edge(r)>=3)c++;if(probability(r)!==null)c++;if(recent(r)!==null)c++;if(books(r)>=2)c++;if(price(r)!==null)c++;if(!['QUESTIONABLE','UNKNOWN','OUT','DOUBTFUL'].includes(status(r)))c++;return c;
 };
 const tierFor=r=>{const s=r._cardScore,c=evidenceCount(r),pr=probability(r),rh=recent(r);if(s>=82&&c>=5&&pr!==null&&rh!==null)return 'TOP PLAY';if(s>=75&&c>=4&&(pr!==null||rh!==null))return 'STRONG';if(s>=66)return 'WATCH';return 'LEAN'};
 const card=()=>{
   const src=A(DATA.master?.best_bets).length?A(DATA.master?.best_bets):A(DATA.master?.props);
   const exact=new Map();
   src.forEach(r=>{const x={...r,_cardScore:normalizedScore(r)};const k=exactKey(x),p=exact.get(k);if(!p||x._cardScore>p._cardScore)exact.set(k,x)});
   const overlap=new Map();
   [...exact.values()].sort((a,b)=>b._cardScore-a._cardScore).forEach(r=>{const k=overlapKey(r);if(!overlap.has(k))overlap.set(k,r)});
   const chosen=[],perPlayer=new Map(),perGame=new Map();
   for(const r of [...overlap.values()].sort((a,b)=>b._cardScore-a._cardScore)){
     if(r._cardScore<60)continue;
     const p=player(r),g=game(r),pc=perPlayer.get(p)||0,gc=perGame.get(g)||0;
     if(pc>=2||gc>=3)continue;
     chosen.push(r);perPlayer.set(p,pc+1);perGame.set(g,gc+1);
     if(chosen.length>=10)break;
   }
   return chosen;
 };
 const tierClass=t=>t==='TOP PLAY'?'top':t==='STRONG'?'strong':t==='WATCH'?'watch':'lean';
 const fmtPct=v=>v===null?'—':`${Math.round(v*100)}%`;
 const why=r=>{const out=[];if(edge(r)>0)out.push(`Projection edge ${edge(r).toFixed(1)} versus line`);if(probability(r)!==null)out.push(`Model probability ${fmtPct(probability(r))}`);if(recent(r)!==null)out.push(`Recent evidence ${fmtPct(recent(r))}`);if(books(r)>=2)out.push(`${books(r)} sportsbook feeds available`);if(status(r))out.push(`Availability: ${status(r)}`);return out.slice(0,4)};
 window.best=function(){
   const rows=card();
   return `<div class="section"><div class="bestHeader"><div><h2 class="mono">Best Bets Card</h2><div class="small mono">Correlation-aware shortlist. Maximum two plays per player, three per matchup, and one overlapping market family per player and side.</div></div><div class="badge mono">Card ${rows.length}</div></div><div class="bestPolicy"><span class="chip mono">Max 2/player</span><span class="chip mono">Max 3/game</span><span class="chip mono">Overlapping combos reduced</span><span class="chip mono">Evidence-gated tiers</span></div><div class="bestGrid">${rows.map((r,i)=>{const t=tierFor(r);return `<div class="bestCard"><div class="row"><div><div class="bestRank mono">#${i+1} · ${E(t)}</div><h2 class="mono">${E(player(r))} ${E(stat(r))} ${E(side(r))}</h2></div><div class="bestScore mono">${E(r._cardScore)}</div></div><div class="small mono">${E(game(r)||'-')} · ${E(r.book||r.best_book||r.best_over_book||r.best_under_book||'Best available')}</div><div class="bestMeta"><span class="chip mono">Line ${E(S(line(r)))}</span><span class="chip mono">Proj ${E(S(proj(r)))}</span><span class="bestTier ${tierClass(t)} mono">${E(t)}</span></div><div class="bestEvidence"><div><b class="mono">${edge(r).toFixed(1)}</b><span>Edge</span></div><div><b class="mono">${fmtPct(probability(r))}</b><span>Model prob</span></div><div><b class="mono">${fmtPct(recent(r))}</b><span>Recent</span></div><div><b class="mono">${books(r)}</b><span>Books</span></div></div><ul class="bestWhy">${why(r).map(x=>`<li>${E(x)}</li>`).join('')}</ul></div>`}).join('')||'<div class="empty mono">No bets cleared the correlation and evidence gates.</div>'}</div></div>`;
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
    print("Sprint 25 correlation-aware Best Bets card applied")


if __name__ == "__main__":
    main()
