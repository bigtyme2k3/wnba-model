"""Add a small deployment/build verification beacon to the Games tab.

The beacon is intentionally distinctive so a single screenshot can prove which
commit and deployment artifact is live. The patch is idempotent and is applied
as the final dashboard build step.
"""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HTML = Path("docs/index.html")
START = "<!-- WNBA_BUILD_BEACON_START -->"
END = "<!-- WNBA_BUILD_BEACON_END -->"


def git_value(*args: str, fallback: str = "unknown") -> str:
    try:
        return subprocess.check_output(["git", *args], text=True).strip() or fallback
    except Exception:
        return fallback


def build_block() -> str:
    commit = os.getenv("GITHUB_SHA") or git_value("rev-parse", "HEAD")
    short = commit[:8]
    built = datetime.now(timezone.utc).strftime("%b %d, %Y · %I:%M %p UTC")
    run_number = os.getenv("GITHUB_RUN_NUMBER", "local")
    release = f"QA-{short}"
    return f'''{START}
<style id="wnba-build-beacon-style">
#wnba-build-beacon{{position:fixed;right:18px;top:196px;z-index:9998;width:min(310px,calc(100vw - 36px));padding:12px 14px;border:1px solid rgba(52,211,153,.65);border-radius:16px;background:linear-gradient(135deg,rgba(6,20,31,.97),rgba(8,35,49,.97));box-shadow:0 14px 38px rgba(0,0,0,.38);color:#e5e7eb;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;display:none}}
#wnba-build-beacon .bb-top{{display:flex;align-items:center;justify-content:space-between;gap:10px}}
#wnba-build-beacon .bb-title{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#a7f3d0;font-weight:900}}
#wnba-build-beacon .bb-chip{{padding:4px 8px;border-radius:999px;background:#064e3b;color:#6ee7b7;font-size:11px;font-weight:900}}
#wnba-build-beacon .bb-id{{font-size:20px;color:#34d399;font-weight:950;margin-top:7px}}
#wnba-build-beacon .bb-meta{{margin-top:5px;color:#94a3b8;font-size:11px;line-height:1.5}}
#wnba-build-beacon .bb-new{{margin-top:8px;padding-top:8px;border-top:1px solid #24334b;color:#facc15;font-size:11px}}
@media(max-width:700px){{#wnba-build-beacon{{top:auto;right:12px;bottom:82px;width:245px;padding:10px 12px}}#wnba-build-beacon .bb-id{{font-size:16px}}}}
</style>
<aside id="wnba-build-beacon" data-build="{short}" aria-label="Dashboard build verification">
  <div class="bb-top"><span class="bb-title">Games QA Beacon</span><span class="bb-chip">LIVE BUILD</span></div>
  <div class="bb-id">✓ {release}</div>
  <div class="bb-meta">Commit {short} · Run {run_number}<br>Built {built}</div>
  <div class="bb-new">New: screenshot-verifiable deployment marker</div>
</aside>
<script id="wnba-build-beacon-script">
(function(){{
  const beacon=document.getElementById('wnba-build-beacon');
  if(!beacon)return;
  const norm=s=>(s||'').trim().toLowerCase();
  function gamesIsActive(){{
    const candidates=[...document.querySelectorAll('button,[role="tab"],a')].filter(el=>norm(el.textContent)==='games');
    if(!candidates.length)return false;
    return candidates.some(el=>{{
      const cls=String(el.className||'').toLowerCase();
      return el.getAttribute('aria-selected')==='true'||el.getAttribute('aria-current')==='page'||cls.includes('active')||cls.includes('selected');
    }});
  }}
  function sync(){{beacon.style.display=gamesIsActive()?'block':'none';}}
  document.addEventListener('click',()=>setTimeout(sync,40),true);
  new MutationObserver(sync).observe(document.body,{{subtree:true,attributes:true,attributeFilter:['class','aria-selected','aria-current']}});
  sync(); setTimeout(sync,600);
}})();
</script>
{END}'''


def main() -> None:
    if not HTML.exists():
        raise SystemExit("docs/index.html is missing")
    html = HTML.read_text(encoding="utf-8")
    block = build_block()
    pattern = re.escape(START) + r".*?" + re.escape(END)
    if re.search(pattern, html, flags=re.S):
        html = re.sub(pattern, block, html, flags=re.S)
    elif "</body>" in html:
        html = html.replace("</body>", block + "\n</body>", 1)
    else:
        html += "\n" + block
    HTML.write_text(html, encoding="utf-8")
    print("Games QA build beacon embedded")


if __name__ == "__main__":
    main()
