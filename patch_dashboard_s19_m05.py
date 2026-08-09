from __future__ import annotations

import json, re
from pathlib import Path

HTML = Path('docs/index.html')
DATA = Path('data/dashboard/wnba_s19_m05_dashboard_health.json')
START = '<!-- SPRINT19_M05_HEALTH_START -->'
END = '<!-- SPRINT19_M05_HEALTH_END -->'


def main():
    if not HTML.exists() or not DATA.exists():
        raise SystemExit('Sprint 19 M05 inputs missing')
    data = json.loads(DATA.read_text(encoding='utf-8'))
    if data.get('status') != 'READY':
        raise SystemExit('Sprint 19 M05 dashboard health not READY')
    raw = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
    block = f'''\n{START}\n<script id="s19-m05-health-script">\n(function(){{\n const D={raw};\n window.WNBA_S19_M05=D;\n window.WNBA_DASHBOARD_HEALTH=D;\n window.WNBA_DASHBOARD_HEALTH_STATUS=D.status;\n}})();\n</script>\n{END}\n'''
    html = HTML.read_text(encoding='utf-8')
    html = re.sub(re.escape(START) + r'.*?' + re.escape(END), '', html, flags=re.S)
    if '</body>' not in html:
        raise SystemExit('Dashboard shell missing closing body')
    HTML.write_text(html.replace('</body>', block + '\n</body>', 1), encoding='utf-8')
    print({'status':'PASS','sprint':19,'module':'M05','target_date':data.get('target_date'),'health':data.get('status'),'age_minutes':data.get('contract_age_minutes')})


if __name__ == '__main__':
    main()
