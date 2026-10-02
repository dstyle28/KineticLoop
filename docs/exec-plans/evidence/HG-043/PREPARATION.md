# HG043 — review evidence provenance repair

Protected base: `1099d85bd4aa76ec8221700e55b4e77a84479126` (normally merged PR83).

Authorized scope: validator, focused provenance regressions, Thread Review and Harness
Governance provenance clarification, legitimate derived index/manifest updates, and
only HG043 governance/evidence/review artifacts. No task packet is refined. No root
schema change is necessary: the existing exact integration `review_record_commit`
provides the durable source binding. No application, DB, migration, CI, product,
release or frozen authority change. No official integration records are written.
HG042 and KL055 remain untouched.

The original HG042 preflight is copied byte for byte as historical failing evidence;
its KL027 merge was then hypothetical and is not relabeled in that source. replay.py
constructs ephemeral candidates from protected Git ancestry, independently verifies
normal merge parents, exact reviewed/review-record revisions and regular-file Git
entries, and replays both protected and repaired validators. KL075 reviewer logs
were committed in the suffix; the earlier characterization as uncommitted was wrong.
The replay uses actual PR83 merge for KL027. It does not claim product requirement
PASS or reclassify independent reviewer runs as task acceptance evidence.

Ordinary references resolve to regular Git blobs at the reviewed implementation SHA.
Only missing ordinary references under the exact same task's whole review-directory
component may resolve at the recorded review commit, and only after a strict ancestral,
linear, exclusively own-review suffix proof. That proves code/result/task evidence
immutability over every intervening commit, including changed-then-reverted edits.
Git object identities content-address the evidence; ambient HEAD and working-tree
existence do not supply it. The delayed post-merge scoped freshness rule and complete
Git-tree squash exception remain unchanged. Delayed reviews with unrelated chronology
cannot use the new evidence exception, though ordinary reviewed references still work.

Required checks: focused regressions, all harness tests, all unit tests, lint,
typecheck, full harness validation, protected-ancestry candidate replay, and diff
whitespace checks. The tested implementation commit precedes check evidence and the
PASS governance record. Fresh independent GENERAL, PROTOCOL, DB_CONCURRENCY reviews
bind the final implementation/governance/evidence revision; only HG043 review paths
may follow. All applicable final hosted CI must pass before ordinary merge.
