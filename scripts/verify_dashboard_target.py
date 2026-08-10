from __future__ import annotations
import argparse,re
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--date',required=True); ap.add_argument('--html',default='docs/index.html'); a=ap.parse_args()
    h=Path(a.html).read_text(encoding='utf-8'); target=a.date
    marker=f'<!-- canonical-build-target-v1:{target} -->'
    if marker not in h: raise SystemExit(f'canonical build marker missing for {target}')
    dates=set(re.findall(r'Slate\s+(\d{4}-\d{2}-\d{2})',h)); stale=sorted(dates-{target})
    if stale: raise SystemExit(f'stale slate dates remain: {stale}; target={target}')
    if target not in dates: raise SystemExit(f'Slate {target} missing from rendered HTML')
    print({'status':'PASS','target':target,'slate_dates':sorted(dates),'stale':stale})
if __name__=='__main__': main()
