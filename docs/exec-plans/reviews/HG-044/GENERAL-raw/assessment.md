# GENERAL review at 351f0eda41ad492e66115f9ea1e41e3e0f9abf3d

CHANGES_REQUIRED. The fresh integrated regression content oracle fails to require
coverage of every selector in a multi-selector command. `m3_execution_evidence_errors`
checks that each collected node matches some selector, then compares collection to
JUnit; it never requires each selector to have a collected/executed case. The
committed synthetic positive fixture itself supplies only the first selector for
both migrations plus transaction interfaces and unit plus DB shadow isolation.
The independently created complete Git fixture passes the content validator with
both second selectors absent. This reproduces past freshness, raw Git hash,
collection-count, positive execution-count and JUnit equality guards. Require each
selector to have collected/executed cases, expand the valid fixture to cover all
selectors, and add correctly hashed omitted-selector negatives after freshness.

Lower-severity type hardening: execution exit code 0.0 is accepted because Python
compares it equal to zero and the guard rejects only bool. The contract says integer
zero, and collection uses the same comparison. Use an exact integer type guard.
This finding does not claim a nonzero exit was accepted.

The committed evidence audit independently verified the exact protected-base diff,
68 declared scoped paths, all 27 authority hashes, all 161 manifest hashes/byte
counts, every retained raw capture (42), selected final evidence at e748b37, legal
result/evidence-only suffix, 52 named check-contract digests, preserved M1/M2 schemas
and all unchanged existing validator functions apart from the intended orchestration
and scope additions. M1/M2 validate; all 32 recursively required integration chains
are valid/reachable and dependencies precede consumers' base and tested revisions.
KL028/KL029 remain prospective absent integrations; no actual M3 instance exists.
Selected final logs report 79 focused, 869 harness and 232 unit tests, lint/type/
validation/diff PASS. Development rounds are explicitly superseded.

Only own GENERAL review artifacts were written. No local PostgreSQL lifecycle,
foreign namespace, network, implementation write, commit, push, PR or app message
was performed. Fresh hosted DB CI remains a separate pre-merge requirement. The
review does not imply product/release PASS or MERGED.
