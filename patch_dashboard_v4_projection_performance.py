from __future__ import annotations
import json
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_projection_performance.json')

CSS = r'''<style id="v4-projection-performance-style">
.ppShell{display:grid;gap:18px}.ppHero{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap}.ppHero h2{margin:0}.ppStatus{border:1px solid #21314b;border-radius:999px;padding:8px 12px;font-size:12px;font-weight:900}.ppStatus.good{color:#00e39b;border-color:#00a975}.ppStatus.warn{color:#ffd166;border-color:#9b7621}.ppStatus.bad{color:#ff6b81;border-color:#a83d53}.ppGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.ppCard{border:1px solid #21314b;border-radius:16px;padding:15px;background:#0a1322;min-width:0}.ppLabel{color:#8fa0bd;font-size:12px}.ppValue{font-size:28px;font-weight:950;margin-top:5px}.ppSub{font-size:11px;color:#73839f;margin-top:4px}.ppSection{border:1px solid #21314b;border-radius:18px;padding:16px;background:linear-gradient(180deg,rgba(15,28,48,.92),rgba(7,15,27,.92))}.ppSection h3{margin:0 0 12px}.ppLeaderboard{display:grid;gap:9px}.ppRank{display:grid;grid-template-columns:42px minmax(70px,.7fr) minmax(90px,1fr) repeat(4,minmax(74px,.7fr));gap:10px;align-items:center;border:1px solid #1d2b42;border-radius:13px;padding:11px;background:#08111f}.ppRankHead{color:#8fa0bd;font-size:11px;text-transform:uppercase;letter-spacing:.08em;background:transparent;border:0;padding-top:0;padding-bottom:3px}.ppMedal{font-size:18px;font-weight:950}.ppGrade{font-weight:950}.ppPositive{color:#00e39b}.ppNegative{color:#ff6b81}.ppNeutral{color:#ffd166}.ppBarRow{display:grid;grid-template-columns:62px 1fr 64px;gap:10px;align-items:center;margin:9px 0}.ppBar{height:10px;border-radius:999px;background:#101c2d;overflow:hidden}.ppBar>span{display:block;height:100%;background:linear-gradient(90deg,#00a975,#00e39b);border-radius:999px}.ppInsightGrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px}.ppInsight{border-left:3px solid #00a975;background:#08111f;border-radius:10px;padding:12px;font-size:13px;line-height:1.45}.ppInsight.warn{border-left-color:#ffd166}.ppInsight.bad{border-left-color:#ff6b81}.ppMatrix{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}.ppMatrixCard{border:1px solid #1d2b42;border-radius:13px;padding:12px;background:#08111f}.ppMatrixCard strong{font-size:17px}.ppMatrixCard .meter{height:8px;background:#101c2d;border-radius:999px;margin:9px 0;overflow:hidden}.ppMatrixCard .meter span{display:block;height:100%;border-radius:999px;background:#00e39b}.ppTableWrap{overflow:auto}.ppTable{width:100%;border-collapse:collapse;min-width:760px}.ppTable th,.ppTable td{padding:9px;border-bottom:1px solid #1d2b42;text-align:left;font-size:12px}.ppTable th{color:#8fa0bd}.ppLocked{color:#8fa0bd}.ppReview{color:#ffd166}.ppEligible{color:#00e39b}.ppDetails summary{cursor:pointer;font-weight:900;padding:4px 0}.ppFoot{font-size:11px;color:#73839f;margin-top:10px}.ppEmpty{color:#8fa0bd;padding:16px;text-align:center}
@media(max-width:760px){.ppRank{grid-template-columns:34px 1fr 62px 62px}.ppRankHead{display:none}.ppRank .hideMobile{display:none}.ppValue{font-size:24px}.ppSection{padding:13px}.ppHero{display:block}.ppStatus{display:inline-block;margin-top:10px}}
</style>'''

