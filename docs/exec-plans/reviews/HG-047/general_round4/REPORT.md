# HG-047 round-four independent GENERAL review

Reviewed result SHA: `b71d2d63f8bc27ab0e905b0be8a0cea5f0122a91`.
Protected base: `d08927706a01a397dac2c78ca4aec7e9918a389c`.
Tested source: `7b35dc5dd7c488b60651175574e37b5d9389d335`.
The provisional `69cf369` candidate was superseded before review execution; no review PASS binds it.

GENERAL verdict: **PASS**, with one NONBLOCKING compatibility finding G-01. This is an implementation review, not a merge, App-gate, full database, product requirement, M3 or release PASS. The final reviewed controller installation, exact admission and mandatory root-run App/full DB gate remain required. No Docker, App, configuration, signing, admission, production, commit or push operation was performed by this reviewer.

## Independent scope and integration verification

Read AGENTS, current authority index, the reviewer skill, HG-047 governance packet, own SCOPE, evidence storage policy and applicable governance/result/review/merge/M3 contracts. Inspected the complete base-to-result changed-path inventory, all implementation/test/contract/derived-metadata changes and the binary/raw evidence through independent retrieval. The change has 276 declared paths, all matching the HG-047 allowlist; the governance schema and source-to-result bookkeeping suffix validate.

Verified the complete final validator equals the entire pre-integration HG-047 validator from `d67ed45` with precisely the HG-048 allowlist block inserted. This checks all bytes, including the tail. Verified the final README equals the complete protected-base README plus exactly the compact-policy paragraph. All 116 nonshared HG-048 changed blobs are byte-identical to the merged protected base. All 197 pre-existing HG-047 evidence/review blobs (excluding the explicitly revised SCOPE/audit helper) are unchanged; the implementation is independently inspected rather than treated as historical proof.

Verified all 27 current-index entries and all 172 delivery-manifest entries against actual Git blob hashes and lengths. Frozen authorities, frozen baseline, current requirement set, runtime, migrations, DB tests, workflows and DB/controller policy dependencies remain unchanged relative to the base. The minimal local controller additions pin the decoder and copy the installed decoder with the trusted validator. Existing plus added controller tests cover missing/changed/symlink pins and candidate-import isolation.

The intermediate `a878a70` validator is only 1,513 lines; `7b35dc5` restores the complete 4,744-line file. The exact parent reconstruction above confirms no remaining truncation. The broken intermediate is not selected execution evidence. The source bootstrap is BLOCKED and the new result selects only the fresh repaired-source checks. The failed resolver/helper attempts are documented in the self-review and Git history; this review does not claim independently executing those old helpers or possessing an unrecorded failure transcript.

## Raw evidence audit

The verification script independently retrieves committed blobs, checks gzip stored/raw byte counts and SHA256 values with standard gzip/hashlib, then cross-checks the candidate decoder. It audits all compact HG-047 evidence, including historical nonzero/interrupted artifacts, without treating envelope navigation counters as test oracles.

Round four has 28 compact artifacts, totaling 10,078,737 recovered bytes. The author's `selected_raw_bytes` metric covers selected check references, not this complete 28-artifact total. Current PR evidence/reviews before this reviewer append total 3,733,970 stored bytes across 257 blobs and pass the prospective budget. No full diff or duplicate bulk output is appended by this review.

Independent XML parsing confirms 1,324 unique harness cases and 241 unique unit cases, with zero failures, errors or skips. The complete 1,324 host-collected IDs equal the trusted observer's ordered IDs and, after pytest's defined JUnit conversion, exactly equal the JUnit multiset. The observer is collection/session-items evidence; case completion is corroborated by full JUnit identities, not invented phase events.

All 11 worker receipt artifact hashes, seven worker check log hashes/lengths/exits, six host check hashes/lengths/exits and 11 installed asset hashes match the recorded exact b737094 release. Selected command strings, tested SHA and zero exits agree with governance evidence wrappers. The driver uses the actual repaired source, isolated UUID resources, `full_db=False` and `test_only=True`; no App object/publication is claimed. Cleanup is verified from the retained complete receipt and driver, not from a new Docker operation.

The initial receipt hashes metadata while status is RUNNING. Independently removing only documented terminal fields from final metadata and restoring RUNNING produces byte-for-byte the recovered initial document, including its original receipt SHA256. The final metadata is separately retained. The first failed packager source and explanatory note are present; that metadata mismatch did not rewrite execution bytes or produce selected PASS.

Historical failure evidence remains historical: the interrupted 609-case run, 240-pass/one-failure unit run, failed authority run and failed old App run were not promoted to current PASS. The old `8a78241` JUnit independently contains 1,306 cases and two errors; current round-four JUnit contains none. Regex-derived envelope counters inside XML/collection parameter text are navigation metadata and can contain apparent failure words; the XML and raw session summaries, not those counters, determine execution outcomes.

