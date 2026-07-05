"""
build_dashboard.py
------------------
Reads the latest predictions JSON and bakes it into docs/index.html.
Also injects model tracking data and overrides dashboard helpers.
"""

import glob, json, os, re
from datetime import date
import pandas as pd

PREDICTIONS_DIR = "predictions"
RAW_DIR = "data/raw"
TRACKING_JSON = "data/tracking/model_tracking.json"
OUTPUT_HTML = "docs/index.html"


def empty_tracking():
    return {"overall":"0-0-0","wins":0,"losses":0,"pushes":0,"win_pct":0,"roi":0,"profit_units":0,"clv_avg":0,"by_type":{},"by_conf":{},"recent_10":[]}


def empty_dashboard_data():
    today = str(date.today())
    return {"date":today,"generated":None,"games":[],"best_bets":[],"props":[],"player_points":[],"props_board":[],"tracking":empty_tracking(),"model_tracking":empty_tracking(),"data_health":{"odds":"missing","props":"missing","player_points":"missing","spreads_found":0,"totals_found":0,"props_found":0,"player_points_found":0,"games":0,"actionable_bets":0,"high_bets":0,"last_updated_utc":None},"model_stats":{"spread":{"algo":"Ridge v2","cv_mae":9.72,"dir_acc":0.716,"strong_ats":0.815,"n":0},"totals":{"algo":"Random Forest","cv_mae":6.77,"ou_acc":0.542,"strong_ou":0.554,"n":0},"props":{"algo":"Ridge","cv_mae":6.00,"hit_rate":0.721,"strong_hr":0.754,"n":0}}}


def find_predictions():
    today = str(date.today())
    candidates = [os.path.join(PREDICTIONS_DIR, f"predictions_{today}.json")] + sorted(glob.glob(os.path.join(PREDICTIONS_DIR, "predictions_*.json")), reverse=True)
    seen = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"  Loaded: {path} ({len(data.get('games', []))} games)")
            return data
    print("  [WARN] No predictions file found — using empty data")
    return empty_dashboard_data()


def csv_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def load_player_points_for_date(target_date):
    for path in [os.path.join(RAW_DIR, f"player_points_{target_date}.csv"), os.path.join(RAW_DIR, "player_points_today.csv")]:
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                print(f"  Loaded player points: {path} ({len(df)} rows)")
                return [{k: csv_value(v) for k, v in row.to_dict().items()} for _, row in df.iterrows()]
            except Exception as exc:
                print(f"  [WARN] Could not load player points from {path}: {exc}")
    return []


def load_tracking():
    if os.path.exists(TRACKING_JSON):
        try:
            with open(TRACKING_JSON) as f:
                return json.load(f)
        except Exception as exc:
            print(f"  [WARN] Could not read model tracking: {exc}")
    return empty_tracking()


def enrich_data(data):
    target_date = data.get("date") or str(date.today())
    points = data.get("props") or data.get("player_points") or load_player_points_for_date(target_date)
    if points:
        data["props"] = points
        data["player_points"] = points
        data["props_board"] = data.get("props_board") or points
        h = data.setdefault("data_health", {})
        h["player_points"] = "loaded"
        h["player_points_found"] = len(points)
        h["props_found"] = max(int(h.get("props_found", 0) or 0), len(points))
    else:
        data.setdefault("props", [])
        data.setdefault("player_points", [])
        data.setdefault("props_board", [])
    tracking = data.get("tracking") or data.get("model_tracking") or load_tracking()
    data["tracking"] = tracking
    data["model_tracking"] = tracking
    return data


