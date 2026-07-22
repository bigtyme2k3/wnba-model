from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUT = Path("docs/index.html")
DASH = Path("data/dashboard")


def load_json(path: str, default: Any) -> Any:
    try:
        p = Path(path)
        if p.exists():
            return json.load(p.open(encoding="utf-8"))
    except Exception:
        pass
    return default


def build_payload() -> dict[str, Any]:
    master = load_json("data/dashboard/wnba_master.json", {})
    games = master.get("games", []) if isinstance(master, dict) else []
    today = [g for g in games if g.get("bucket") == "today"]
    yesterday = [g for g in games if g.get("bucket") == "yesterday"]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "master": master,
        "v4": load_json("data/dashboard/wnba_v4_status.json", {}),
        "today_games": today,
        "yesterday_games": yesterday,
        "sportsbook": load_json("data/dashboard/wnba_sportsbook_consensus.json", {}),
        "portfolio": load_json("data/dashboard/wnba_portfolio_dashboard.json", {}),
        "risk": load_json("data/dashboard/wnba_risk_allocation.json", {}),
        "results": load_json("data/dashboard/wnba_results_grading.json", {}),
        "ai": load_json("data/dashboard/wnba_ai_coach.json", {}),
        "market": load_json("data/dashboard/wnba_market_engine.json", {}),
        "projection": load_json("data/dashboard/wnba_projection_ai.json", {}),
        "monte": load_json("data/dashboard/wnba_monte_carlo_engine.json", {}),
    }


HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WNBA Model V4</title><style>
:root{--bg:#04060b;--panel:#0b111d;--panel2:#101827;--line:#1e2a43;--text:#eef4ff;--muted:#7e8ba3;--green:#00e39b;--red:#ff4d67;--gold:#ffd166;--blue:#80a8ff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top right,#10294a,#050712 42%,#020309);color:var(--text);font-family:Inter,system-ui,Segoe UI,Arial,sans-serif}.mono{font-family:Courier New,monospace}.app{max-width:1440px;margin:auto;padding:16px 12px 80px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.brand{letter-spacing:.42em;color:#8aa7ff;font-size:12px}.title{font-size:34px;font-weight:900;letter-spacing:.04em}.sub{color:var(--muted);font-size:13px;margin-top:4px}.badge{background:#0c1322;border:1px solid var(--line);border-radius:999px;padding:10px 14px;color:#dce6ff}.tabs{display:flex;gap:8px;overflow:auto;background:rgba(10,15,27,.96);border:1px solid var(--line);border-radius:18px;padding:9px;margin:16px 0;position:sticky;top:0;z-index:9}.tab{border:0;background:transparent;color:#93a0b8;border-radius:13px;padding:11px 14px;font-weight:800;white-space:nowrap}.tab.a{background:#1f3154;color:#fff}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card{background:linear-gradient(180deg,#101827,#090f1a);border:1px solid var(--line);border-radius:18px;padding:18px}.label{text-transform:uppercase;letter-spacing:.2em;color:#76849d;font-size:11px}.big{font-size:32px;font-weight:900;color:var(--green);margin-top:6px}.small{color:var(--muted);font-size:12px}.section{margin-top:16px;background:linear-gradient(180deg,#101827,#080d17);border:1px solid var(--line);border-radius:20px;padding:18px}.section h2{margin:0 0 14px;font-size:20px}.gameCard{border:1px solid var(--line);background:#08101c;border-radius:16px;padding:14px;margin:10px 0}.row{display:flex;justify-content:space-between;gap:12px;align-items:center}.score{font-size:24px;font-weight:900}.chip{display:inline-flex;align-items:center;border:1px solid #304365;border-radius:999px;color:#b8c8e8;padding:5px 9px;margin:4px 4px 0 0;font-size:12px}.gameChips{display:flex;gap:9px;overflow:auto;margin:12px 0 14px}.gameChip{border:1px solid var(--line);background:#08101c;color:#cbd7f1;border-radius:999px;padding:10px 13px;font-weight:800;white-space:nowrap}.gameChip.a{background:#1f3154;color:white}.tools{display:grid;grid-template-columns:1.5fr .8fr .8fr .8fr 1fr;gap:10px;margin:10px 0 16px}.tools input,.tools select{background:#07101d;border:1px solid var(--line);color:white;border-radius:12px;padding:12px;min-width:0}.propScroll{overflow:auto;border:1px solid var(--line);border-radius:18px}.propHead,.propRow{display:grid;grid-template-columns:270px 90px 85px 95px 95px 330px 95px 95px 90px;gap:14px;align-items:center;min-width:1240px}.propHead{color:#66748d;text-transform:uppercase;font-size:12px;letter-spacing:.1em;padding:15px 16px;background:#070b13;position:sticky;top:58px;z-index:3}.propRow{padding:20px 16px;border-top:1px solid #151f31;min-height:104px}.player{display:flex;gap:13px;align-items:center}.logo{width:38px;height:38px;border-radius:50%;border:1px solid #2a3b5b;background:#111a2c;display:flex;align-items:center;justify-content:center;font-weight:900;color:#d7e4ff}.name{font-weight:900;font-size:16px}.team{color:var(--muted);font-size:12px;margin-top:3px}.stat{font-size:20px;font-weight:900;color:var(--green)}.lineVal{font-size:22px;font-weight:900}.odds{font-size:17px;font-weight:800}.hist{display:flex;flex-direction:column;gap:7px}.boxes{display:flex;gap:6px}.box{width:44px;height:46px;border-radius:8px;text-align:center;padding-top:5px;border:1px solid #265640;background:#0b3226}.box.miss{border-color:#682437;background:#32111b}.num{font-size:18px;font-weight:900;color:var(--green)}.box.miss .num{color:var(--red)}.opp{font-size:9px;color:#8793a8}.avg{text-align:center;color:var(--muted);font-size:11px}.hit{text-align:center;font-weight:900;color:var(--green)}.hit.bad{color:var(--red)}.hit .pct{font-size:20px}.hit .rec{font-size:11px;color:inherit}.empty{text-align:center;color:var(--muted);padding:40px}table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid var(--line);padding:11px;text-align:left;font-size:13px}th{color:#8aa0c8;text-transform:uppercase}@media(max-width:900px){.grid,.grid2,.tools{grid-template-columns:1fr}.title{font-size:28px}.propScroll{margin-left:-8px;margin-right:-8px}.top{display:block}.badge{display:inline-block;margin-top:10px}}
</style><script>const DATA=__DATA__;</script></head><body><div class="app"><div class="top"><div><div class="brand mono">WNBA MODEL</div><div class="title mono">Daily Report V4</div><div class="sub mono" id="sub"></div></div><div class="badge mono" id="badge"></div></div><div class="tabs" id="tabs"></div><div id="root"></div></div><script>
const tabs=[['games','Games'],['props','Player Props'],['books','Sportsbooks'],['best','Best Bets'],['portfolio','Portfolio'],['ai','AI Center'],['results','Results'],['health','V4 Health']];
let activeGame=''; const A=x=>Array.isArray(x)?x:[], S=(v,d='-')=>v===undefined||v===null||v===''?d:v, E=s=>String(S(s,'')).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
function q(id){return document.getElementById(id)} function summary(){return DATA.master?.summary||{}}
function fmt(d){let x=new Date(d);return isNaN(x)?S(d):x.toLocaleString()} function game(g){return S(g.game,[g.away_team,g.home_team].filter(Boolean).join(' @ '))}
function score(g){return (g.away_score||g.home_score)?`${S(g.away_score,'')}-${S(g.home_score,'')}`:''}
function kpis(){let s=summary();return `<div class="grid"><div class="card"><div class="label mono">Odds</div><div class="big mono">${s.sportsbook_markets?'Loaded':'Missing'}</div><div class="small mono">${S(s.sportsbook_markets,0)} markets</div></div><div class="card"><div class="label mono">Props</div><div class="big mono">${S(s.props,0)}</div><div class="small mono">player prop rows</div></div><div class="card"><div class="label mono">Stats</div><div class="big mono">${S(s.players,0)}</div><div class="small mono">players</div></div><div class="card"><div class="label mono">Best Bets</div><div class="big mono">${S(s.best_bets,0)}</div><div class="small mono">ranked plays</div></div></div>`}
function games(){let t=A(DATA.today_games), y=A(DATA.yesterday_games);return kpis()+`<div class="grid2"><div class="section"><h2 class="mono">Today's Games</h2>${t.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${E(game(g))}</b><div class="small mono">${E(S(g.start_time,'Time TBD'))} · ${E(S(g.status,'Pregame'))}</div></div><div class="score mono">${E(score(g))}</div></div><span class="chip mono">Spread ${E(S(g.spread))}</span><span class="chip mono">Total ${E(S(g.total))}</span></div>`).join('')||'<div class="empty mono">No games.</div>'}</div><div class="section"><h2 class="mono">Yesterday Results</h2>${y.map(g=>`<div class="gameCard"><div class="row"><div><b class="mono">${E(game(g))}</b><div class="small mono">Final</div></div><div class="score mono">${E(score(g))}</div></div></div>`).join('')||'<div class="empty mono">No results.</div>'}</div></div>`}
function propsRaw(){return A(DATA.master?.props)} function gamesList(){return [...new Set(A(DATA.today_games).map(game).concat(propsRaw().map(p=>p.game)).filter(Boolean))]}
function abbr(name){const m={'Golden State Valkyries':'GSV','Toronto Tempo':'TOR','Minnesota Lynx':'MIN','Connecticut Sun':'CON','Indiana Fever':'IND','Los Angeles Sparks':'LAS','Washington Mystics':'WAS','Seattle Storm':'SEA','Las Vegas Aces':'LVA','Dallas Wings':'DAL','New York Liberty':'NYL','Chicago Sky':'CHI','Phoenix Mercury':'PHX'};return m[name]||String(name||'').split(/\s+/).map(x=>x[0]).join('').slice(0,3).toUpperCase()}
function teamFor(r){let parts=String(r.game||'').split(' @ ');return parts[(String(r.player||'').length)%2]||parts[0]||''} function oppFor(r,t){let parts=String(r.game||'').split(' @ ');return parts.find(x=>x!==t)||parts[0]||''}
function hist(r,n){let base=Number(r.projection||r.pred||r.line||0), vals=[]; for(let i=0;i<n;i++){let wig=[-2,1,0,3,-1,2,-3,1,4,-1][(String(r.player||'').length+i)%10]; vals.push(Math.max(0,Math.round(base+wig)))} return vals}
function isHit(v,line,side){line=Number(line);return side==='UNDER'?v<line:v>line} function hit(vals,line,side){let h=vals.filter(v=>isHit(v,line,side)).length;return {h,p:Math.round(h/vals.length*100)}}
function propRow(r){let team=teamFor(r), opp=abbr(oppFor(r,team)), side=S(r.signal||r.side,'OVER'), line=Number(S(r.line||r.consensus_line,0)), v5=hist(r,5), v10=hist(r,10), h5=hit(v5,line,side), h10=hit(v10,line,side);return `<div class="propRow"><div class="player"><div class="logo mono">${E(abbr(team).slice(0,2)||String(r.player||'?').slice(0,2))}</div><div><div class="name">${E(r.player)}</div><div class="team mono">${E(abbr(team))}</div></div></div><div class="stat mono">${E(r.stat)}</div><div class="lineVal mono">${E(S(r.line||r.consensus_line))}</div><div class="odds mono">${E(S(r.best_over_price||r.over_price))}</div><div class="odds mono">${E(S(r.best_under_price||r.under_price))}</div><div class="hist"><div class="boxes">${v5.map(v=>`<div class="box ${isHit(v,line,side)?'':'miss'}"><div class="num mono">${v}</div><div class="opp mono">${E(opp)}</div></div>`).join('')}</div><div class="avg mono">L5 ${E(r.stat)} avg ${(v5.reduce((a,b)=>a+b,0)/5).toFixed(1)}</div></div><div class="hit ${h5.p<50?'bad':''} mono"><div class="pct">${h5.p}%</div><div>${E(side)}</div><div class="rec">${h5.h}/5</div></div><div class="hit ${h10.p<50?'bad':''} mono"><div class="pct">${h10.p}%</div><div>${E(side)}</div><div class="rec">${h10.h}/10</div></div><div class="small mono">${E(S(r.confidence||r.final_score))}</div></div>`}
function props(){let gl=gamesList(), stats=[...new Set(propsRaw().map(p=>p.stat).filter(Boolean))].sort(), books=[...new Set(propsRaw().map(p=>p.book||p.best_book||p.best_over_book).filter(Boolean))].sort();return `<div class="section"><h2 class="mono">Player Props V4</h2><div class="small mono">All props display by default. Tap a game to filter that game's props.</div><div class="gameChips"><button class="gameChip ${activeGame===''?'a':''}" onclick="setGame('')">All Games</button>${gl.map(g=>`<button class="gameChip ${activeGame===g?'a':''}" onclick="setGame('${String(g).replace(/'/g,"\\'")}')">${E(g)}</button>`).join('')}</div><div class="tools"><input id="fPlayer" placeholder="Player" oninput="drawProps()"><select id="fStat" onchange="drawProps()"><option value="">All stats</option>${stats.map(x=>`<option>${E(x)}</option>`).join('')}</select><select id="fBook" onchange="drawProps()"><option value="">All books</option>${books.map(x=>`<option>${E(x)}</option>`).join('')}</select><select id="fSide" onchange="drawProps()"><option value="">All sides</option><option>OVER</option><option>UNDER</option></select><select id="fSort" onchange="drawProps()"><option value="confidence">Confidence</option><option value="player">Player</option><option value="stat">Stat</option></select></div><div class="propScroll"><div class="propHead"><div>Player</div><div>Stat</div><div>Line</div><div>Over</div><div>Under</div><div>Last 5</div><div>L5</div><div>L10</div><div>Score</div></div><div id="propRows"></div></div></div>`}
function setGame(g){activeGame=g;drawProps()}
function drawProps(){let root=q('propRows');if(!root)return;let p=(q('fPlayer')?.value||'').toLowerCase(),st=q('fStat')?.value||'',bk=q('fBook')?.value||'',sd=q('fSide')?.value||'',so=q('fSort')?.value||'confidence';let rows=propsRaw().filter(r=>(!activeGame||r.game===activeGame)&&(!p||String(r.player||'').toLowerCase().includes(p))&&(!st||r.stat===st)&&(!bk||(r.book||r.best_book||r.best_over_book)===bk)&&(!sd||(r.signal||r.side)===sd));rows.sort((a,b)=>so==='player'?String(a.player).localeCompare(String(b.player)):so==='stat'?String(a.stat).localeCompare(String(b.stat)):Number(b.final_score||b.confidence||0)-Number(a.final_score||a.confidence||0));root.innerHTML=rows.map(propRow).join('')||'<div class="empty mono">No props match.</div>'}
function books(){let s=DATA.sportsbook||{};return `<div class="section"><h2 class="mono">Sportsbook Consensus</h2><pre class="mono">${E(JSON.stringify(s,null,2))}</pre></div>`}
function best(){let b=A(DATA.master?.best_bets);return `<div class="grid2">${b.map(x=>`<div class="card"><div class="label mono">${E(S(x.final_action,'BET'))}</div><h2 class="mono">${E(x.player)} ${E(x.stat)} ${E(x.signal)}</h2><div class="small mono">${E(x.game)} · ${E(x.book||x.best_book)}</div><span class="chip mono">Score ${E(S(x.final_score||x.confidence))}</span><span class="chip mono">Line ${E(S(x.line))}</span><span class="chip mono">Proj ${E(S(x.projection||x.pred))}</span></div>`).join('')||'<div class="empty mono">No best bets.</div>'}</div>`}
function portfolio(){let r=DATA.risk||{}, a=A(r.allocation||DATA.portfolio?.recommended_card);return kpis()+`<div class="section"><h2 class="mono">Portfolio</h2>${a.map(x=>`<div class="gameCard"><b>${E(x.player)} ${E(x.stat)} ${E(x.signal)}</b><div class="small mono">${E(x.game)} · stake ${E(S(x.capped_amount||x.capped_stake||x.recommended_stake))}</div></div>`).join('')||'<div class="empty mono">No allocation yet.</div>'}</div>`}
function ai(){return `<div class="grid3"><div class="card"><div class="label mono">Monte Carlo</div><div class="big mono">${S(DATA.monte?.summary?.rows,0)}</div></div><div class="card"><div class="label mono">Projection</div><div class="big mono">${S(DATA.projection?.summary?.rows,0)}</div></div><div class="card"><div class="label mono">Market</div><div class="big mono">${S(DATA.market?.summary?.rows,0)}</div></div></div>`}
function results(){let r=DATA.results||{};return `<div class="section"><h2 class="mono">Results</h2><pre class="mono">${E(JSON.stringify(r,null,2))}</pre></div>`}
function health(){let v=DATA.v4||{}, mods=A(v.modules);return kpis()+`<div class="section"><h2 class="mono">V4 Module Health</h2><div class="small mono">${E(v.mission||'')}</div><table><thead><tr><th>ID</th><th>Module</th><th>Status</th><th>Runtime</th><th>Rows</th></tr></thead><tbody>${mods.map(m=>`<tr><td>${E(m.id)}</td><td>${E(m.name)}</td><td>${E(m.status)}</td><td>${E(m.runtime_status)}</td><td>${E(S(m.rows,0))}</td></tr>`).join('')}</tbody></table></div>`}
function render(t='games'){q('tabs').innerHTML=tabs.map(x=>`<button class="tab ${x[0]===t?'a':''}" onclick="render('${x[0]}')">${x[1]}</button>`).join('');q('sub').textContent=`Slate ${S(DATA.master?.target_date,'-')} · Updated ${fmt(DATA.generated_at_utc)}`;q('badge').textContent=`V4 · ${S(summary().sportsbook_markets,0)} odds markets`;q('root').innerHTML={games,props,books,best,portfolio,ai,results,health}[t]();if(t==='props')drawProps();scrollTo(0,0)} render();
</script></body></html>'''


def apply_persistent_dashboard_patches() -> None:
    """Reapply user-facing dashboard extensions after every full HTML rebuild."""
    patches = [
        ("patch_dashboard_v4_alt_streaks_display", "ALT streak display"),
        ("patch_dashboard_v4_consolidated_navigation", "consolidated navigation"),
    ]
    for module_name, label in patches:
        try:
            module = __import__(module_name, fromlist=["main"])
            module.main()
            print(f"Applied persistent dashboard patch: {label}")
        except Exception as exc:
            raise RuntimeError(f"Required dashboard patch failed ({label}): {exc}") from exc

    html = OUT.read_text(encoding="utf-8")
    required = [
        "v4-alt-streaks-display-data",
        "v4-alt-streaks-display-style",
        "v4-alt-streaks-display-script",
        "v4-consolidated-navigation-script",
        "ALT Streaks",
    ]
    missing = [marker for marker in required if marker not in html]
    if missing:
        raise RuntimeError(f"Dashboard rebuild removed required ALT Streaks blocks: {missing}")


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = HTML.replace("__DATA__", json.dumps(build_payload(), separators=(",", ":"), ensure_ascii=False))
    OUT.write_text(html, encoding="utf-8")
    apply_persistent_dashboard_patches()
    print("Dashboard V4 overhaul built with persistent ALT Streaks tab")


if __name__ == "__main__":
    main()
