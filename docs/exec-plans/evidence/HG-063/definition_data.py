"""Strict bounded definition JSON only; never reads report/source pointers."""
import json
from decimal import Decimal
from definition_oracle import Denied

def strict_json(raw,cap=1048576):
 if type(raw) is not bytes or len(raw)>cap:raise Denied('definition-json-bytes')
 def pairs(entries):
  obj={}
  for key,value in entries:
   if key in obj:raise Denied('definition-json-duplicate')
   obj[key]=value
  return obj
 def constant(_):raise Denied('definition-json-nonfinite')
 try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant,parse_float=Decimal)
 except (UnicodeDecodeError,json.JSONDecodeError,RecursionError):raise Denied('definition-json-syntax')
 stack=[(value,0)];nodes=0
 while stack:
  obj,depth=stack.pop();nodes+=1
  if nodes>262144 or depth>64:raise Denied('definition-json-nodes-depth')
  if isinstance(obj,dict):stack.extend((x,depth+1) for x in obj.values())
  elif isinstance(obj,list):stack.extend((x,depth+1) for x in obj)
 return value
