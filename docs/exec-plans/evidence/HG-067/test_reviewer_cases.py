"""Read-only retained R3 counterexample inputs, translated to R4 format only."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from definition_oracle import seal_record,validate_record

ROOT=Path(__file__).resolve().parent
bindings=json.loads((ROOT/'FIXTURE_BINDINGS.json').read_text())
def retained(label):
 rows=[row for row in bindings if row['label']==label]
 values=[]
 for row in rows:
  raw=(ROOT/row['file']).read_bytes()
  assert hashlib.sha256(raw).hexdigest()==row['sha256']
  values.append(json.loads(raw))
 return values
security=retained('security')
general=retained('general')
assert len(security)==48 and len(general)==8
CASES=[('SECURITY-'+p['id'],p) for p in security]+[
 ('GENERAL-'+str(i)+'-'+p['acquisition']+'-'+p['stage']+'-'+p['status'],p) for i,p in enumerate(general)]

@pytest.mark.parametrize('identifier,retained',CASES,ids=[case[0] for case in CASES])
def test_exact_retained_failed_record_now_conforms_without_replacing_observation(identifier,retained):
 assert retained['accepted'] is False
 original=copy.deepcopy(retained['input'])
 value=copy.deepcopy(original)
 assert value['format']=='host-preparation-result-draft-v3'
 value['format']='host-preparation-result-draft-v4'
 sealed=seal_record(value)
 result=validate_record(sealed)
 assert result=={'definition_conforms':True,'observations_authenticated':False,'runtime_or_native_pass':False}
 assert value['initial']==original['initial'] and value['terminal']==original['terminal']
 assert value['owned_store']==original['owned_store']
 assert retained['input']==original and retained['accepted'] is False
 for key in original:
  if key not in ('format','counters'):assert sealed[key]==original[key]
 for key in original['counters']:
  if key!='result_bytes':assert sealed['counters'][key]==original['counters'][key]
