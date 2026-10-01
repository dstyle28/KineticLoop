"""Prepare the structurally exact bounded-readiness guard, without product writes."""
import hashlib
import pprint
from pathlib import Path

ROOT = Path.cwd()
HERE = ROOT/'docs/exec-plans/evidence/HG-037'
original = (ROOT/'src/kineticloop/db/lifecycle.py').read_text()
old_start = original[original.index('    def start('):original.index('    def _psql(')]
new_start = '''    def start(self, *, timeout_seconds: float = 60.0) -> None:
        self.validate_compose()
        self._run(self.compose_command("up", "--detach", "postgres"))
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = self._run(
                self.compose_command(
                    "exec",
                    "--no-TTY",
                    "postgres",
                    "pg_isready",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5432",
                    "--username",
                    self.user,
                    "--dbname",
                    "postgres",
                ),
                check=False,
                timeout_seconds=remaining,
            )
            if result.returncode == 0:
                return
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
        raise DatabaseLifecycleError(
            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"
        )

'''
old_reset = original[original.index('    def reset('):original.index('    def connection(')]
new_reset = old_reset.replace('                "pg_isready",\n', '                "pg_isready",\n                "--host",\n                "127.0.0.1",\n                "--port",\n                "5432",\n').replace('            check=False,\n', '            check=False,\n            timeout_seconds=timeout_seconds,\n')
old_run = original[original.index('    def _run('):original.index('    def validate_compose(')]
new_run = old_run.replace('        check: bool = True,\n', '        check: bool = True,\n        timeout_seconds: float | None = None,\n').replace('                text=True,\n', '                text=True,\n                timeout=timeout_seconds,\n').replace('        except FileNotFoundError as error:\n', '        except subprocess.TimeoutExpired:\n            raise DatabaseLifecycleError("database readiness command timed out") from None\n        except FileNotFoundError as error:\n')
p=HERE/'guard.draft.py'; s=p.read_text(); s=s[:s.index('\nREADINESS_LIFECYCLE_BASE_SHA256') if '\nREADINESS_LIFECYCLE_BASE_SHA256' in s else s.index('\ndef readiness_content_errors')]
s+='\nREADINESS_LIFECYCLE_BASE_SHA256 = '+repr(hashlib.sha256(original.encode()).hexdigest())+'\n'
s+='READINESS_LIFECYCLE_REPLACEMENTS = '+pprint.pformat([(old_run,new_run),(old_start,new_start),(old_reset,new_reset)],width=98)+'\n'
s+='''

def readiness_lifecycle_candidate(before):
    """Only the complete reviewed bounded-readiness delta is authorized."""
    if hashlib.sha256(before).hexdigest() != READINESS_LIFECYCLE_BASE_SHA256:
        raise ValueError('unexpected readiness lifecycle baseline')
    text = before.decode()
    for old, new in READINESS_LIFECYCLE_REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('unexpected readiness lifecycle method baseline')
        text = text.replace(old, new, 1)
    return text.encode()


def readiness_content_errors(path, before, after):
    """Keep startup ownership, SQL/auth and every other source byte exact."""
    if path == 'compose.yaml':
        import yaml
        try:
            old, new = yaml.safe_load(before), yaml.safe_load(after)
            expected = ['CMD-SHELL', 'pg_isready --host 127.0.0.1 --port 5432 --username "$${POSTGRES_USER}" --dbname "$${POSTGRES_DB}"']
            if new['services']['postgres']['healthcheck']['test'] != expected:
                return ['readiness-compose-tcp-required']
            new['services']['postgres']['healthcheck']['test'] = old['services']['postgres']['healthcheck']['test']
            return [] if old == new else ['readiness-compose-content-scope']
        except (KeyError, TypeError, yaml.YAMLError):
            return ['readiness-compose-content-scope']
    if path != 'src/kineticloop/db/lifecycle.py':
        return []
    try:
        expected = readiness_lifecycle_candidate(before)
    except (ValueError, UnicodeError):
        return ['readiness-lifecycle-baseline-unexpected']
    return [] if after == expected else ['readiness-lifecycle-content-scope']
'''
p.write_text(s)
p=ROOT/'tools/harness/validate_harness.py'; s=p.read_text(); a=s.index('\nREADINESS_LIFECYCLE_BASE_SHA256') if '\nREADINESS_LIFECYCLE_BASE_SHA256' in s else s.index('\ndef readiness_content_errors');z=s.index("\n\nif __name__ == '__main__':",a)
new=s[:a]+'\nREADINESS_LIFECYCLE_BASE_SHA256'+(HERE/'guard.draft.py').read_text().split('\nREADINESS_LIFECYCLE_BASE_SHA256',1)[1]
p.write_text(new+s[z:])
