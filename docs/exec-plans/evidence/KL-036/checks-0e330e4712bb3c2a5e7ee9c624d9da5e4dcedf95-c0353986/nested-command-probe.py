from pathlib import Path
import importlib.util,json,subprocess,sys
from unittest.mock import Mock
root=Path.cwd();path=root/'tests/unit/workflow/test_worker_reaper.py'
assert path.read_bytes()==subprocess.check_output(['git','show','HEAD:tests/unit/workflow/test_worker_reaper.py'])
spec=importlib.util.spec_from_file_location('kl036_namespace_probe',path)
assert spec and spec.loader
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
runner=Mock(return_value=subprocess.CompletedProcess([],0,'',''))
lifecycle=module.WorkerLifecycle(root,sha,runner=runner,environ={})
rejected=False
try:lifecycle._run(lifecycle.compose_command('up','--detach','postgres','--project-name','foreign'))
except ValueError:rejected=True
ok=rejected and runner.call_count==0
print(json.dumps({'task_identity':'harness-backlog-v0.2/KL-036','tested_commit':sha,'foreign_override_rejected_before_runner':ok,'mock_runner_calls':runner.call_count,'physical_docker_io':False,'result':'PASS' if ok else 'FAIL'}))
sys.exit(0 if ok else 1)