SCRIPT = r'''<script id="v4-projection-performance-script">(function(){
const pct=v=>v==null?'—':(Number(v)*100).toFixed(1)+'%';
const num=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d);
const signed=(v,d=1,suffix='')=>{if(v==null||!Number.isFinite(Number(v)))return '—';const n=Number(v);return `${n>0?'+':''}${n.toFixed(d)}${suffix}`};
const cls=v=>Number(v)>0?'ppPositive':Number(v)<0?'ppNegative':'ppNeutral';
const grade=r=>{const decisions=Number(r.market_decisions||0),roi=r.roi==null?null:Number(r.roi),hit=r.hit_rate==null?null:Number(r.hit_rate),coverage=Number(r.p10_p90_coverage||0),bias=Math.abs(Number(r.bias||0));if(decisions>=20&&roi>=.10&&hit>=.55)return'A';if(decisions>=15&&roi>=0&&hit>=.50)return'B';if(decisions>=10&&roi>=-.10&&coverage>=.85)return'C';if(decisions>=10)return'D';if(coverage>=.90&&bias<=.35)return'B*';return'C*'};
const gradeClass=g=>g.startsWith('A')?'ppPositive':g.startsWith('B')?'ppPositive':g.startsWith('C')?'ppNeutral':'ppNegative';
const qualityScore=r=>{const decisions=Math.min(1,Number(r.market_decisions||0)/25),roi=r.roi==null?-.1:Number(r.roi),hit=r.hit_rate==null?.45:Number(r.hit_rate),coverage=Number(r.p10_p90_coverage||0),bias=Math.abs(Number(r.bias||0));return decisions*30+Math.max(0,Math.min(30,(roi+.30)*50))+Math.max(0,Math.min(20,(hit-.35)*100))+coverage*15+Math.max(0,5-bias*3)};
window.projectionPerformance=function(){
 const p=DATA.projection_performance||{},s=p.summary||{},rows=Array.isArray(p.by_stat)?p.by_stat:[],conf=Array.isArray(p.by_confidence)?p.by_confidence:[],recs=Array.isArray(p.recommendations)?p.recommendations:[];
 const recMap=Object.fromEntries(recs.map(r=>[r.stat,r]));
 const ranked=rows.filter(r=>Number(r.market_decisions||0)>0).slice().sort((a,b)=>qualityScore(b)-qualityScore(a));
 const overallRoi=Number(s.roi||0),overallHit=Number(s.hit_rate||0),overallBias=Math.abs(Number(s.bias||0));
 const health=overallRoi>=0&&overallHit>=.5?'good':overallRoi>=-.1&&overallBias<.5?'warn':'bad';
 const healthText=health==='good'?'Healthy':health==='warn'?'Review recommended':'Retraining review';
 const overallGrade=overallRoi>=.08&&overallHit>=.55?'A':overallRoi>=0&&overallHit>=.5?'B':overallRoi>=-.10?'C':'D';
 const leaderboard=ranked.slice(0,8).map((r,i)=>{const g=grade(r);return `<div class="ppRank"><div class="ppMedal">${i<3?['🥇','🥈','🥉'][i]:i+1}</div><div><strong>${E(r.group)}</strong><div class="ppSub">${E(r.market_decisions||0)} decisions</div></div><div class="ppGrade ${gradeClass(g)}">${g}</div><div class="${cls(r.roi)}">${pct(r.roi)}</div><div class="hideMobile">${pct(r.hit_rate)}</div><div class="hideMobile">${num(r.mae,2)}</div><div class="hideMobile">${pct(r.p10_p90_coverage)}</div></div>`}).join('');
 const calRows=rows.slice().sort((a,b)=>Number(b.p10_p90_coverage||0)-Number(a.p10_p90_coverage||0)).slice(0,8).map(r=>`<div class="ppBarRow"><strong>${E(r.group)}</strong><div class="ppBar"><span style="width:${Math.max(0,Math.min(100,Number(r.p10_p90_coverage||0)*100))}%"></span></div><div>${pct(r.p10_p90_coverage)}</div></div>`).join('');
 const confRows=conf.filter(r=>Number(r.market_decisions||0)>=5).slice().sort((a,b)=>Number(b.roi||-9)-Number(a.roi||-9)).slice(0,6).map(r=>{const strength=Math.max(5,Math.min(100,(Number(r.roi||0)+.5)*70));return `<div class="ppMatrixCard"><div class="ppLabel">Confidence ${E(r.group)}</div><strong class="${cls(r.roi)}">${pct(r.roi)} ROI</strong><div class="meter"><span style="width:${strength}%"></span></div><div class="ppSub">${E(r.market_decisions||0)} decisions · ${pct(r.hit_rate)} hit</div></div>`}).join('');
 const best=ranked[0],weak=ranked[ranked.length-1],bestCal=rows.slice().sort((a,b)=>Number(b.p10_p90_coverage||0)-Number(a.p10_p90_coverage||0))[0],biasIssue=rows.slice().sort((a,b)=>Math.abs(Number(b.bias||0))-Math.abs(Number(a.bias||0)))[0];
 const insights=[
  best?`<div class="ppInsight"><strong>Best current market:</strong> ${E(best.group)} ranks first using ROI, hit rate, sample size, coverage and bias.</div>`:'',
  weak?`<div class="ppInsight bad"><strong>Weakest priced market:</strong> ${E(weak.group)} has ${pct(weak.roi)} ROI across ${E(weak.market_decisions||0)} decisions.</div>`:'',
  bestCal?`<div class="ppInsight"><strong>Best interval coverage:</strong> ${E(bestCal.group)} is covering ${pct(bestCal.p10_p90_coverage)} of verified outcomes.</div>`:'',
  biasIssue?`<div class="ppInsight warn"><strong>Largest projection bias:</strong> ${E(biasIssue.group)} is ${signed(biasIssue.bias,2)} versus actual results.</div>`:'',
  `<div class="ppInsight ${overallRoi<0?'bad':''}"><strong>Bankroll signal:</strong> Overall ROI is ${pct(s.roi)} on ${E(s.market_decisions||0)} graded market decisions.</div>`,
  `<div class="ppInsight ${overallHit<.5?'warn':''}"><strong>Decision accuracy:</strong> The current hit rate is ${pct(s.hit_rate)} with ${E(s.wins||0)} wins, ${E(s.losses||0)} losses and ${E(s.pushes||0)} pushes.</div>`
 ].join('');
 const technical=rows.map(r=>{const rec=recMap[r.group]||{};const status=rec.status||((r.graded||0)>=100?'CALIBRATION_ELIGIBLE':'LOCKED');const st=status==='CALIBRATION_ELIGIBLE'?'ppEligible':status==='WEIGHT_REVIEW'?'ppReview':'ppLocked';return `<tr><td>${E(r.group)}</td><td>${E(r.graded)}</td><td>${num(r.mae,4)}</td><td>${signed(r.bias,4)}</td><td>${pct(r.p10_p90_coverage)}</td><td>${pct(r.hit_rate)}</td><td>${pct(r.roi)}</td><td class="${st}">${E(status.replaceAll('_',' '))}</td></tr>`}).join('');
 return `<div class="section ppShell"><div class="ppHero"><div><h2 class="mono">Model Performance</h2><div class="small mono">Historical accuracy, calibration, market results and model-learning signals.</div></div><div class="ppStatus ${health}">${healthText}</div></div><div class="ppGrid"><div class="ppCard"><div class="ppLabel">Overall Grade</div><div class="ppValue ${gradeClass(overallGrade)}">${overallGrade}</div><div class="ppSub">Evidence-weighted status</div></div><div class="ppCard"><div class="ppLabel">Predictions Graded</div><div class="ppValue mono">${E(s.graded||0)}</div><div class="ppSub">Frozen pregame projections</div></div><div class="ppCard"><div class="ppLabel">Market ROI</div><div class="ppValue mono ${cls(s.roi)}">${pct(s.roi)}</div><div class="ppSub">${E(s.market_decisions||0)} decisions</div></div><div class="ppCard"><div class="ppLabel">Hit Rate</div><div class="ppValue mono ${overallHit>=.5?'ppPositive':'ppNegative'}">${pct(s.hit_rate)}</div><div class="ppSub">Pushes excluded</div></div><div class="ppCard"><div class="ppLabel">MAE</div><div class="ppValue mono">${num(s.mae,3)}</div><div class="ppSub">Average absolute error</div></div><div class="ppCard"><div class="ppLabel">Bias</div><div class="ppValue mono ${overallBias<=.25?'ppPositive':overallBias<=.75?'ppNeutral':'ppNegative'}">${signed(s.bias,3)}</div><div class="ppSub">Near zero is best</div></div></div><div class="ppSection"><h3 class="mono">Accuracy Leaderboard</h3><div class="ppRank ppRankHead"><div>Rank</div><div>Market</div><div>Grade</div><div>ROI</div><div class="hideMobile">Hit</div><div class="hideMobile">MAE</div><div class="hideMobile">Coverage</div></div><div class="ppLeaderboard">${leaderboard||'<div class="ppEmpty">No graded market decisions yet.</div>'}</div></div><div class="ppSection"><h3 class="mono">Calibration Coverage</h3><div class="small">How often verified outcomes landed inside each model's P10–P90 range.</div>${calRows||'<div class="ppEmpty">No calibration rows available.</div>'}</div><div class="ppSection"><h3 class="mono">Automated Learning Notes</h3><div class="ppInsightGrid">${insights}</div></div><div class="ppSection"><h3 class="mono">Confidence-Bucket Results</h3><div class="small">Only buckets with at least five market decisions are shown.</div><div class="ppMatrix">${confRows||'<div class="ppEmpty">No qualified confidence buckets yet.</div>'}</div></div><div class="ppSection ppDetails"><details><summary>Technical Metrics</summary><div class="ppTableWrap"><table class="ppTable"><thead><tr><th>Stat</th><th>N</th><th>MAE</th><th>Bias</th><th>Coverage</th><th>Hit</th><th>ROI</th><th>Calibration</th></tr></thead><tbody>${technical||'<tr><td colspan="8">No graded projections yet.</td></tr>'}</tbody></table></div><div class="ppFoot mono">Grades summarize observed results; they do not guarantee future profitability. Bias diagnosis unlocks at 50 samples, stat-weight review at 100, and simulation-variance review at 200.</div></details></div></div>`;
};
const previous=window.altPerformance;window.altPerformance=function(){const base=typeof previous==='function'?previous():'';return base+window.projectionPerformance()};
})();</script>'''

