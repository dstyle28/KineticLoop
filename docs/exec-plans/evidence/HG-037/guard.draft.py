# Generated HG037 guard proposal; append only after HG036 merge.
READINESS_TASK_DEFINITION = None  # filled from ratified proposal
READINESS_PACKET_BOUNDARIES = None  # filled from ratified proposal


def readiness_definition_errors(task):
    if task.get('id') != 'KL-074':
        return []
    return ['readiness-definition-drift:' + field
            for field in set(task) | set(READINESS_TASK_DEFINITION)
            if task.get(field) != READINESS_TASK_DEFINITION.get(field)]


def readiness_packet_errors(task, text):
    if task.get('id') != 'KL-074':
        return []
    return ['readiness-packet-boundary:' + heading
            for heading, value in READINESS_PACKET_BOUNDARIES.items()
            if (section(text, heading) or '').strip() != value]


READINESS_LIFECYCLE_BASE_SHA256 = 'de55f62dd25e3379c67b7b6306cdbd882ce8a6d3d615715a7f9d35c30c6a3686'
READINESS_LIFECYCLE_REPLACEMENTS = [('    def _run(\n'
  '        self,\n'
  '        command: Sequence[str],\n'
  '        *,\n'
  '        check: bool = True,\n'
  '    ) -> subprocess.CompletedProcess[str]:\n'
  '        try:\n'
  '            return self._runner(\n'
  '                list(command),\n'
  '                cwd=self.root,\n'
  '                env=self.environment,\n'
  '                check=check,\n'
  '                capture_output=True,\n'
  '                text=True,\n'
  '            )\n'
  '        except FileNotFoundError as error:\n'
  '            raise DatabaseLifecycleError(\n'
  '                "Docker with the Compose plugin is required for the local test database."\n'
  '            ) from error\n'
  '        except subprocess.CalledProcessError as error:\n'
  '            details = Redactor((self.user, self.password)).exception_diagnostic(error)\n'
  '            raise DatabaseLifecycleError(f"database command failed: {details}") from None\n'
  '\n',
  '    def _run(\n'
  '        self,\n'
  '        command: Sequence[str],\n'
  '        *,\n'
  '        check: bool = True,\n'
  '        timeout_seconds: float | None = None,\n'
  '    ) -> subprocess.CompletedProcess[str]:\n'
  '        try:\n'
  '            return self._runner(\n'
  '                list(command),\n'
  '                cwd=self.root,\n'
  '                env=self.environment,\n'
  '                check=check,\n'
  '                capture_output=True,\n'
  '                text=True,\n'
  '                timeout=timeout_seconds,\n'
  '            )\n'
  '        except subprocess.TimeoutExpired:\n'
  '            raise DatabaseLifecycleError("database readiness command timed out") from None\n'
  '        except FileNotFoundError as error:\n'
  '            raise DatabaseLifecycleError(\n'
  '                "Docker with the Compose plugin is required for the local test database."\n'
  '            ) from error\n'
  '        except subprocess.CalledProcessError as error:\n'
  '            details = Redactor((self.user, self.password)).exception_diagnostic(error)\n'
  '            raise DatabaseLifecycleError(f"database command failed: {details}") from None\n'
  '\n'),
 ('    def start(self, *, timeout_seconds: float = 60.0) -> None:\n'
  '        self.validate_compose()\n'
  '        self._run(self.compose_command("up", "--detach", "postgres"))\n'
  '        deadline = time.monotonic() + timeout_seconds\n'
  '        while time.monotonic() < deadline:\n'
  '            result = self._run(\n'
  '                self.compose_command(\n'
  '                    "exec",\n'
  '                    "--no-TTY",\n'
  '                    "postgres",\n'
  '                    "pg_isready",\n'
  '                    "--username",\n'
  '                    self.user,\n'
  '                    "--dbname",\n'
  '                    "postgres",\n'
  '                ),\n'
  '                check=False,\n'
  '            )\n'
  '            if result.returncode == 0:\n'
  '                return\n'
  '            time.sleep(0.5)\n'
  '        raise DatabaseLifecycleError(\n'
  '            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"\n'
  '        )\n'
  '\n',
  '    def start(self, *, timeout_seconds: float = 60.0) -> None:\n'
  '        self.validate_compose()\n'
  '        self._run(self.compose_command("up", "--detach", "postgres"))\n'
  '        deadline = time.monotonic() + timeout_seconds\n'
  '        while time.monotonic() < deadline:\n'
  '            remaining = deadline - time.monotonic()\n'
  '            if remaining <= 0:\n'
  '                break\n'
  '            result = self._run(\n'
  '                self.compose_command(\n'
  '                    "exec",\n'
  '                    "--no-TTY",\n'
  '                    "postgres",\n'
  '                    "pg_isready",\n'
  '                    "--host",\n'
  '                    "127.0.0.1",\n'
  '                    "--port",\n'
  '                    "5432",\n'
  '                    "--username",\n'
  '                    self.user,\n'
  '                    "--dbname",\n'
  '                    "postgres",\n'
  '                ),\n'
  '                check=False,\n'
  '                timeout_seconds=remaining,\n'
  '            )\n'
  '            if result.returncode == 0:\n'
  '                return\n'
  '            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))\n'
  '        raise DatabaseLifecycleError(\n'
  '            f"PostgreSQL did not become ready within {timeout_seconds:g} seconds"\n'
  '        )\n'
  '\n'),
 ('    def reset(self, *, timeout_seconds: float = 60.0) -> DatabaseConnection:\n'
  '        self.start(timeout_seconds=timeout_seconds)\n'
  '        quoted_database = f\'"{self.namespace.database_name}"\'\n'
  '        quoted_user = f\'"{self.user}"\'\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",\n'
  '        )\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"CREATE DATABASE {quoted_database} OWNER {quoted_user};",\n'
  '        )\n'
  '        ready = self._run(\n'
  '            self.compose_command(\n'
  '                "exec",\n'
  '                "--no-TTY",\n'
  '                "postgres",\n'
  '                "pg_isready",\n'
  '                "--username",\n'
  '                self.user,\n'
  '                "--dbname",\n'
  '                self.namespace.database_name,\n'
  '            ),\n'
  '            check=False,\n'
  '        )\n'
  '        if ready.returncode != 0:\n'
  '            raise DatabaseLifecycleError("reset database failed its readiness probe")\n'
  '        return self.connection()\n'
  '\n',
  '    def reset(self, *, timeout_seconds: float = 60.0) -> DatabaseConnection:\n'
  '        self.start(timeout_seconds=timeout_seconds)\n'
  '        quoted_database = f\'"{self.namespace.database_name}"\'\n'
  '        quoted_user = f\'"{self.user}"\'\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"DROP DATABASE IF EXISTS {quoted_database} WITH (FORCE);",\n'
  '        )\n'
  '        self._psql(\n'
  '            "postgres",\n'
  '            f"CREATE DATABASE {quoted_database} OWNER {quoted_user};",\n'
  '        )\n'
  '        ready = self._run(\n'
  '            self.compose_command(\n'
  '                "exec",\n'
  '                "--no-TTY",\n'
  '                "postgres",\n'
  '                "pg_isready",\n'
  '                "--host",\n'
  '                "127.0.0.1",\n'
  '                "--port",\n'
  '                "5432",\n'
  '                "--username",\n'
  '                self.user,\n'
  '                "--dbname",\n'
  '                self.namespace.database_name,\n'
  '            ),\n'
  '            check=False,\n'
  '            timeout_seconds=timeout_seconds,\n'
  '        )\n'
  '        if ready.returncode != 0:\n'
  '            raise DatabaseLifecycleError("reset database failed its readiness probe")\n'
  '        return self.connection()\n'
  '\n')]


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
