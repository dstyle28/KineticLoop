'Harmless synthetic test child. NOT compact audit/installed/root controller.'
import argparse,json,time
p=argparse.ArgumentParser();p.add_argument('--fixture',required=True);p.add_argument('--variant',required=True);a=p.parse_args()
from pathlib import Path
x=json.loads(Path(a.fixture).read_bytes())
if a.variant=='timeout':time.sleep(1)
if a.variant=='unexpected':x['errors'].append('native-unexpected-codec-denial')
if a.variant=='incomplete':x.pop('files')
print(json.dumps(x))
raise SystemExit(7 if a.variant=='unexpected' else 1)
