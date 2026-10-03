# HG-048 author review

The changed entrypoint owns one local process topology (1–4 workers). Collection
preflight rejects paths outside tests/harness and explicit harness_serial markers
before execution in parallel mode. Scope and marker checks also run in workers.
Only the parent writes shared evidence; worker collections and reports are forwarded
through xdist. Worker restart is disabled. Missing IDs, duplicates, different
collections, skips, failed phases, worker crashes, JUnit identity disagreement and
source changes all prevent complete execution PASS. Pytest failure status remains
nonzero, raw output remains available, and owned execution processes are cleaned up.
Legacy JUnit export and collection-only invocation have explicit regression coverage.

Resource audit: generic ValidatorTests fixtures create per-test TemporaryDirectory
repositories, disable hooks/automatic Git maintenance, and copy authority files
into that repository. M3 History uses per-test tmp_path_factory repositories.
Other filesystem/Git fixtures use tmp_path; monkeypatch and mock state lives within
each process/test. Source decision tests read the shared checkout's committed Git
objects. Local-gate, App-publication and local-DB tests mock execution/publication
or use isolated temporary files/subprocess probes; they do not call a live Docker
DB lifecycle or publish a real check. No current harness fixture needs a shared
DB, migration chain, signing key, installation or primary-checkout mutation.
Future exclusive fixtures must be marked harness_serial and run with workers 1;
real tests/db remain on the existing serial command/controller paths.

The scope audit proves frozen files, runtime/DB/migration paths, execution policy
and workflows unchanged. Indexed identity/path sets are unchanged; only derived
hashes for authorized edited files are refreshed. validate_harness.py is a pinned
controller asset and changes only the exact HG-048 governance allowlist. Its
installation compatibility is explicitly recorded in CONTROLLER_HANDOFF.md.
No live controller installation or settings were edited.

This is author self-review, not independent GENERAL review. No review PASS,
production authorization, requirement PASS, App gate PASS or merge is asserted.
