# HG-046 trusted controller execution

Selected implementation: c91d2635427a13a97a53fe4e52ec4655e1e7d866. Protected base: fc8a044ffa4d15a74ce5dc59298ae411f1f4009b.
The controller-c91d263 directory contains the complete test-only execution receipt,
raw command logs, copied JUnit/node identities, exact image/controller identities
and verified outer cleanup. This is actual local quality/full DB/lifecycle PASS;
`test_only: true` explicitly does not claim review-gate approval or publication.
Source bundles and all credentials/configuration/admission files are excluded.

112 focused boundary tests, full typecheck/lint and the scope/frozen/HG045 audit
are in checks-c91d263. The scope audit source is preserved byte-for-byte as
controller_scope_audit.py; its capture command named /private/tmp.

Development history is not selected PASS. The first attempt49fbc18 rejected a
stale live master before candidate execution. Master had integrated HG045 PR89;
HG046 merged that base and preserved all source-decision authorities. A merge
script dependency mistake briefly committed conflict markers to this draft branch;
they were corrected before any selected run.57f2581 failed startup because the
external copy did not preserve entrypoint execute mode. Its orphaned owned
container/volume were explicitly removed; controller cleanup was then repaired
for uncertain create/start outcomes and verified by failure tests.00df4ff failed
strict typing on two newly added test callbacks and correctly removed both owned
resources. The corrected c91d263 run is the only selected controller execution.

Original341333d/2f7c4f5 records and reviews predate mandatory enforcement and remain
historical development evidence. New independent reviews must bind the new result
revision. Dedicated App5169734 is installed only on repository1377771702 and master
requires local-db-gate from that App, with strict freshness and no bypass. The App
key is owner-only outside Git and workers. Authenticated installation scope was
verified. Final publication/activation will occur only after independent review
and another exact-current-head controller run; no previous JSON is imported as PASS.
