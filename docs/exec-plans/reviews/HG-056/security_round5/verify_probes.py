"""Exact-R classifier review; synthetic input is parsed/recovered, never executed."""
import ast, hashlib, json, subprocess, tempfile, types
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
R = 'd8aaf7c897e5a7653daa30b8d3bd906ba859652d'
B = '3ec7f7a38d974256a928c3687f63e4d90019e42b'
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)
def blob(path, revision=R): return git('show', revision + ':' + path)
code = blob('tools/harness/compact_evidence.py')
ce = types.ModuleType('exact_review_ce'); ce.__file__ = str(ROOT/'tools/harness/compact_evidence.py')
# Execute only the reviewed decoder implementation; never fixture/provider/source input.
exec(compile(code, 'exact_review_decoder', 'exec'), ce.__dict__)
K, M = 'kineticloop_evidence', 'compact_reencoding'
def target(key=K): return 'record[' + json.dumps(key) + ']'
def write(key=K): return target(key) + ', ordinary = "gzip-v1", "x"'
cases = {
's1-subscript': (target() + ' = "gzip-v1"', 'reject'),
's1-map': (target(M) + ' = "v1"', 'reject'),
's2-octal': ('record = {"' + K.replace('_', '\\137') + '": "gzip-v1"}', 'reject'),
's2-continued': ('record = {"kineticloop_" \\\n"evidence": "gzip-v1"}', 'reject'),
's3-array-values': (json.dumps(['ordinary', K]), 'plain'),
's3-reader-default': ('record.get("ordinary", '+json.dumps(K)+')', 'plain'),
's6-prefix': ('record = {"kineticloop_" r"evidence": "gzip-v1"}', 'reject'),
's6-comment-adjacent': ('record = {("compact_" # c\n"reencoding"): "v1"}', 'reject'),
's7-named': ('record = {"kineticloop\\N{LOW LINE}evidence": "gzip-v1"}', 'reject'),
's8-multiline': (K + ': (\n str\n) = "gzip-v1"', 'reject'),
's9-comment-target': ('record[' + json.dumps(K) + ' # c\n] = "gzip-v1"', 'reject'),
's9-comment-map': ('record[' + json.dumps(M) + ' # c\n] += "v1"', 'reject'),
's9-parenthesized': ('(' + target() + ' # c\n) = "gzip-v1"', 'reject'),
's10-tuple': (write(), 'reject'),
's10-list': ('[' + target() + ', ordinary] = ["gzip-v1", "x"]', 'reject'),
's10-nested': ('((' + target(M) + ', ordinary), other) = (("v1", "x"), "y")', 'reject'),
's10-starred': (target() + ', *ordinary = ["gzip-v1", "x"]', 'reject'),
'root-invalid-rhs': (target() + ', ordinary = $$$', 'reject'),
'root-incomplete-rhs': (target() + ', ordinary = (', 'reject'),
'root-string-wrapper': (chr(34)+'record['+chr(39)+K+chr(39)+'], ordinary = '+chr(39)+'gzip-v1'+chr(39)+', '+chr(39)+'x'+chr(39)+chr(34), 'reject'),
'new-comment-tuple': ('# '+write(), 'reject'),
'new-comment-map-list': ('# [' + target(M) + ', ordinary] = ["v1", "x"]', 'reject'),
'new-prose-tuple': ('prefix '+write(), 'reject'),
'new-prose-nested-map': ('prefix ((' + target(M) + ', ordinary), other) = (("v1", "x"), "y")', 'reject'),
'ordinary-tuple-rhs': ('ordinary, other = '+target()+', "x"', 'plain'),
'ordinary-comment-read': ('# ordinary, other = '+target()+', "x"', 'plain'),
'ordinary-prose-read': ('prefix ordinary, other = '+target()+', "x"', 'plain'),
'ordinary-string-read': (json.dumps('ordinary, other = '+target()+', "x"'), 'plain'),
'ordinary-get': ('record.get('+json.dumps(K)+')', 'plain'),
'ordinary-surrogate': ('ordinary = "x=\\ud800"; record.get('+json.dumps(K)+')', 'plain'),
'reserved-surrogate': (target()+', ordinary = "x=\\ud800", "x"', 'reject'),
}
encodings = ['utf-8','utf-8-sig','utf-16-le','utf-16-be','utf-16','utf-32-le','utf-32-be','utf-32']
rows=[]; reads=[]
for name,(text,expected) in cases.items():
 for encoding in encodings:
  raw=text.encode(encoding)
  for codec in [None, ce.FORMAT, ce.XZ_FORMAT]:
   recovered=raw if codec is None else ce.decode(ce.encode(raw,codec),codec,len(raw))
   assert recovered==raw
   row={'case':name,'encoding':encoding,'recovery':codec or 'plain','expected':expected,'bytes':len(raw),'sha256':ce.digest(raw)}
   for fn in ['envelope','reencoding_record']:
    try: row[fn]='plain' if getattr(ce,fn)(recovered) is None else 'metadata'
    except ValueError as ex: row[fn]='reject'; row[fn+'_error']=str(ex)
   rows.append(row)
