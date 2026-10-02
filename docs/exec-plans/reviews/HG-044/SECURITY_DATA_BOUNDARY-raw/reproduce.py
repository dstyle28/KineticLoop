from pathlib import Path
import importlib.util, tempfile, json, copy, hashlib, subprocess
ROOT=Path(__file__).resolve().parents[5]
spec=importlib.util.spec_from_file_location('review_m3', ROOT/'tests/harness/test_m3_milestone_closure.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
v=m.v
with tempfile.TemporaryDirectory(prefix='hg044-security-', dir='/private/tmp') as tmp:
    h=m.History(Path(tmp)/'repo')
    out={'reviewed_head_sha': '351f0eda41ad492e66115f9ea1e41e3e0f9abf3d', 'baseline_errors':v.m3_execution_evidence_errors(h.root,h.payload,h.evaluated,h.evaluated,h.records)}
    multis=[]
    for run in h.payload['executions']:
        if run['command'].startswith('uv run pytest -q ') and len(run['command'].removeprefix('uv run pytest -q ').split())>1:
            collection=v.load_artifact_text(v.m3_evidence_bytes(h.root,dict(run['collection'],revision=h.evaluated),h.evaluated).decode(),'.json')
            multis.append({'command':run['command'],'nodeids':collection['nodeids'],'omitted_selectors':[s for s in run['command'].removeprefix('uv run pytest -q ').split() if not any(n==s or n.startswith(s+'::') or n.startswith(s+'[') or n.startswith(s+'/') for n in collection['nodeids'])]})
    out['accepted_omitted_selectors']=multis
    negative=copy.deepcopy(h.payload); negative['executions'][0]['exit_code']=False
    out['boolean_exit_rejected']=v.m3_execution_evidence_errors(h.root,negative,h.evaluated,h.evaluated,h.records)
    negative=copy.deepcopy(h.payload); negative['executions'][0]['exit_code']=0.0
    out['float_zero_result']=v.m3_execution_evidence_errors(h.root,negative,h.evaluated,h.evaluated,h.records)
    print(json.dumps(out,indent=2))
