# Development diagnostic history

The development runs at 7a411c9e237ffe9df49eb1467f4ec6bbbf019ca9 contain
1,070 tests and are indexed separately in BENCHMARK_INDEX.json. Their raw logs, JUnit,
collections and manifests are committed. Two obsolete successful phase records
remain in the listed local paths, with hashes/lengths recorded in
excluded_development_artifacts; this removes redundant prototype bulk from the
prospective 16 MiB PR budget. Every final and interrupted-run phase record is
committed in full. The initial
two-worker run overlapped an earlier task-owned authority check and is excluded
from the final speedup comparison. The four-worker run completed. The serial
run was deliberately interrupted (outer exit 130) after discovering legacy JUnit
flag compatibility needed correction. Its partial log/JUnit/worker data is failure
evidence, not PASS. The prototype manifest's observer-exit mismatch reflects
that interruption; final source records the actual child return status separately.

Commit 0045808352507b7af67a3a2135408421d8bcc6bc preserves --junitxml /
--junit-xml exports and explicitly separates COLLECTION_ONLY from completed
execution. All final serial, two-worker, four-worker and repeated two-worker runs
use this exact source with 1,071 cases. Prototype timing is not combined with them.
