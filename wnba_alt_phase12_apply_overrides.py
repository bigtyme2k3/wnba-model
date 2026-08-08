"""Apply Phase 12 safe local resolutions to the canonical identity audit."""
import json
from pathlib import Path
AUDIT=Path('data/dashboard/wnba_alt_game_identity_audit.json')
OVR=Path('data/warehouse/wnba_alt_phase12_resolutions.json')
def norm(v): return ' '.join(str(v or '').strip().lower().replace('’',"'").split())
def main():
    audit=json.loads(AUDIT.read_text(encoding='utf-8'))
    payload=json.loads(OVR.read_text(encoding='utf-8')) if OVR.exists() else {'resolutions':{}}
    rows=audit.get('records',[]); applied=0
    for k,o in (payload.get('resolutions') or {}).items():
        i=int(k)
        if not (0<=i<len(rows)): raise SystemExit(f'Phase12 override index out of range: {i}')
        r=rows[i]
        if norm(r.get('player'))!=norm(o.get('player')): raise SystemExit(f'Phase12 player mismatch at {i}')
        r['phase12_original_classification']=r.get('classification')
        r['classification']='EXACT_MATCH'
        r['warehouse_game_id']=str(o['canonical_game_id'])
        r['warehouse_date']=o['canonical_game_date']
        r['warehouse_game']=o['canonical_game']
        r['note']=f"Phase12 safe local resolution: {o.get('resolution_method')}"
        r['phase12_resolution_method']=o.get('resolution_method')
        r['phase12_source']=o.get('source')
        applied+=1
    audit['phase12_overrides_applied']=applied
    AUDIT.write_text(json.dumps(audit,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print({'phase12_overrides_applied':applied,'audit_rows':len(rows)})
if __name__=='__main__': main()
