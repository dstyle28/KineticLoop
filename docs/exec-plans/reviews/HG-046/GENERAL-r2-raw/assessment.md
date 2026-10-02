# HG-046 GENERAL r2

Reviewed protected base 26906bd7f4444914c228e98377f2b164fee0dd5d through exact head 5182feb0ad33319336efd913f63bf8c01c74b6a7. Status: CHANGES_REQUIRED.

Independent inspection verified 68 exact declared paths, allowed governance scope, unchanged frozen/task/schema/requirement authorities, derived index/manifest hashes, and an exclusively allowed tested-to-reviewed suffix. All seven selected committed envelopes and deterministic payloads decode at the same reviewed revision, bind tested source 58de0f7dfbf39947f2c2c1852cc927823e79b4c3 and exact commands/zero exits. Raw outputs establish 950 harness, 241 unit and 59 compact passes. The prospective audit counts 52 changed evidence/review blobs totaling 45,135 bytes with no budget errors. Source is byte-identical from tested to reviewed outside allowed governance/evidence bookkeeping.

The r1 filename bypass is corrected for ordinary JSON content and the M3 JUnit/collection/collection-stdout command gaps are corrected. This review separately found the remaining source-level Unicode classifier gap after the concurrent SECURITY review reported its isolated reproduction: the ASCII byte prefilter returns None before json.loads for UTF-16/32 JSON, and read accepts None as plain evidence. UTF-16/32 storage fields therefore avoid payload/integrity/metadata validation. GENERAL independently inspected the implicated code; it did not repeat SECURITY's probe. This violates the fail-closed missing-payload rule and blocks approval.

The bounded test run selects the entire compact suite, the two exact new CI budget/provenance cases, and only the nine new compact M3 semantic-source cases. All 70 selected cases passed (exit zero); the exact command/output is captured once in focused.json. No full harness, broad historical selector, normal check-harness, runtime/DB action or external message was executed.

The first independent verification script asserted an incorrect authority-output presentation (tasks/results instead of tasks/active). Its failed output is retained in verification.json; correcting that reviewer assertion produced verification-corrected.json with exit zero. This was a reviewer probe error, not an implementation failure.

Hosted CI, refreshed protected base, and the final selected gate remain coordinator obligations; this review asserts no merge, release/product PASS, production activation, executable shadow or historical proof.
