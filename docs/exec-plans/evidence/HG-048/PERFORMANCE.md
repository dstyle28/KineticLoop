# HG-048 measurements

Tested source: `0045808352507b7af67a3a2135408421d8bcc6bc`; protected base: `391c9198fa8ec647e377a0572700bc7568468c85`.
Four sequential full harness runs used the same clean source, Python 3.12.14,
pytest 8.4.2, pytest-xdist 3.8.0 and execnet 2.1.2 on macOS 26.6.2 ARM64,
18 physical/logical CPUs and 36 GiB RAM. Wall times include serial preflight
collection, worker startup, execution, JUnit checking and evidence aggregation.

| Run order | Workers | Wall seconds | Serial / run | Passed / failed |
|---|---:|---:|---:|---:|
| initial-w2 | 2 | 606.68 | 1.85× | 1,071 / 0 |
| w4 | 4 | 378.61 | 2.97× | 1,071 / 0 |
| serial | 1 | 1124.21 | 1.00× | 1,071 / 0 |
| repeat-w2 | 2 | 587.36 | 1.91× | 1,071 / 0 |

All four runs collected the same ordered 1,071 node IDs. Each executed every ID
exactly once, with matching JUnit identities and all 3,213 setup/call/teardown
reports passed. The 18 new process/evidence regression cases are included in every
run. No test is removed, skipped or relabeled to improve these numbers.

The default is two local processes, bounded to four. Use `uv run kl test-harness
--workers 1` for serial or `--workers 4` for the faster measured local option.
Two is conservative: several expensive cases grew from roughly 120–123 seconds
with two workers to 145–147 seconds with four. Four still completed faster overall.
There is one serial run, one four-worker run and two two-worker runs; this is a
local comparison, not a statistical performance guarantee. Background applications
and filesystem caches were not disabled. No task-owned quality subprocesses ran
during this comparison. The selected source predates PR 91; its separately owned
Git evidence-read optimization must be retained during integration, followed by
required retesting. Numbers on another source/cohort are not this baseline.

Independent lint, typecheck and unit commands were captured concurrently only
after all benchmark runs ended, with at most three subprocesses. This capture
script does not change the installed quality controller. See QUALITY.json for
individual and combined time; the harness remains the dominant measured cost.

BENCHMARK_INDEX.json maps every original raw log, JUnit, full collection, final/interrupted worker
execution record and run manifest to a lossless envelope. COMPARISON.json contains
the numerical comparison. RAW_RETRIEVAL.md explains exact-revision retrieval.
These are developer harness checks. Product requirements are NOT_RUN; independent
GENERAL review, the App-bound full DB gate, merge and activation are separate facts.
