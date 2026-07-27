"""QA for Sprint 20.5 Phase B probability provenance audit."""
import json,tempfile
from pathlib import Path
import audit_phase_b_data_flow as audit

def main():
    assert audit.selected({'simulation_probability':.61,'confidence':.95})==('simulation_probability',.61)
    assert audit.selected({'confidence':92})==('confidence',.92)
    assert audit.selected({'final_score':87})==('final_score',.87)
    assert audit.prob(61)==.61
    assert audit.prob(.61)==.61
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);model=root/'model.jsonl';edge=root/'edge.jsonl';out=root/'out.json';trace=root/'trace.json'
        model.write_text(json.dumps({'date':'2099-01-01','history_key':'a','player':'A','stat':'PTS','confidence':95})+'\n'+json.dumps({'date':'2099-01-01','history_key':'b','player':'B','stat':'REB','simulation_probability':.58,'confidence':.91})+'\n')
        edge.write_text(json.dumps({'date':'2099-01-01','edge_key':'a','model_probability':.95})+'\n'+json.dumps({'date':'2099-01-01','edge_key':'b','model_probability':.58})+'\n')
        old=(audit.MODEL,audit.EDGE,audit.OUT,audit.TRACE);audit.MODEL,audit.EDGE,audit.OUT,audit.TRACE=model,edge,out,trace
        try:r=audit.build('2099-01-01')
        finally:audit.MODEL,audit.EDGE,audit.OUT,audit.TRACE=old
        s=r['summary'];assert s['source_records']==2;assert s['selected_field_counts']['confidence']==1;assert s['findings']['score_field_selected_as_probability']==1;assert out.exists() and trace.exists()
    print('Sprint 20.5 Phase B QA passed')
if __name__=='__main__':main()
