from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path("docs/index.html")
STYLE_ID = "dashboard-stabilization-v2-style"
SCRIPT_ID = "dashboard-stabilization-v2-script"

STYLE = r'''<style id="dashboard-stabilization-v2-style">
.dashboardStabilityNote{margin:8px 0 14px;padding:10px 12px;border:1px solid #6b5a28;border-radius:12px;background:#201a0a;color:#e8d18a}.bestProjectionMissing{color:#d6a84b}.stabilityWarn{color:#d6a84b}
</style>'''

SCRIPT = r'''<script id="dashboard-stabilization-v2-script">
(function(){
 const arr=v=>Array.isArray(v)?v:[];
 const norm=v=>String(v??'').trim().replace(/\s+/g,' ').toLowerCase();
 const num=v=>{const x=Number(v);return Number.isFinite(x)?x:null};
 const games=arr(DATA.master?.games);
 const todayGames=games.filter(g=>String(g.bucket||'').toLowerCase()==='today');
 const teamMap=new Map();
 todayGames.forEach(g=>{
   const home=String(g.home_team||g.home||'').trim(),away=String(g.away_team||g.away||'').trim();
   if(home)teamMap.set(norm(home),{team:home,opponent:away,game:`${away} @ ${home}`});
   if(away)teamMap.set(norm(away),{team:away,opponent:home,game:`${away} @ ${home}`});
 });
 const aliases=new Map([
  ['dream','Atlanta Dream'],['atlanta dream','Atlanta Dream'],['wings','Dallas Wings'],['dallas wings','Dallas Wings'],
  ['valkyries','Golden State Valkyries'],['golden state valkyries','Golden State Valkyries'],['mercury','Phoenix Mercury'],['phoenix mercury','Phoenix Mercury']
 ]);
 const canonicalTeam=v=>aliases.get(norm(v))||String(v||'').trim();
 const playerTeamIndex=()=>{
   const out=new Map();
   arr(DATA.master?.players).forEach(p=>{if(p?.player&&p?.team)out.set(norm(p.player),canonicalTeam(p.team))});
   arr(DATA.master?.props).forEach(p=>{if(p?.player&&(p.team||p.player_team))out.set(norm(p.player),canonicalTeam(p.team||p.player_team))});
   return out;
 };
 const pteam=playerTeamIndex();
 const projectionFor=r=>{
   const direct=num(r.projection??r.pred??r.projected_value);
   if(direct!==null)return direct;
   const stat=String(r.stat||r.market||'').toUpperCase();
   const unified=arr(DATA.unified?.players||DATA.master?.unified_player_simulation_v2?.players).find(p=>norm(p.player)===norm(r.player));
   const dist=unified?.distributions?.[stat];
   return num(dist?.mean??dist?.p50);
 };
 const repairRow=r=>{
   const x={...r};
   let team=canonicalTeam(x.team||x.player_team||pteam.get(norm(x.player))||'');
   let ctx=teamMap.get(norm(team));
   if(!ctx&&team){
     for(const [k,v] of teamMap.entries())if(k.includes(norm(team))||norm(team).includes(k)){ctx=v;break}
   }
   if(ctx){x.team=ctx.team;x.opponent=ctx.opponent;x.game=ctx.game}
   else {
     if(!x.team)x.team=team||'Team unavailable';
     if(!x.opponent)x.opponent='Opponent unavailable';
     if(!x.game||/none/i.test(String(x.game)))x.game=`${x.team} vs ${x.opponent}`;
   }
   const p=projectionFor(x);if(p!==null)x.projection=p;
   return x;
 };
 const rawTop=()=>arr(DATA.cross_market?.top_plays||DATA.master?.top_plays||DATA.master?.best_bets).map(repairRow);
 const actionable=()=>rawTop().filter(r=>['BET','LEAN'].includes(String(r.decision||r.final_action||r.action||'').toUpperCase())&&(num(r.recommended_units_final??r.recommended_units)??0)>0);
 window.dashboardActiveBestBets=actionable;
 const oldKpis=window.kpis;
 if(typeof oldKpis==='function')window.kpis=function(){
   const html=oldKpis();const count=actionable().length;
   return html.replace(/(<div class="label mono">Best Bets<\/div><div class="big mono">)(.*?)(<\/div><div class="small mono">)(.*?)(<\/div>)/s,`$1${count}$3active ranked plays$5`);
 };
 const oldBest=window.best;
 window.best=function(){
   const rows=actionable();
   if(!rows.length&&typeof oldBest==='function')return oldBest();
   const units=rows.reduce((s,r)=>s+(num(r.recommended_units_final??r.recommended_units)||0),0);
   return `<div class="section"><div class="bestHeader"><div><h2 class="mono">Stabilized Best Bets</h2><div class="small mono">Only actionable BET/LEAN plays with positive allocated units are displayed. Team, opponent, matchup and projection fields are repaired from the master slate when upstream payloads are incomplete.</div></div><div class="badge mono">${rows.length} active</div></div><div class="dashboardStabilityNote mono">Allocated units ${units.toFixed(2)} · dashboard stabilization active</div><div class="bestGrid">${rows.map((r,i)=>{const p=projectionFor(r);return `<div class="bestCard"><div class="row"><div><div class="bestRank mono">#${i+1} · ${E(r.decision||'LEAN')}</div><h2 class="mono">${E(r.player||'Game market')} ${E(r.stat||'')} ${E(r.side||r.signal||'')}</h2></div><div class="bestScore mono">${E(r.top_play_score||r.final_score||r.confidence||'—')}</div></div><div class="small mono">${E(r.game||`${r.team} vs ${r.opponent}`)} · ${E(r.sportsbook||r.book||r.best_book||'Best available')}</div><div class="bestMeta"><span class="chip mono">Line ${E(S(r.line??r.consensus_line))}</span><span class="chip mono ${p===null?'bestProjectionMissing':''}">Proj ${E(p===null?'Unavailable':p)}</span><span class="chip mono">Units ${E(S(r.recommended_units_final??r.recommended_units))}</span></div></div>`}).join('')}</div></div>`;
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
    print("Dashboard stabilization v2 applied")


if __name__ == "__main__":
    main()
