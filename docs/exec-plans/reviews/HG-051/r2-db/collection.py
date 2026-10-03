from pathlib import Path
from collections import Counter
import json
root=Path('/private/tmp')
collection=json.loads((root/'hg051-r2-db-harness-collection-json.json').read_text())
execution=json.loads((root/'hg051-r2-db-harness-execution-json.json').read_text())
manifest=json.loads((root/'hg051-r2-db-harness-manifest-json.json').read_text())
expected=collection['collections']['serial']
assert len(expected)==len(set(expected))==1492 and collection['exit_code']==0 and not collection['errors']
assert execution['exit_code']==0 and not execution['errors']
assert set(execution['started'])==set(expected) and len(execution['started'])==1492
assert all(items==expected for items in execution['collections'].values())
assert manifest['tested_commit']=='0557dbd8f2196df871af20c0982bdc2526f0ad6e' and manifest['dirty_source'] is False
assert manifest['execution_complete'] and manifest['pytest_exit_code']==manifest['exit_code']==0 and not manifest['errors']
reports=execution['reports']; assert len(reports)==1492*3
counts=Counter((r["phase"],r['outcome']) for r in reports)
assert counts==Counter({('setup','passed'):1492,('call','passed'):1492,('teardown','passed'):1492}),counts
assert all(Counter(r['nodeid'] for r in reports if r["phase"]==phase)==Counter(expected) for phase in ['setup','call','teardown'])
print(json.dumps({'status':'PASS','collected':1492,'unique_started':1492,'workers':{k:len(v) for k,v in execution['collections'].items()},'phase_counts':{str(k):v for k,v in counts.items()},'dirty_source':False,'execution_complete':True,'App_gate':'still required'},indent=2))
