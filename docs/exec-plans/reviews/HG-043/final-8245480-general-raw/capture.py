import hashlib, json, os, subprocess, sys
from pathlib import Path
root=Path.cwd()
sha="8245480918251739339987de69bfe41fa0b39af5"
name=sys.argv[1]
checks={"focused":[str(root/".venv/bin/python"),"-m","pytest","-q","tests/harness/test_review_evidence_provenance.py","tests/harness/test_validator.py","-k","provenance or Integration or integration or delayed or squash"],"replay":[str(root/".venv/bin/python"),str(root/"docs/exec-plans/evidence/HG-043/replay.py")]}
command=checks[name]
run=subprocess.run(command,env=dict(os.environ,PYTHONPATH=str(root/"src"),PYTHONDONTWRITEBYTECODE="1"),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
raw=run.stdout
report={"reviewed_head_sha":sha,"command":command,"exit_code":run.returncode,"raw_sha256":hashlib.sha256(raw).hexdigest(),"raw_byte_count":len(raw),"raw_utf8":raw.decode()}
path=root/"docs/exec-plans/reviews/HG-043/final-8245480-general-raw"/(name+".json")
assert not path.exists()
path.write_text(json.dumps(report,indent=2)+"\n")
print(name,run.returncode,len(raw),raw.decode()[-700:] if name=="focused" else "")
raise SystemExit(run.returncode)
