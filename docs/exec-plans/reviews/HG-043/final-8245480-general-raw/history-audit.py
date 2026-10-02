import json, subprocess, hashlib
from pathlib import Path
sha="8245480918251739339987de69bfe41fa0b39af5"
git=lambda *a: subprocess.check_output(["git",*a])
blob=lambda p:git("show",sha+":"+p)
report={"reviewed_head_sha":sha,"prior_reviews_preserved":[],"historical_checks":[]}
for kind in ["GENERAL","PROTOCOL","DB_CONCURRENCY"]:
 raw=blob("docs/exec-plans/reviews/HG-043/"+kind+".json")
 assert raw==blob("docs/exec-plans/reviews/HG-043/round-2896d24/"+kind+".json")
 data=json.loads(raw);assert data["status"]=="CHANGES_REQUIRED"
 report["prior_reviews_preserved"].append({"review_type":kind,"original_sha":data["reviewed_head_sha"],"status":data["status"],"raw_sha256":hashlib.sha256(raw).hexdigest()})
for path in git("ls-tree","-r","--name-only",sha,"--","docs/exec-plans/evidence/HG-043").decode().splitlines():
 if not path.endswith(".json"):continue
 data=json.loads(blob(path))
 if "raw_utf8" not in data: continue
 raw=data["raw_utf8"].encode();assert hashlib.sha256(raw).hexdigest()==data["raw_sha256"];assert len(raw)==data["raw_byte_count"]
 if not data["tested_commit"].startswith("97b76c7"):
  report["historical_checks"].append({"path":path,"tested_commit":data["tested_commit"],"result":data["result"],"exit_code":data["exit_code"],"raw_sha256":data["raw_sha256"]})
report["final_check_oracles"]={}
for key in ["unit","lint","typecheck","validation"]:
 data=json.loads(blob("docs/exec-plans/evidence/HG-043/"+key+"-97b76c7.json"))
 report["final_check_oracles"][key]=data["raw_utf8"][-400:]
print(json.dumps(report,indent=2))