## Focused independent verification

Final independent verification: **18 HG-048 runner tests passed** in the isolated locked environment; **two new validator regressions passed**; authority returned **HARNESS_CHECK_PASS tasks=77 active=74**. The original targeted run remains **FAIL (7 failed, 57 passed)** because the older environment lacked declared xdist/execnet; its 39 provenance and seven nested-M3 cases completed successfully. The overbroad run remains **INTERRUPTED (373 completed passes; exec exit 130)**. Exact commands, statuses and raw log/JUnit hashes are retained in `checks.json`.

An exploratory run accidentally selected the entire unchanged M3 history module. At the root reviewer's direction it was interrupted: the exec session returned 130, the log records KeyboardInterrupt and 373 completed passes in 1021.53 seconds. It is INTERRUPTED, never a suite PASS. The retained JUnit contains 373 named completed cases (228 compact, 44 controller, 101 M3) plus one unnamed interruption artifact; its suite counter is 373. The 101 M3 cases include all nine new compact semantic-source cases. No omitted historical M3 case is relabeled PASS.

A separate targeted completion run covers only the missing 39 review-provenance cases, 18 HG-048 runner cases and seven nested-storage M3 cases. Separate tests exercise the two new validator merge-gate regressions. Fresh standalone authority passes at the fixed candidate. The complete independently audited Linux 1324-case execution supplies full-suite evidence; this review does not claim a completed full native suite or DB run.

`verify-attempt1.py` and `verification-attempt1.log` retain an initial reviewer-script assertion failure: it inserted the HG-048 block at the start of the function instead of its actual location after HG-047. Inspection of the exact diff corrected that expected construction. It was a failed review probe, not a product test failure or PASS. `verify.py` subsequently confirms complete-file equality at the correct insertion point.

## G-01 — NONBLOCKING

At `tools/harness/compact_evidence.py:129`, `storage_pairs` calls `unique` before determining whether an object has reserved storage identity. An ordinary nonreserved duplicate-key JSON object with literal text is plain; changing an ordinary value to a Unicode escape makes the same structure raise `evidence-duplicate-key`. The fresh probe is recorded in `verification.json`; no previous review waiver is assumed.

This is a real lossless compatibility limitation for ordinary duplicate-key output. It fails closed, does not alter accepted bytes or provide a PASS/provenance bypass, and does not affect any selected or historical evidence retrieved in this review. Accordingly it is NONBLOCKING for this storage concern. A prospective correction should identify reserved storage objects before enforcing storage-specific duplicate rejection, preserve nonreserved raw bytes, and add literal/escaped parity tests. Reserved envelopes must continue rejecting duplicates.

No BLOCKER or REQUIRED_FOLLOWUP implementation finding was identified. The outstanding mandatory final App/full DB gate is an explicit integration prerequisite; this review makes no final merge recommendation before it passes.

## Pre-review hosted merge-gate failure assessment

The root supplied a completed failing hosted merge-gate transcript while canonical reviews still selected round three. The gate derives `governance_reviewed_head` from GENERAL, then compares the declared changed-path set against base-to-reviewed, reads result/evidence at that reviewed SHA, validates tested-to-reviewed and reviewed-to-HEAD suffixes, and resolves review evidence at those bindings. The stale GENERAL SHA therefore affects result/evidence binding and path-set comparison, not just error labels mentioning staleness. This review independently verified the fixed candidate's exact 276-path declaration, tested suffix, schema, all selected compact command bindings, and authority. Fresh b71-bound records require a strictly linear task-owned review-only append. The root must rerun the actual complete final-suffix gate; this assessment does not predict or record that future run as PASS. The supplied hosted failure transcript remains root-owned evidence and is not copied into this review directory.

The seven targeted failures were independently diagnosed from raw child output (`unrecognized arguments: -n 0`) and missing distributions in the older shared hg044 environment. A unique temporary venv installs only pytest/xdist and their dependencies at exact committed-lock versions and wheel hashes with `--require-hashes`. All 18 HG048 runner cases then passed without source changes. `targeted-log.json`/`targeted-xml.json` preserve every original failure; `parallel.log`/`parallel.xml` hold the successful rerun. `locked-review-requirements.txt` and `dependency-install.log` preserve dependency provenance. The shared environment was not modified.

The failed targeted-run log and JUnit contain literal trailing whitespace. Before review persistence they were captured losslessly into compact envelopes (`targeted-log.json`, `targeted-xml.json`) and content-addressed gzip payloads. Raw SHA256 and byte counts match the untouched originals in /private/tmp, with exit 1 and the original JUnit start timestamp. No raw bytes were stripped or rewritten and no test was rerun for this storage-only correction. `compact-conversion.json` records both exact roundtrips. The originally executed finalization script remains historical; this subsequent script records the storage conversion.
