from pathlib import Path
import subprocess, os, json, hashlib, tempfile, time
root=Path('/Users/davetian/.codex/worktrees/8578/KineticLoop')
out=root/'docs/exec-plans/reviews/HG-044/GENERAL-r4-raw'
temp=tempfile.mkdtemp(prefix='hg044-general-r4-',dir='/private/tmp')
command=['/private/tmp/hg044-venv/bin/python','-m','pytest','-q','-p','no:cacheprovider','--basetemp',temp+'/pytest','--junitxml',str(out/'targeted.xml'),
 'tests/harness/test_m3_milestone_closure.py::test_genuine_pytest_parameter_collection_and_junit_are_accepted',
 'tests/harness/test_m3_milestone_closure.py::test_each_multiselect_suite_requires_collected_and_executed_cases',
 'tests/harness/test_m3_milestone_closure.py::test_integrated_regression_fails_closed[float-exit]',
 'tests/harness/test_m3_milestone_closure.py::test_integrated_regression_fails_closed[collection-float-exit]',
 'tests/harness/test_m3_milestone_closure.py::test_integrated_regression_fails_closed[collection-skipped]',
 'tests/harness/test_m3_milestone_closure.py::test_legacy_m1_m2_schema_and_validator_behavior_unchanged']
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(root/'src')); env.pop('PYTEST_ADDOPTS',None)
start=time.time(); p=subprocess.run(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(out/'targeted.log').write_bytes(p.stdout)
record={'reviewed_head_sha':'4bc0b0122245d54649e3f3d03a9acce7d4c6df2a','command':command,'exit_code':p.returncode,'duration_seconds':time.time()-start,'stdout_path':str((out/'targeted.log').relative_to(root)),'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'temp_directory':temp}
(out/'commands.json').write_text(json.dumps([record],indent=2)+'\n'); print(p.stdout.decode()); raise SystemExit(p.returncode)
