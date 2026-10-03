# HG-047 PROTOCOL review, round 4

Verdict: PASS for exact reviewed implementation/result SHA
`b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91`, against protected merged base
`d08927706a01a397dac2c78ca4aec7e9918a389c`. Zero BLOCKER,
REQUIRED_FOLLOWUP or NONBLOCKING findings in this protocol review. This does not
satisfy the pending final full DB/App gate or authorize merge by itself.

## Authority and scope

Read AGENTS.md, CURRENT_DOCUMENT_INDEX.json, HG-047 governance YAML and SCOPE,
pr-merge-reviewer and protocol-guardian skills, frozen Protocol invariants,
SafetyRegistry/S01 lock order and T1–T8 table, frozen DB S49–S51 and command
ownership, M3_CLOSURE_CONTRACT, EVIDENCE_STORAGE_POLICY and the review/result/
governance/merge contracts. Inspected the complete implementation/test/contract
diff; retained evidence and repair claims were checked using exact committed Git
blobs, independent of concurrent dirty review files.

No production runtime, migration, DB test, task packet, task result, integration,
milestone instance, requirement authority, provider adapter, workflow or classifier
changed relative to the protected base. Frozen files and FROZEN_BASELINE remain
byte-identical and their bound hashes verify. There is no changed frozen table,
transaction guard or command owner. INV-01–18, Evidence Admission, authorization,
SafetyRegistry → S01 lock order, T1–T8 boundaries, TEST isolation, non-executable
shadow, and provider evidence-only authority retain their previous meaning.
No SPEC_CHANGE_REQUIRED condition was found.

## Merge repair and evidence identity

The independent `verify.py` reads exact regular Git blobs. Its successful output
is `verification.json`; it does not use the candidate decoder to prove raw logs.
It confirms all 116 nonshared HG048 files equal the merged parent and all 211
retained HG047 files equal d67ed45. The entire current validator, including its
tail, equals the old HG047 blob with exactly the HG048 allowlist inserted. The
entire README equals the complete composition of both parent sections. The
intermediate a878a70 truncation is not the reviewed or tested implementation.
All current-index and manifest hashes and sizes validate.

The selected source is `7b35dc5dd7c488b60651175574e37b5d9389d335`. Every individual
commit in its linear suffix to the reviewed SHA changes only HG047 governance or
own evidence. All implementation and test files used by focused review execution
match their exact reviewed Git blobs.

All 28 round4 compact captures were independently decompressed with bounded
single-member zlib, exact stored/raw SHA256 and lengths, same-revision regular
blob provenance, source ancestry, and tested SHA. The selected governance checks
bind their exact commands and zero exit codes. The worker receipt binds every
raw execution artifact and check argv/hash/size. Linux ARM64 logs and JUnit show
1324 harness and 241 unit cases, with zero failures/errors/skips. All 1324 unique
harness collection node IDs match the observer in order and match JUnit identities
as a multiset, preserving complete parameter text and XML escaping. The observer
records session.items; this review does not call those records phase events.

The receipt's development.json digest refers to initial RUNNING metadata.
Removing precisely the four final fields and restoring RUNNING in the separately
retained final JSON reconstructs the initial bytes exactly, including formatting,
and matches the receipt SHA256. Both raw versions and the packaging explanation
remain retained. This is explicit metadata reconstruction, not a fresh execution
claim. The receipt records successful removal of its own container and volume.
All 11 controller asset hashes match the recorded reviewed b737094 release.
The candidate source authority check remains distinct from that older installed
validator's check. The prior E2BIG execution still contains 1304 passes and two
errors and remains a failure.

## Protocol evidence semantics and focused validation

M3 constants, the 17 required identities, exact exit/check mappings, regression
commands, pytest count oracle, dependency order, frozen validation, layer status
rules and complete closure function are AST-identical to base except the bounded
validation-session decorator. The 31-row boundary ledger still admits only 19
planned executable PASS rows and retains 12 NOT_RUN rows. I01–I09 DC remains
separate from I04 WF NOT_RUN; PU equality cannot become DC equality, and DC cannot
become WF/E2E. KL074 is support; KL080 remains corrective source evidence. Product
claims remain empty; shadow usability, R04 E2E and historical reproducibility
retain their existing non-PASS semantics. No M3 instance or release claim is added.

The compact decoder validates envelopes before using decoded raw bytes, rejects
reserved storage metadata a second time after decompression, and never recursively
decodes nested storage. Thus P01's fake `1 passed` in an inner envelope timestamp
cannot supply a raw PASS oracle, even with a missing/corrupt payload, wrong SHA,
wrong command/exit, malformed encoding or list/object wrapper. M3 logs, JUnit,
collection JSON and raw collection output keep exact command/tested/exit bindings
and their original failure, skip, count, selector and identity checks.

The cache stores only successful immutable full-SHA availability proofs, keyed by
repository, path, revision, tested SHA, command and exit expectation, in one bounded
validation operation. It retains neither mutable HEAD/working-tree verdicts nor
failed reads and never caches M3 raw semantic oracle output.

`focused.log` and `focused.xml` record 47 selected passing regressions across the
compact decoder/cache tests and full M3 execution evidence oracle, including all
nine compact semantic-source mutations and all seven nested-storage variants.
The selection intentionally excludes unrelated harness tests. Its 296 deselected
cases are not claimed as executed; complete Linux suite evidence was independently
audited above. Temporary Git fixtures are isolated in a unique review directory.
No Docker, App, installation, configuration, admission or remote mutation was run
by this reviewer.

`budget.json` independently runs the committed candidate's prospective audit:
257 changed evidence/review blobs, 3,733,970 stored bytes, zero errors. Historical
untouched evidence is preserved. Ordinary duplicate-key Unicode JSON (prior G-01)
remains the previously documented separate nonblocking concern; it does not reopen
P01 or substitute for raw M3 proof.

## Remaining gates

Full DB and final App publication remain NOT_RUN. Root must finish all fresh
reviews, append review records through the exact own-task REVIEW_RECORD_ONLY
suffix, install the independently reviewed controller/validator/decoder release
and full pins, obtain exact final-head/controller admission, and run the mandatory
final full DB/App and required hosted gates. Those are existing merge prerequisites,
not waived by this PROTOCOL PASS. New implementation/result changes require fresh
review. This review grants no requirement, M3, product/release, production activation
or executable-shadow PASS.
