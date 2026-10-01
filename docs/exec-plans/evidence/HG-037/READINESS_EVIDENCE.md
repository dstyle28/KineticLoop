# HG-037 PostgreSQL readiness evidence

Preparation base: `0c11a89f4c624290bf8f2a911bc81e5740240e45`. These read-only observations motivate fresh follow-up `harness-backlog-v0.2/KL-074`, not a redefinition of completed KL002. HG037 does not implement the repair. Future KL074 checks remain NOT_RUN.

## Source observation and inference

At preparation base, `src/kineticloop/db/lifecycle.py` start runs Compose up --detach then accepts the first successful pg_isready without host/port, normally using a Unix socket. reset immediately executes DROP DATABASE through socket psql, then CREATE and another default pg_isready. `compose.yaml` configures postgres:16.10-alpine, and its healthcheck also omits host/port. Compose up does not wait for health. Existing `tests/db/test_lifecycle.py` mock readiness immediately; they do not model an init-stop-final sequence.

The saved official docker-library [entrypoint reference](https://raw.githubusercontent.com/docker-library/postgres/master/docker-entrypoint.sh) was fetched during preparation. It starts a temporary server with empty listen_addresses, stops it after initialization, then execs final postgres. This upstream master URL is mutable and version-varying: the saved SHA256 and retrieval provenance identify only this reference, not the deployed image's actual entrypoint.

The source and missing-socket failures strongly support acceptance of the temporary initialization server followed by its disappearance. Exact causal attribution to the deployed image remains unverified: no actual image digest/entrypoint and timestamped failing-container startup logs have been recovered here. KL074 must identify the actual configured/resolved image and demonstrate its init-stop-final ordering, rather than promoting this inference to root-cause PASS.

## Independently retrieved hosted evidence

[PR67](https://github.com/dstyle28/KineticLoop/pull/67) normally merged as `0c11a89`.
[Run36807167973](https://github.com/dstyle28/KineticLoop/actions/runs/36807167973) binds all three attempts to head `32d4d1a6ea10e09be42fa08eb56cd607ae9b2e35`:

- Attempt1: failure, 234 passed / 10 setup errors; planning, call ledger and factset fixture bootstrap failed at lifecycle reset DROP with `/var/run/postgresql/.s.PGSQL.5432` missing. Saved byte-exact failed-job log content in a JSON envelope.
- Attempt2: failure, 243 passed / 1 setup error; same missing socket at planning fixture DROP. Saved full failed-job log and attempt metadata.
- Attempt3: success, 244 passed, unchanged head; saved byte-exact full run log content in a JSON envelope and metadata.

These are setup failures, not product assertion failures. Same-SHA eventual success supports intermittency, not causal proof. Similar KL024/KL025 incidents were reported in delegation but are not independently reproduced or counted as verified evidence by this record.

## Narrow future boundary

Explicit container loopback TCP readiness excludes a socket-only init server. Align Compose and post-reset probes, bound the existing deadline including probe subprocess duration, preserve psql socket/auth behavior, and never retry destructive SQL. Unit runner/clock regressions must fail old code and pass repaired code. Three owned cold starts must capture actual image provenance, logs, migrations, exact namespace proof before reset, and cleanup. No CI suppression, fixed startup sleep, migration/authorization/product change, live data or credentials.

Raw GitHub logs have trailing blank-line spaces. JSON log envelopes preserve the original content, raw SHA256 and byte length without introducing whitespace-check failures into repository source. No log line was trimmed.