with tempfile.TemporaryDirectory(prefix='hg056-security-r5-',dir='/private/tmp') as scratch:
 root=Path(scratch)
 for name in [n for n in cases if n.startswith('new-')]:
  for encoding in ['utf-8','utf-16','utf-32']:
   raw=cases[name][0].encode(encoding)
   for suffix in ['py','json','txt','log','arbitrary']:
    path='docs/exec-plans/evidence/HG-056/probe.'+suffix
    targetpath=root/path;targetpath.parent.mkdir(parents=True,exist_ok=True);targetpath.write_bytes(raw)
    try: result=ce.read(root,path,None); outcome='plain-byte-identical' if result==raw else 'changed'
    except ValueError as ex: outcome='reject:'+str(ex)
    reads.append({'case':name,'encoding':encoding,'suffix':suffix,'revision':None,'outcome':outcome,'sha256':ce.digest(raw),'bytes':len(raw)})
original_path='docs/exec-plans/reviews/KL-036/SECURITY_DATA_BOUNDARY/audit.py'
original_revision='f93364d90aaae9b0b62706fd4e4fe395a8cd8ec5'
original=blob(original_path,original_revision)
assert len(original)==8063 and ce.digest(original)=='a602ee684cdd7b4d8169388d2a2fe821fc6bc5beadf0d69a593c2ed260ffe382'
assert ce.envelope(original) is None and ce.reencoding_record(original) is None
assert blob('docs/exec-plans/evidence/HG-056/original-reader.fixture')==original
assert ce.read(ROOT,original_path,original_revision)==original
original_pin={'revision':original_revision,'bytes':len(original),'sha256':ce.digest(original),'entry':git('ls-tree',original_revision,'--',original_path).decode().strip(),'exact_bound_read_byte_identical':True,'helper_executed':False}
def functions(raw):
 tree=ast.parse(raw)
 return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
old,new=functions(blob('tools/harness/compact_evidence.py',B)),functions(code)
changed=[name for name in old if old[name]!=new[name]]
assert changed==['reserved_ascii', 'envelope']
unchanged=[name for name in old if name not in changed]
added=sorted(set(new)-set(old))
new_failures=sorted({r['case'] for r in rows if r['expected']=='reject' and r['envelope']=='plain'})
print(json.dumps({'observed_plain_hostile':new_failures}))
assert new_failures==sorted(n for n in cases if n.startswith('new-'))
assert all(r['envelope']==r['reencoding_record'] for r in rows)
assert all(r['envelope']=='plain' for r in rows if r['expected']=='plain')
static_wrappers=[]
for name in new_failures:
 text=cases[name][0]
 unwrapped=text[2:] if text.startswith('# ') else text[7:]
 tree=ast.parse(unwrapped)
 assert isinstance(tree.body[0],ast.Assign)
 fields=sorted({node.slice.value for node in ast.walk(tree) if isinstance(node,ast.Subscript) and isinstance(node.ctx,ast.Store) and isinstance(node.slice,ast.Constant)})
 assert fields and all(key in (K,M) for key in fields)
 static_wrappers.append({'case':name,'unwrapped_statement_type':'Assign','literal_reserved_store_targets':fields,'wrapper':'comment' if text.startswith('# ') else 'prose','input_executed':False})
summary={'R':R,'case_count':len(cases),'classifier_pairs':len(rows),'new_defect_cases':new_failures,'new_defect_pairs':sum(r['case'] in new_failures for r in rows),'plain_read_defect_count':sum(r['outcome']=='plain-byte-identical' for r in reads),'ordinary_all_plain':True,'old_reviewed_forms_reject':True,'original':original_pin,'input_executed':False,'synthetic_commits_created':False,'for_with_incidental_contexts_not_findings':True}
(OUT/'classifier-probes.json').write_text(json.dumps({'summary':summary,'static_wrapper_assignments':static_wrappers,'rows':rows},separators=(',',':'))+'\n')
(OUT/'read-probes.json').write_text(json.dumps({'R':R,'scope':'Temporary working-file plain reads only; no synthetic bound-read fixtures or commits','reads':reads},indent=2)+'\n')
(OUT/'static-boundary.json').write_text(json.dumps({'R':R,'B':B,'changed_existing_functions':changed,'added_functions':added,'unchanged_functions':unchanged,'other_existing_bodies_identical':True,'lexical_denial_precedes_AST':True,'AST_only_adds_keys_to_denial':True,'no_eval_or_literal_eval':True,'no_input_execution':True,'availability_suffix_proposal':'NOT_IMPLEMENTED','codec_budget_retention_history_reader_bodies_unchanged':True},indent=2)+'\n')
print(json.dumps(summary,indent=2))
