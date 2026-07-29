from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "sprint25-best-bets-evidence-fix-style"
SCRIPT_ID = "sprint25-best-bets-evidence-fix-script"

STYLE = r'''<style id="sprint25-best-bets-evidence-fix-style">
.bestScoreNote{font-size:11px;color:var(--muted);margin-top:3px}.bestMissing{color:#d6a84b}.bestEvidence b.missing{color:#7e8aa2}
</style>'''

SCRIPT = r'''<script id="sprint25-best-bets-evidence-fix-script">
(function(){
 const n=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 const pct=v=>{const x=n(v);if(x===null)return null;return x>1?x/100:x};
 const norm=v=>String(v??'').trim().replace(/\s+/g,' ').toLowerCase();
 const side=r=>String(r.signal||r.side||'').trim().toUpperCase();
 const stat=r=>String(r.stat||r.market||'').trim().toUpperCase();
 const player=r=>String(r.player||'Game market').trim();
 const game=r=>String(r.game||'').trim();
 const line=r=>n(r.line??r.consensus_line);
 const proj=r=>n(r.projection??r.pred);
 const edge=r=>{const a=line(r),b=proj(r);return a!==null&&b!==null?Math.abs(b-a):0};
 const probability=r=>pct(r.model_probability??r.probability??r.win_probability);
 const recent=r=>pct(r.l10_hit_rate??r.hit_rate_l10??r.l5_hit_rate??r.recent_hit_rate??r.hit_rate_l5);
 const books=r=>n(r.book_count??r.books_count)??1;
 const status=r=>String(r.availability_status||r.injury_status||'').trim().toUpperCase();
 const price=r=>n(r.odds??r.best_price??(side(r)==='UNDER'?r.best_under_price:r.best_over_price));
 const family=r=>{const s=stat(r);if(['PTS','POINTS','PR','PA','RA','PRA'].includes(s))return 'OFFENSE';if(['REB','REBOUNDS'].includes(s))return 'REBOUNDING';if(['AST','ASSISTS'].includes(s))return 'PLAYMAKING';if(['3PM','THREES','3PT'].includes(s))return 'THREES';return s||'OTHER'};
 const rounded=v=>v===null?'':Number(v).toFixed(2);
 const exactKey=r=>[norm(player(r)),norm(game(r)),stat(r),side(r),rounded(line(r))].join('|');
 const overlapKey=r=>[norm(player(r)),norm(game(r)),family(r),side(r)].join('|');
 const rawScore=r=>{
   const e=edge(r),pr=probability(r),rh=recent(r),bk=books(r),od=price(r),st=status(r);
   if(['OUT','DOUBTFUL'].includes(st))return 0;
   let s=42;
   s+=Math.max(0,Math.min(20,e*2));
   if(pr!==null)s+=Math.max(-5,Math.min(16,(pr-.50)*40));
   else s-=7;
   if(rh!==null)s+=Math.max(-4,Math.min(12,(rh-.50)*30));
   else s-=6;
   if(bk>=3)s+=5;else if(bk===2)s+=3;else s-=2;
   if(od!==null){if(od>=-135&&od<=140)s+=4;else if(od<-175||od>220)s-=3}else s-=2;
   if(['QUESTIONABLE','UNKNOWN'].includes(st))s-=10;
   if(e<2)s-=5;
   return Math.round(Math.max(0,Math.min(92,s)));
 };
 const evidenceCount=r=>{let c=0;if(edge(r)>=3)c++;if(probability(r)!==null)c++;if(recent(r)!==null)c++;if(books(r)>=2)c++;if(price(r)!==null)c++;if(!['QUESTIONABLE','UNKNOWN','OUT','DOUBTFUL'].includes(status(r)))c++;return c};
 const tierFor=r=>{const s=r._cardScore,c=evidenceCount(r),pr=probability(r),rh=recent(r);if(s>=84&&c>=5&&pr!==null&&rh!==null)return 'TOP PLAY';if(s>=76&&c>=4&&(pr!==null||rh!==null))return 'STRONG';if(s>=64)return 'WATCH';return 'LEAN'};
 const buildCard=()=>{
   const src=A(DATA.master?.best_bets).length?A(DATA.master?.best_bets):A(DATA.master?.props);
   const exact=new Map();
   src.forEach(r=>{const x={...r,_cardScore:rawScore(r)};const k=exactKey(x),p=exact.get(k);if(!p||x._cardScore>p._cardScore)exact.set(k,x)});
   const overlap=new Map();
   [...exact.values()].sort((a,b)=>b._cardScore-a._cardScore).forEach(r=>{const k=overlapKey(r);if(!overlap.has(k))overlap.set(k,r)});
   const selected=[],perPlayer=new Map(),perGame=new Map(),finalKeys=new Set();
   for(const r of [...overlap.values()].sort((a,b)=>b._cardScore-a._cardScore)){
     if(r._cardScore<58)continue;
     const k=exactKey(r);if(finalKeys.has(k))continue;
     const p=norm(player(r)),g=norm(game(r)),pc=perPlayer.get(p)||0,gc=perGame.get(g)||0;
     if(pc>=2||gc>=3)continue;
     selected.push(r);finalKeys.add(k);perPlayer.set(p,pc+1);perGame.set(g,gc+1);
     if(selected.length>=10)break;
   }
   return selected;
 };
 const fmtPct=v=>v===null?'—':`${Math.round(v*100)}%`;
 const tierClass=t=>t==='TOP PLAY'?'top':t==='STRONG'?'strong':t==='WATCH'?'watch':'lean';
 const why=r=>{const out=[];if(edge(r)>0)out.push(`Projection edge ${edge(r).toFixed(1)} versus line`);if(probability(r)!==null)out.push(`Model probability ${fmtPct(probability(r))}`);else out.push('Model probability unavailable');if(recent(r)!==null)out.push(`Recent evidence ${fmtPct(recent(r))}`);else out.push('Recent evidence unavailable');if(books(r)>=2)out.push(`${books(r)} sportsbook feeds available`);return out.slice(0,4)};
 window.best=function(){
   const rows=buildCard();
   return `<div class="section"><div class="bestHeader"><div><h2 class="mono">Best Bets Card</h2><div class="small mono">Correlation-aware and evidence-scored. Missing probability or recent evidence lowers the score; it can no longer inherit a previous 92.</div></div><div class="badge mono">Card ${rows.length}</div></div><div class="bestPolicy"><span class="chip mono">Max 2/player</span><span class="chip mono">Max 3/game</span><span class="chip mono">Hard dedup</span><span class="chip mono">Evidence penalties active</span></div><div class="bestGrid">${rows.map((r,i)=>{const t=tierFor(r),pr=probability(r),rh=recent(r);return `<div class="bestCard"><div class="row"><div><div class="bestRank mono">#${i+1} · ${E(t)}</div><h2 class="mono">${E(player(r))} ${E(stat(r))} ${E(side(r))}</h2></div><div><div class="bestScore mono">${E(r._cardScore)}</div><div class="bestScoreNote mono">evidence score</div></div></div><div class="small mono">${E(game(r)||'-')} · ${E(r.book||r.best_book||r.best_over_book||r.best_under_book||'Best available')}</div><div class="bestMeta"><span class="chip mono">Line ${E(S(line(r)))}</span><span class="chip mono">Proj ${E(S(proj(r)))}</span><span class="bestTier ${tierClass(t)} mono">${E(t)}</span></div><div class="bestEvidence"><div><b class="mono">${edge(r).toFixed(1)}</b><span>Edge</span></div><div><b class="mono ${pr===null?'missing':''}">${fmtPct(pr)}</b><span>Model prob</span></div><div><b class="mono ${rh===null?'missing':''}">${fmtPct(rh)}</b><span>Recent</span></div><div><b class="mono">${books(r)}</b><span>Books</span></div></div><ul class="bestWhy">${why(r).map(x=>`<li class="${x.includes('unavailable')?'bestMissing':''}">${E(x)}</li>`).join('')}</ul></div>`}).join('')||'<div class="empty mono">No bets cleared the correlation and evidence gates.</div>'}</div></div>`;
 };
 try{render('games')}catch(e){}
})();
</script>'''


def replace_or_insert(html: str, element_id: str, block: str, closing: str) -> str:
    pattern = re.compile(rf'<(?:style|script) id="{re.escape(element_id)}">.*?</(?:style|script)>', re.S)
    if pattern.search(html):
        return pattern.sub(block, html, count=1)
    return html.replace(closing, block + closing, 1)


def main() -> None:
    if not DASHBOARD.exists():
        raise FileNotFoundError(DASHBOARD)
    html = DASHBOARD.read_text(encoding="utf-8")
    html = replace_or_insert(html, STYLE_ID, STYLE, "</head>")
    html = replace_or_insert(html, SCRIPT_ID, SCRIPT, "</body>")
    DASHBOARD.write_text(html, encoding="utf-8")
    print("Sprint 25 Best Bets evidence score and hard dedup fix applied")


if __name__ == "__main__":
    main()
