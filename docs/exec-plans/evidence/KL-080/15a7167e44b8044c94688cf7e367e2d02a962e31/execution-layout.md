# KL-080 verification layout

All seventeen packet commands were executed against immutable implementation
`15a7167e44b8044c94688cf7e367e2d02a962e31`. The runner preserved the exact
packet command in each raw stdout log. `PYTEST_ADDOPTS` added only JUnit
capture, and `-s` for the complete own DB suite to retain raw row, guard,
namespace and cleanup witnesses. Each pytest selector has a separate raw
collection log and node list; execution counts must equal collection counts.

One worker ran the namespace preflight first, followed by all own source
commands serially. No two local DB lifecycles overlapped. Two independent
workers ran repository unit and harness regressions, then the normal harness,
lint and type checks. No imported foreign pytest lifecycle was invoked.

The own fixture aligns its process timezone with the registered UTC test
calendar so immutable builders using `date.today()` use the actual calendar
day. This also applies to the separate exact prior-deployment child process.
Cleanup restores the prior process timezone. Neither the real clock nor the
trusted calendar guard is changed. Raw namespace witnesses record UTC.

The previous review cycle is retained in Git history and its original evidence
directory. Its shared assertion scope finding was corrected by restoring the
original assertion and keeping duplicate-event verification solely in the own
suite. This cycle independently reruns every required command. Interrupted
development diagnostics at `6bba630` are outside the committed proof corpus;
they are not task PASS evidence.

The actual unchanged hosted PostgreSQL and quality workflow identities are
recorded separately in `hosted-status.json`. A pending run does not establish
hosted PASS. All source, task, review, hosted, integration and product status
claims remain separate.
