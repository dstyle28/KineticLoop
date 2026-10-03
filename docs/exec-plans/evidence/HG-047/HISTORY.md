# Compact-evidence integration history

PR 91 originally used the unmerged HG-046 identity. The independently merged
local CI concern now owns HG-046. Only this compact concern is prospectively
renamed to harness-governance-v0.1/HG-047.

Original compact proof remains byte-for-byte in Git at
`ac63ac53b1fb222ef0d816c171b2041c48d0d722`,
under `docs/exec-plans/evidence/HG-046/`,
`docs/exec-plans/reviews/HG-046/`, and
`docs/exec-plans/governance/HG-046.yaml`. The final original implementation was
`9f2f38fe69f772d1564f0fa5eee2441da038aef1`, with result commit `02d95c1`.
Use `git show <original-sha>:<original-path>` to inspect those original blobs.
Their envelopes must be read at their original revision and original owner paths;
they are not rewritten, relocated, or rebound to the integrated revision.

Those runs and reviews are historical and stale for HG-047. They establish no
HG-047 task, review, requirement, release, or merge PASS. New integrated checks
and fresh independent reviews are required. Removal of the unmerged compact
paths from the current tree before integration prevents any overwrite of the
merged CI HG-046 evidence; it is not a migration of merged historical artifacts.
