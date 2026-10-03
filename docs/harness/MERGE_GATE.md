# Merge Gate v0.3

A task PR may merge only when:

1. hard prerequisites are merged and conditional prerequisites required by current launch/release scope are satisfied;
2. the task packet is refined and its DoD is satisfied;
3. every `checks_required_for_this_task` item is explicitly matched by `check_id` and PASS on `tested_commit`; the base → tested → reviewed revision ancestry and result/new-evidence-only suffix are verified;
4. related requirement obligations are reported separately; NOT_RUN/SKIPPED are never promoted to PASS;
5. frozen authority impact has been checked and protected-baseline validation passes;
6. GENERAL independent review is PASS for the reviewed implementation revision;
7. all risk-triggered specialist reviews are PASS for the reviewed implementation revision;
8. the committed result artifact conforms to `THREAD_RESULT.schema.json` and semantic checks;
9. no unresolved resource/write-set collision exists;
10. generated docs/contracts are updated only when their current source of truth changed;
11. if HEAD is newer than a review's `reviewed_head_sha`, the suffix is mechanically proven to contain only REVIEW_RECORD_ONLY paths allowed by `THREAD_REVIEW_CONTRACT.md`.

Any implementation/configuration/migration/test/contract change after a reviewed SHA invalidates that review. Appending the prescribed review artifact does not invalidate the review when the review-record-only diff check passes.

Merge state is recorded separately from task PASS. A review PASS is not a merge fact, and a merged task does not imply any covered product requirement is PASS. An integration record is valid only when its result commit contains the same byte-identical result path and content reviewed at `reviewed_head_sha`; that result must be PASS and semantically valid.

An already-merged task may receive delayed required reviews and its integration
record in one Harness governance remediation. The reviews must bind the exact merge
tree, every task-required review type must PASS at that same revision, and the PR may
not change the task's implementation, result, evidence, packet, requirement state or
frozen authority.

Derived-hash bookkeeping is permitted for `CURRENT_DOCUMENT_INDEX.json` and `HARNESS_DOCUMENT_MANIFEST.json`: only checksums/byte counts of already-indexed, actually changed, task-authorized implementation files may refresh. No entry, path, identity, authority metadata or frozen hash may be changed under this allowance. The package manifest may refresh the current index checksum after an allowed refresh. The trusted Git baseline supplies the task write scope and frozen paths; a PR cannot authorize itself by editing its task definition.

Harness-definition changes use the separate `HARNESS_GOVERNANCE_CONTRACT.md` path. CI must derive exactly one task result or one governance record from the protected-base diff; mixing change types fails. Governance changes require a PASS committed record, exact file declaration, protected-base write allowlist, bound evidence, required independent reviews and an unchanged Frozen baseline. Required governance review types are the union of the protected-base and reviewed-head requirements for every changed task definition, so the PR cannot weaken its own review gate.

## Prospective local database execution

Full database execution may use the owned local Linux daemon specified in
`LOCAL_DB_CI.md`. Every PR requires the dedicated App-bound `local-db-gate`. Its trusted complete-diff
policy requires full DB for all changes except the narrow inert documentation/review
allowlist in `LOCAL_DB_CI.md`; evidence/configuration changes are not blanket exempt.
The result and independent review must bind the complete local manifest, raw logs,
collection/JUnit and outer cleanup envelope. This is not a GitHub-hosted claim.
Existing task-specific hosted requirements and KL-074 provenance remain unchanged.