def dashboard_override_script():
    return r'''
<script id="model-tracking-override">
(function(){
  const tabs=document.querySelectorAll('.tab');
  tabs.forEach(t=>{ if(t.textContent.trim()==='Stats') t.textContent='Model Tracking'; });

  window.rowGameKey=function(p){
    const norm=v=>String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'');
    const raw=[p.game,p.opp,p.team,p.home_team,p.away_team].map(x=>String(x||'')).join(' ').toUpperCase();
    const compact=norm(raw);
    for(const g of (DATA.games||[])){
      const key=g.away.name+' @ '+g.home.name;
      const awayName=norm(g.away.name), homeName=norm(g.home.name), awayAbbr=norm(g.away.abbr), homeAbbr=norm(g.home.abbr);
      const hasAway=compact.includes(awayName)||compact.includes(awayAbbr);
      const hasHome=compact.includes(homeName)||compact.includes(homeAbbr);
      if(hasAway && hasHome) return key;
    }
    return p.game||p.opp||'UNKNOWN';
  };

  window.renderProps=function(){
    const safe=(v,d='—')=>v===null||v===undefined||v===''||String(v)==='nan'?d:v;
    const pct=x=>typeof x==='number'?Math.round(x*100)+'%':'—';
    const arr=v=>{if(Array.isArray(v))return v;if(!v)return[];try{let p=JSON.parse(v);return Array.isArray(p)?p:[]}catch(e){return[]}};
    const rankClass=r=>{r=Number(r||8);return r<=5?'rank-tough':r<=10?'rank-mid':'rank-easy'};
    const statClass=p=>p.conf==='HIGH'?'stat-pill high':'stat-pill';
    const hitLabel=(v,sig)=>sig?`${pct(v)} ${sig}`:'—';
    const l5Boxes=p=>{let vals=arr(p.last5_vals).slice(0,5),opps=arr(p.last5_opps).slice(0,5),line=Number(p.line),sig=p.signal;if(!vals.length)return'—';return`<div class="l5-wrap">${vals.map((v,i)=>{let cls='l5-neutral';if(sig){let hit=sig==='UNDER'?v<line:v>line;cls=hit?'l5-hit':'l5-miss'}return`<div class="l5-box"><div class="l5-num ${cls}">${v}</div><div class="l5-opp">${safe(opps[i],'')}</div></div>`}).join('')}</div>`};
    const gameKey=(a,h)=>a+' @ '+h;
    const props=(DATA.props||DATA.player_points||DATA.props_board||[]).filter(p=>p.line!==null&&p.line!==undefined&&p.line!==''&&p.market_status!=='NO MARKET'&&p.injury_status!=='OUT'&&p.injury_status!=='DOUBTFUL');
    const games=DATA.games||[];
    let gameCards=`<article class="props-game all ${propsGame==='ALL'?'active':''}" onclick="setPropsGame('ALL')"><div class="game-time">ALL</div><div class="team-line">All Players</div></article>`+games.map(g=>{let k=gameKey(g.away.name,g.home.name);return`<article class="props-game ${propsGame===k?'active':''}" onclick="setPropsGame('${k.replace(/'/g,"\\'")}')"><div class="game-time">${fmtTime(g.tip)}</div><div class="team-line">${g.away.abbr} @ ${g.home.abbr}</div><div class="board-sub">${g.away.name} @ ${g.home.name}</div></article>`}).join('');
    let stats=['ALL','PTS','REB','AST','3PM','PRA'];
    let filtered=props.map(p=>Object.assign({},p,{_game:window.rowGameKey(p)})).filter(p=>(propsGame==='ALL'||p._game===propsGame)&&(propsStat==='ALL'||String(p.stat).toUpperCase()===propsStat));
    filtered.sort((a,b)=>(b.conf==='HIGH')-(a.conf==='HIGH')||(b.conf==='MED')-(a.conf==='MED')||Math.abs(b.edge||0)-Math.abs(a.edge||0));
    let table=filtered.length?`<div class="props-scroll"><div class="props-table"><div class="props-head"><div>Player</div><div>Stat</div><div>Line</div><div>Over</div><div>Under</div><div>Projected</div><div>Last 5</div><div>L5 Hit</div><div>L10 Hit</div><div>H2H L5</div><div>Opp Rank</div></div>${filtered.map(p=>`<article class="prop-row ${p.conf||'LOW'}"><div><div class="player-name">${safe(p.player)}</div><div class="player-meta">${safe(p.team)} · ${safe(p.pos)} · ${safe(p.injury_status,'ACTIVE')} · ${safe(p.opp)}</div></div><div><span class="${statClass(p)}">${safe(p.stat)}</span></div><div class="board-value">${safe(p.line)}</div><div class="signal-over">${p.signal==='OVER'?'OVER':'—'}</div><div class="signal-under">${p.signal==='UNDER'?'UNDER':'—'}</div><div class="${p.line?'proj-bright':'proj-dim'}">${safe(p.pred)}</div><div>${l5Boxes(p)}</div><div>${hitLabel(p.last5_hit,p.signal)}</div><div>${hitLabel(p.last10_hit,p.signal)}</div><div>${arr(p.h2h_last5).length?arr(p.h2h_last5).join(', '):'—'}</div><div class="${rankClass(p.opp_rank)}">${safe(p.opp_rank)}</div></article>`).join('')}</div></div>`:`<div class="empty">No props for this selected game/stat filter. Try ALL or another stat.</div>`;
    document.getElementById('tab-props').innerHTML=`<div class="section-title">Today's Games</div><div class="props-games">${gameCards}</div><div class="section-title">Filters</div><div class="filter-bar">${stats.map(s=>`<button class="filter-btn ${propsStat===s?'active':''}" onclick="setPropsStat('${s}')">${s}</button>`).join('')}</div><div class="section-title">Props Table</div>${table}`;
  };

  window.renderStats=function(){
    const t=DATA.tracking||DATA.model_tracking||{};
    const byType=t.by_type||{}, byConf=t.by_conf||{};
    const fmtPct=v=>typeof v==='number'?Math.round(v*1000)/10+'%':'—';
    const safe=(v,d='—')=>v===null||v===undefined||v===''?d:v;
    const statCard=(title,rows)=>`<article class="stat-card"><div class="stat-title">${title}</div>${rows.map(r=>`<div class="stat-line"><span>${r[0]}</span><span>${safe(r[1])}</span></div>`).join('')}</article>`;
    const typeRows=Object.keys(byType).length?Object.entries(byType).map(([k,v])=>`<article class="board-row"><div><div class="board-main">${k}</div><div class="board-sub">${v.bets||0} tracked bets</div></div><div><div class="board-label">Record</div><div class="board-value">${safe(v.record)}</div></div><div><div class="board-label">Win %</div><div class="board-value">${fmtPct(v.win_pct)}</div></div><div></div><div></div></article>`).join(''):'<div class="empty">No graded bets yet. Tracking starts once games finish.</div>';
    const confRows=Object.keys(byConf).length?Object.entries(byConf).map(([k,v])=>`<article class="board-row"><div><div class="board-main">${k}</div><div class="board-sub">Confidence bucket</div></div><div><div class="board-label">Record</div><div class="board-value">${safe(v.record)}</div></div><div><div class="board-label">Win %</div><div class="board-value">${fmtPct(v.win_pct)}</div></div><div></div><div></div></article>`).join(''):'<div class="note">Confidence tracking appears after bets are graded.</div>';
    const recent=(t.recent_10||[]).slice(-10).map(b=>`<article class="board-row"><div><div class="board-main">${safe(b.play)}</div><div class="board-sub">${safe(b.date)} · ${safe(b.game)}</div></div><div><div class="board-label">Type</div><div class="board-value">${safe(b.type)}</div></div><div><div class="board-label">Result</div><div class="board-value ${b.result==='WIN'?'good':b.result==='LOSS'?'bad':'warn'}">${safe(b.result)}</div></div><div><div class="board-label">Units</div><div class="board-value">${safe(b.profit_units)}</div></div><div></div></article>`).join('')||'<div class="empty">No recent graded bets yet.</div>';
    document.getElementById('tab-stats').innerHTML=`<div class="section-title">Model Tracking</div><section class="stats-grid">${statCard('Overall',[['Record',t.overall||'0-0-0'],['Win %',fmtPct(t.win_pct)],['ROI',fmtPct(t.roi)],['Units',safe(t.profit_units,0)],['Avg CLV',safe(t.clv_avg,0)]])}${statCard('Automation',[['Odds',safe((DATA.data_health||{}).odds)],['Props',safe((DATA.data_health||{}).props)],['Games',safe((DATA.data_health||{}).games,0)],['Best Bets',(DATA.best_bets||[]).length]])}${statCard('EV Engine',[['A/B Bets',(DATA.best_bets||[]).filter(b=>['A','B'].includes(b.grade)).length],['Top EV',(DATA.best_bets||[])[0]?.ev_pct?((DATA.best_bets||[])[0].ev_pct+'%'):'—'],['Top Grade',(DATA.best_bets||[])[0]?.grade||'—'],['Kelly Units',(DATA.best_bets||[])[0]?.units||'—']])}${statCard('Model Counts',[['Spreads',(DATA.data_health||{}).spreads_found||0],['Totals',(DATA.data_health||{}).totals_found||0],['Props',(DATA.data_health||{}).props_found||0],['High Bets',(DATA.data_health||{}).high_bets||0]])}</section><div class="section-title">Performance by Market</div><div class="board">${typeRows}</div><div class="section-title">Confidence Breakdown</div><div class="board">${confRows}</div><div class="section-title">Recent Graded Bets</div><div class="board">${recent}</div>`;
  };
})();
</script>
'''


