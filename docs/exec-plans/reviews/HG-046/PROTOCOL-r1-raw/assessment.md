# HG-046 independent PROTOCOL assessment

Reviewed implementation/result head: `5ae6b31ac4c4639fbfe2fd7ca3df029abdfae323`.
Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Task identity: `harness-governance-v0.1/HG-046`.

The reviewer independently read AGENTS.md, the indexed current authorities, the governance record, pr-merge-reviewer and protocol-guardian skills, and the current evidence-storage, thread-result, thread-review, governance, merge and M3 contracts. The implementation diff and relevant source/tests were inspected directly.

Frozen invariant IDs, transaction boundaries and tables affected: **NONE**. No runtime, frozen Protocol/DB, FROZEN_BASELINE, active task packet, backlog, schema, requirement status, activation or executable-shadow path changed. The SHA-bound provenance check verifies both frozen files against their pinned hashes and protected-base bytes, and verifies the frozen baseline is unchanged. No frozen semantic change or SPEC_CHANGE_REQUIRED is needed.

The ordinary `.json` decoder checks envelope/payload regular blobs at the same fixed revision, stored and raw bounds/hashes, tested ancestry, exact supplied command/tested/exit metadata, and one complete gzip member. The task-tested suffix remains restricted to own record/new evidence; ordinary review references bind the reviewed SHA, and absent own review-created references require the proven linear own REVIEW_RECORD_ONLY suffix. A later same-path repair cannot supply an ordinary reference. Seven committed task-check envelopes decoded with exact tested/command/zero-exit binding. These facts are verified in `provenance.json`.

M3 retains its exact task/check/oracle set, frozen protection, deferred NOT_RUN layers, empty product PASS claims, false production/shadow activation, positive raw executed counts, JUnit failure/skip/count/name checks, exact collection commands/nodeids/selector contributions, and exact tested/result/review/integration provenance. No summaries or test-count metadata should substitute for raw execution.

A blocking exception violates that final rule: `compact_evidence.read` recognizes envelopes only for `.json` references, while `evidence_exists` bypasses decoding for other extensions. A renamed manifest can therefore be accepted as a raw regular log without its payload, and the budget also treats it as plain output. M3's count reader then scans the envelope's metadata. Recognize compact signatures independent of extension or reject such renamed records at every availability/read/budget path, with negative regressions for missing/tampered payloads and metadata-only execution counts.

Ancillary JUnit/collection envelope commands are not currently compared with their expected generation commands. Decoded collection command/selectors and case correspondence still enforce the current M3 contract; stricter ancillary envelope attribution is useful hardening, but is not the basis of this blocking finding.

Review-created evidence is exclusively under this review's child directory. Compact envelopes bind their executions to the reviewed head; the coordinator must commit them only through the own linear REVIEW_RECORD_ONLY suffix. These fixtures and review checks create no product/release PASS, M3 closure, integration or merge claim. The first reproduction launcher failed because its script had not yet been saved; that unsuccessful attempted execution is retained separately in `reproduction.json` and does not supply the finding's oracle.

The broader selected compact/provenance/M3/review/budget pytest execution was interrupted on coordinator instruction while historical synthetic replay remained expensive. The subprocess wrapper exited 130 (KeyboardInterrupt); it did not return or capture the child pytest output, so this review claims no PASS for that selected run. The follow-on M3 alias fixture was also stopped; the completed first fixture demonstrates availability and budget acceptance, while its full M3 result correctly rejected the rename as a non-addition suffix. The blocker rests on that completed availability/budget reproduction and direct source inspection, independently corroborated by the other reviewers.
