# KL-036 GENERAL independent review

Reviewed implementation/result revision: `96ebb9e0e95211fc684273e7b69a49dc11e11e87`. Protected base: `af09be228fbc89d074b6e863c83e1fdda343d55b`. Recorded tested revision: `6a3f10ef424f41bb690d8835f952484b0ca4f87b`.

This review independently read the current index, packet, relevant Protocol sections 6.2–6.7/T5/T8 and DB sections 4.1–4.3/T5/T8, owner contracts, prerequisite result/integration records, committed diff, task result, source/tests and recovered evidence. No other reviewer conclusions were used. No DB lifecycle, installation, App/full-DB gate, commit, push or other-chat operation ran.

## Required correction GENERAL-001

The independent reaper treats reaping scan facts as stale observations, but does not provide equivalent handling for accounting scan facts. `mark_outstanding_unknown` commits a read of DISPATCH_INTENT reservation IDs/revisions (worker_reaper.py:98–107), then submits each MarkUnknown using that cached revision (111–115). A separately authenticated reliable SettleCall is permitted directly from DISPATCH_INTENT by the existing ledger owner and can commit between that read and MarkUnknown.

Concrete valid schedule: (1) accounting scan reads reservation R at DISPATCH_INTENT/revision 1 on an expired root; (2) a reliable SettleCall with expected_transition=DISPATCH_INTENT and expected_revision=1 commits R as SETTLED/revision 2 through the existing owner; (3) scanned MarkUnknown locks the current R, and `prepare_ledger_change` raises GuardRequired("ledger expected revision is stale") at transactions.py:5025–5026. The owner correctly rolls back; however, this exception escapes the loop at worker_reaper.py:135. No run-level continuation/restart path exists in the new implementation. The bounded independently supervised reaper therefore ends because of ordinary settlement concurrency, and remaining candidates receive no subsequent scans. This is a static reachability finding; this review did not claim a newly executed DB reproduction.

`test_unknown_call_preserves_budget` sequentially marks unknown and then settles late. It does not place settlement between accounting discovery and mutation, nor prove the independently running reaper continues after such a rejection. Existing passing evidence cannot close this gap.

Required correction: handle only confirmed obsolete accounting observations as no-effect contention and continue bounded cleanup, preserving denial on authentication/integrity/infrastructure failures and retaining the existing ledger owner/transaction guards. Count only successful or acknowledged historical cleanup outcomes. Add a distinct-process migrated PostgreSQL interleaving using actual reliable SettleCall after discovery/before MarkUnknown, prove complete settlement/occupation history remains intact, and prove the same reaper process continues to close a subsequent expired intent. No frozen-spec change is needed.

## Verified evidence and scope

All 16 exact required check records were independently decoded from regular Git blobs at the reviewed SHA, checking stored/raw SHA256 and sizes, single gzip membership, commands, tested SHA and zero exits. Collection/started/setup/call/teardown/JUnit identities and counts agree: 1492 harness regressions, 249 unit regressions, 2 task unit cases, 7 task DB cases, and each standalone selector has one positive case. Executable source/tests/contracts/launcher are unchanged from the tested revision. The five prerequisite integration merge commits are ancestors of the protected base, and their actual result statuses are PASS.

The final DB raw record contains 18 child-ready events, 10 PostgreSQL blocker witnesses, 44 complete no-effect comparisons, 10 complete rollback comparisons, actual worker PID termination (-15), independent reaper/admission PIDs, actual T6 success preservation and identical before/after physical inventories with joined child exits. New targets use typed guarded owners, distinct frozen S27/S29 terminal meanings and server clock after locks; success remains T6-owned. Legacy synthetic compatibility is separate. No code/grant/migration/enum/production/shadow authority expansion appears in the diff.

All 187 compact envelopes across retained runs have valid stored/raw hashes and available same-revision payloads; 175 distinct payloads, no orphan gzip files and 11,800,511 added evidence bytes. Retained failed/superseded runs are not eligible final PASS evidence. Credentials exposed in an early failure remain declared local quarantine, with committed sanitized diagnostics explicitly ineligible as lossless originals.

These observations establish recorded-check integrity, not complete DoD in the presence of GENERAL-001. Product requirements remain empty/NOT_RUN and the result remains UNMERGED. The coordinator owns later installed-App/full-DB and merge admission.