def replace_block(html: str, start: str, end: str, replacement: str) -> str:
    i = html.find(start)
    if i < 0:
        return html
    j = html.find(end, i)
    if j < 0:
        return html
    return html[:i] + replacement.strip() + html[j + len(end):]

def main() -> None:
    if not HTML.exists():
        raise SystemExit('docs/index.html missing')
    try:
        payload = json.load(DATA.open(encoding='utf-8')) if DATA.exists() else {}
    except Exception:
        payload = {}
    html = HTML.read_text(encoding='utf-8')
    data = f'<script id="v4-projection-performance-data">DATA.projection_performance={json.dumps(payload,separators=(",",":"),ensure_ascii=False)};</script>'
    html = replace_block(html, '<script id="v4-projection-performance-data">', '</script>', data) if 'id="v4-projection-performance-data"' in html else html.replace('</body>', data + '</body>')
    html = replace_block(html, '<style id="v4-projection-performance-style">', '</style>', CSS) if 'id="v4-projection-performance-style"' in html else html.replace('</head>', CSS + '</head>')
    html = replace_block(html, '<script id="v4-projection-performance-script">', '</script>', SCRIPT) if 'id="v4-projection-performance-script"' in html else html.replace('</body>', SCRIPT + '</body>')
    HTML.write_text(html, encoding='utf-8')
    print('Projection Performance redesigned as model intelligence center')

if __name__ == '__main__':
    main()
