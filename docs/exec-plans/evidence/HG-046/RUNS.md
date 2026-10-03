# HG-046 execution evidence

Selected implementation SHA: 341333dd4b5140ac15f715ce28bd0d2a4a4ee1ec. The checks-* and db-* directories
at this SHA are selected PASS evidence; development/* contains earlier failed or
interrupted diagnostics and is never selected. The initial nested overlay driver
failed before tests; using a fresh owned data volume fixed it. Subsequent lint/type
issues in the new test were fixed before the selected run. Independent security
review found implicit Docker proxy forwarding; cc05b13 rejects effective proxy
configuration and ambient builder overrides. The prior 6a4e04f DB run was
interrupted for that correction and is never selected. Both owned resources
were removed after every volume-backed attempt. Earlier interrupted suites were
stopped for the new implementation, not counted as regression PASS. The completed cc05b13 suite had 672 PASS and two failures: the obsolete
generic-workflow hash assertion in startup_readiness and the old paths-ignore
string assertion in test_workflow. The afca6c0 partial run was interrupted after
the second failure was exposed. The final implementation changes only these
compatibility assertions to the authorized new CI policy, preserves all
KL-074-specific checks, and declares an exact HG-046-only exception for those
two test paths. Failed/partial runs remain development evidence; final full DB
proof is rerun in full.

The local executor used Linux ARM64 with a dedicated nested daemon. Actual
collection/execution, JUnit, commands, raw stdout and versions are inside the run
manifest; image identity and outer cleanup are in local-executor.json. No hosted
DB run is claimed for the new workflow. Historical task result/evidence and the
separate HG-045 PR are unchanged. The hosted fallback uses the same command plan
and is explicit, never automatically dispatched by this task.

Capture and scope-audit scripts are copied here byte-for-byte from the exact
/private/tmp command paths named by their capture records. Selected raw bytes are
retained exactly, including whitespace. The task record is committed only after
these checks passed; fresh independent reviews will bind that resulting SHA.
