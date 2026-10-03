# HG-048 controller compatibility

The developer entrypoint uses xdist; the installed gate_pytest.py, db_ci_pytest.py,
local_gate.py, db_policy.py and workflows retain their existing serial behavior.
No controller installation, admission, credential, branch protection or live setting
was changed. The candidate validate_harness.py adds only the exact HG-048 allowed
paths; this file is a pinned controller asset. An authorized administrator must
independently review the final source and update the installed pinned validator
(and HG-047 evidence decoder if integrated) through its existing installation
contract before exact-head admission. Existing pins must not be bypassed.

A fresh independent GENERAL review and the dedicated App-bound local-db-gate with
full isolated PostgreSQL regression remain merge prerequisites. The developer
parallel evidence here cannot substitute for either. No live DB was run here.
If PR 91 merges first, retain its optimized Git read path, rebase/retest this change,
then obtain a fresh SHA-bound review. Do not reuse current measurements or stale
controller receipts as tests of a different implementation SHA.