def build_html(data):
    data = enrich_data(data)
    data_json = json.dumps(data, separators=(",", ":"))
    with open(OUTPUT_HTML) as f:
        html = f.read()
    html = html.replace('>Stats</button>', '>Model Tracking</button>')
    html = re.sub(r"<script id=\"model-tracking-override\">.*?</script>", "", html, flags=re.DOTALL)
    pattern = r"const\s+DATA\s*=\s*.*?;\s*(?=\n\s*const|\n\s*let|\n\s*function|\n\s*window\.)"
    replacement = f"const DATA = {data_json};\n"
    new_html = re.sub(pattern, lambda _: replacement, html, flags=re.DOTALL)
    if new_html == html:
        print("  [WARN] Could not find DATA constant to replace — check docs/index.html")
        return False
    new_html = new_html.replace("</body>", dashboard_override_script() + "\n</body>")
    with open(OUTPUT_HTML, "w") as f:
        f.write(new_html)
    return True


def main():
    print("\n═══ Building Dashboard ═══\n")
    os.makedirs("docs", exist_ok=True)
    data = find_predictions()
    success = build_html(data)
    if success:
        h = data.get("data_health", {})
        print(f"  ✅ {OUTPUT_HTML} updated")
        print(f"     Date: {data.get('date')}")
        print(f"     Games: {len(data.get('games', []))}")
        print(f"     Best bets: {len(data.get('best_bets', []))}")
        print(f"     Props: {len(data.get('props', []))}")
        print(f"     Odds: {h.get('odds', 'unknown')}")
    else:
        raise SystemExit("  ❌ Build failed")


if __name__ == "__main__":
    main()
