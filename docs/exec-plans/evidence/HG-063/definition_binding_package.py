"""Own pinned research data packaging only; never body pointer resolution/runtime trust."""
from pathlib import Path
import hashlib,json
from definition_data import strict_json
def load_binding_package(root):
 m=strict_json((root/'BINDING_PACKAGE.json').read_bytes(),262144)
 rows=[]
 for item in m['ordered_rows']:
  name=item['path']
  if name!='binding-'+str(item['row']).zfill(2)+'.json':raise ValueError('noncanonical-package-path')
  raw=(root/name).read_bytes()
  if len(raw)!=item['bytes'] or len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('package-byte-binding')
  row=strict_json(raw,262144)
  if row['row']!=item['row']:raise ValueError('package-row-binding')
  rows.append(row)
 value=dict(m['top_level'],rows=rows)
 raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
 if hashlib.sha256(raw).hexdigest()!=m['decoded_canonical_sha256']:raise ValueError('decoded-identity')
 return value
