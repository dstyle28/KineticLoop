# HG-047 P-01 correction self-review

Source `536c9b7b7c5bfa9b36a0b38e513bce34ed6eb31d` against protected base `391c9198fa8ec647e377a0572700bc7568468c85`.
This is author self-review; independent review, M3, product and release PASS are separate.

Original round1 reviews of `47de76d206df89124ffe41c59b0b983af4defc97` remain in
`0fd0f3d34dbf6c95d8446b4376f6ed9d00512d76`. At `b30a9c6`, the original reviewers
removed only the decoder source file from their raw evidence references and
appended bookkeeping to their reports; bound SHA, verdicts and finding remain.
The failed `166bf3e` unit run is preserved under `development-166bf3e/`.
The failed `b30a9c6` authority run is also preserved: it rejected the pending
record's selected FAIL entry. Failed runs were removed from the pending selected
list while retaining BLOCKED status and exact failure history; no gate changed.
There was no source-reference bypass or classifier relaxation. The PROTOCOL BLOCKER
P-01 identified valid outer gzip storage returning invalid inner storage JSON as
raw stdout. Metadata could then supply a pytest PASS phrase without raw execution.

After bounded single-member decompression and exact raw length/hash checks, the
decoder now applies the existing reserved-content classifier to decoded bytes.
It rejects reserved nested/wrapped/malformed objects before availability, budget
or M3 semantic callers can accept them. It never recursively decompresses nested
envelopes. Actual ordinary text, binary and UTF8/16/32 JSON remain lossless.
The capture writer uses this same read check and cleans up rejected new artifacts.

Thirty-five new regressions cover direct/compressed rejection parity for missing,
corrupt, wrong command/tested/exit and wrapped/truncated metadata; valid nested
objects and capture cleanup; positive ordinary encoded JSON; and complete M3
execution validation with seven attacker variants. The M3 assertions require the
specific decoded-storage error while retaining normal JUnit/collection records.
These are synthetic security regressions, not actual M3 execution proof.

The required full harness, unit, lint, typecheck, authority, protected-scope,
diff and bounded benchmark commands passed on this exact source. Selected raw
logs are captured in deterministic gzip under `docs/exec-plans/evidence/HG-047/round2-536c9b7/` with full commands,
exit codes, bindings and monotonic durations. No older check or review is relabeled.

No validator policy, controller, workflow, classifier, runtime, frozen authority,
requirement semantics or merged HG045/HG046 artifact changed in this correction.
Existing index/manifest entries were recomputed and already match current bytes.
Fresh GENERAL/PROTOCOL/SECURITY_DATA_BOUNDARY reviews and the separately installed,
pinned controller release followed by the final-head App/full DB gate remain
mandatory. No live installation, signing key or admission was changed.
