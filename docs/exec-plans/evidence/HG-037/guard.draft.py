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


def readiness_content_errors(path, before, after):
    """Preserve SQL/auth/namespace semantics outside bounded readiness plumbing."""
    import ast
    import copy
    if path == 'compose.yaml':
        import yaml
        old, new = yaml.safe_load(before), yaml.safe_load(after)
        expected = ['CMD-SHELL', 'pg_isready --host 127.0.0.1 --port 5432 --username "$${POSTGRES_USER}" --dbname "$${POSTGRES_DB}"']
        if new['services']['postgres']['healthcheck']['test'] != expected:
            return ['readiness-compose-tcp-required']
        new['services']['postgres']['healthcheck']['test'] = old['services']['postgres']['healthcheck']['test']
        return [] if old == new else ['readiness-compose-content-scope']
    if path != 'src/kineticloop/db/lifecycle.py':
        return []
    old, new = ast.parse(before), ast.parse(after)
    def methods(tree):
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DatabaseLifecycle')
        return cls, {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    oc, om = methods(old)
    nc, nm = methods(new)
    if set(om) != set(nm):
        return ['readiness-lifecycle-method-scope']
    if ast.dump(om['_run'].args) != ast.dump(nm['_run'].args):
        # Only one optional timeout parameter may be appended.
        args = copy.deepcopy(nm['_run'].args)
        if not args.kwonlyargs or args.kwonlyargs[-1].arg != 'timeout_seconds':
            return ['readiness-command-failure-policy']
        args.kwonlyargs.pop()
        args.kw_defaults.pop()
        if ast.dump(args) != ast.dump(om['_run'].args):
            return ['readiness-command-failure-policy']
    # _run may only pass a bounded timeout and translate TimeoutExpired;
    # command ownership, redaction and failure behavior remain exact.
    runner_calls = [node for node in ast.walk(nm['_run'])
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == '_runner']
    if len(runner_calls) != 1 or any(isinstance(node, (ast.For, ast.While))
                                   for node in ast.walk(nm['_run'])):
        return ['readiness-command-replay-forbidden']
    for node in ast.walk(nm['_run']):
        if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Attribute) and node.type.attr == 'TimeoutExpired':
            for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                if not isinstance(call.func, ast.Name) or call.func.id != 'DatabaseLifecycleError':
                    return ['readiness-timeout-handler-replay-forbidden']
    run = copy.deepcopy(nm['_run'])
    run.args = copy.deepcopy(om['_run'].args)
    for node in ast.walk(run):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == '_runner':
            node.keywords = [kw for kw in node.keywords if kw.arg != 'timeout']
        if isinstance(node, ast.Try):
            node.handlers = [handler for handler in node.handlers if not (
                isinstance(handler.type, ast.Attribute) and handler.type.attr == 'TimeoutExpired')]
    if ast.dump(run) != ast.dump(om['_run']):
        return ['readiness-command-body-scope']
    start_text = ast.unparse(nm['start'])
    if not all(value in start_text for value in ['--host', '127.0.0.1', '--port', '5432']):
        return ['readiness-start-tcp-required']
    for name in ('start', '_run'):
        # Readiness plumbing cannot invoke SQL, reset or cleanup.
        for node in ast.walk(nm[name]):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {'_psql', 'execute_sql', 'reset', 'destroy'}:
                    return ['readiness-startup-sql-or-cleanup']
        nc.body[nc.body.index(nm[name])] = copy.deepcopy(om[name])
    reset = nm['reset']
    for node in ast.walk(reset):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == '_run':
            node.keywords = [kw for kw in node.keywords if kw.arg != 'timeout_seconds']
        if isinstance(node.func, ast.Attribute) and node.func.attr == 'compose_command':
            args = node.args
            if any(isinstance(n, ast.Constant) and n.value == 'pg_isready' for n in args):
                values = [n.value if isinstance(n, ast.Constant) else None for n in args]
                if values.count('--host') != 1 or values.count('--port') != 1:
                    return ['readiness-reset-tcp-required']
                if values[values.index('--host') + 1] != '127.0.0.1' or values[values.index('--port') + 1] != '5432':
                    return ['readiness-reset-tcp-required']
                node.args = [n for i, n in enumerate(args) if i not in {
                    values.index('--host'), values.index('--host') + 1,
                    values.index('--port'), values.index('--port') + 1}]
    return [] if ast.dump(old) == ast.dump(new) else ['readiness-lifecycle-content-scope']
