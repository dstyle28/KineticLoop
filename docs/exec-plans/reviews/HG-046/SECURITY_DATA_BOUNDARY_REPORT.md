# HG-046 SECURITY_DATA_BOUNDARY independent review

Verdict: PASS. No BLOCKER or REQUIRED_FOLLOWUP findings in the security scope.

Reviewed implementation/result: `dedf063f909419dd05e0f49e8a7e646903e3548a`.
Protected base: `fc8a044ffa4d15a74ce5dc59298ae411f1f4009b`.
Selected tested implementation: `c91d2635427a13a97a53fe4e52ec4655e1e7d866`.
Identity: `harness-governance-v0.1/HG-046`; contract v0.2.

This fresh-context review followed AGENTS.md, CURRENT_DOCUMENT_INDEX.json and the
pr-merge-reviewer skill. HG-046 is a governance task: its packet/result authority
is docs/exec-plans/governance/HG-046.yaml plus its approved SCOPE.md extension.
I independently inspected the changed controller, App client, worker wrappers,
classifier, evidence validation, workflow policies, focused tests and selected
execution records. I did not read private configuration, admission or key files,
use credentials, install a controller, publish a check, or run another DB suite.

## Trust and credential boundaries

The installed controller loads its sibling trusted modules and pins all ten
assets. Its worker invokes the installed validator and pytest observer by absolute
paths under isolated Python. Candidate runner manifests cannot request a verdict
or bypass the host-owned command plan. Operator admission binds repository, PR,
live master, head and controller identity and requires an owner-only regular file.
It rejects fork/wrong-repository/closed PRs, incomplete pins and mismatched
admission before worker execution. The operator and installed files remain trusted.

Privileged nested Docker is expressly restricted to reviewed trusted project code.
Candidate tests and dependencies run with substantial worker privileges; the
mechanism does not claim to resist hostile candidate code or a compromised
administrator. Public automatic execution needs the separately documented worker
boundary. This limitation is material and adequately disclosed for the approved
operator-admitted scope.

The signer uses owner-only regular key/config files, an eight-minute JWT and a
repository-restricted installation token. The client verifies App/installation,
selected-repository mode, account and exact checks-write/contents-read/PR-read/
metadata-read permissions before minting a token. Requests use a fixed HTTPS API
origin, disable proxies and redirects, and redact HTTP error bodies. Tokens remain
in memory; signing uses stdin and captured output, not token-bearing command-line
arguments. Worker commands and source bundles do not receive App configuration,
admission, private key or authentication tokens. Changed tracked files were
pattern-scanned for PEM keys and GitHub token prefixes; the sole match was a
literal private-key detection pattern in controller_scope_audit.py, not a key.

## Worker evidence, cleanup and publication

The controller owns its build context, command ordering, observed process exits,
verdict parser and dedicated labelled container/volume. It rejects unexpected
mounts/network sharing, populated nested daemons and implicit Docker proxy
forwarding. Copied evidence rejects symlinks, devices and oversized files before
parsing. DB collection/execution/JUnit identities must agree without skip/failure;
quality JUnit must be nonempty without skip/failure. Cleanup includes uncertain
creation outcomes and checks exact ownership before removal. Cleanup failure
cannot publish success, and foreign resources are not removed.

The controller reads current master independently of PR base metadata, requires
master ancestry, and rereads head/base after work and immediately before
publication. It creates one App-owned check, then PATCHes that exact check ID;
response validation binds App, head, name and ID. Missing, failed or interrupted
execution cannot produce a success verdict. The narrow inert-file classifier
preserves both sides of renames and makes unknown/executable/link/submodule paths
require DB. Every classification still executes quality and merge validation.

Committed applied/effective rules snapshots show master PR-only protection,
strict required-check freshness, no bypass actors, no force push/deletion, and
local-db-gate bound to App 5169734 alongside quality/merge-gate from App 15368.
This review inspects those recorded snapshots; it does not claim a new live API
readback or independent use of the App credentials.

## Independent verification and state

I reran `/private/tmp/hg044-venv/bin/python -m pytest -q -p no:cacheprovider
 tests/harness/test_local_gate.py tests/harness/test_db_policy.py
 tests/harness/test_local_db_ci.py`: 112 passed in 2.69 seconds. Coverage includes
admission/pin/permission refusal, plugin shadowing, artifact rejection, freshness,
wrong publication identity, same-ID PATCH, worker failure and owned cleanup.

I recalculated all selected controller command-log sizes/SHA256 values and all
worker artifact hashes, checked nested receipt equality and every command suffix
against the trusted test-only plan. Controller identity
`f3525a8ca06c09da26620640c6ea24d0823d41771dc2b2c86f5d32603b17754a`
matches the reviewed asset bytes. Independent artifact parsing confirms 674 DB,
241 unit and 1,037 harness cases with zero failures/errors/skips. The receipts bind
the expected base/head/repository/PR, report dedicated volume-only mounts and
successful outer container/volume removal; the environment readback says Linux
ARM64 and confirms resource absence. No executable/controller changes occur from
the tested SHA to the reviewed result SHA.

The selected receipt explicitly says test_only=true. It demonstrates quality,
DB and lifecycle execution, not final independent-review validation or GitHub
publication. This PASS approves the reviewed implementation within its documented
trusted-code boundary. It does not assert production controller activation,
current-head check success, MERGED, hosted/x64 evidence, or product/release PASS.
Fresh admission and a full exact-current-head publication run remain required
operational steps after all reviews; prior receipts cannot be imported as success.
