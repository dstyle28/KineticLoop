# Raw review diff preservation

The retained PROTOCOL-r3 raw complete-diff.patch contains ordinary unified-diff
context lines consisting of one space. The broad 0ce071a diff check flags those
intentional raw bytes; its FAIL capture is retained and is not selected acceptance
evidence. The source_diff check covers the entire protected-base diff except the
own HG044 review-record directory. Application/harness code, tests, contracts,
plan/index/manifest and own governance/evidence files remain checked.

Review captures retain their original bytes and hashes. Review schema, normalized
paths, Git type/provenance, exact reviewed SHA and own REVIEW_RECORD_ONLY suffix
still apply. The final result selects source_diff and fresh standard execution
checks; no raw failed report is converted into PASS. The actual patch does not
enter runtime or command-owner paths.
