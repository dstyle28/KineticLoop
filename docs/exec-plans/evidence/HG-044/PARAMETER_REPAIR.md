# Genuine pytest parameter formats

Actual collection of current harness and unit suites has 1107 cases, including
25 parameter IDs containing `::` and three with summary-looking skip/error text.
The 19dc5a4 review round independently confirms valid required full-harness
evidence is falsely rejected. Preserve those CHANGES_REQUIRED artifacts.

Normalize the address before the first `[` and retain the complete parameter
suffix as pytest JUnit does. Classify collection dispositions only outside actual
node record lines. Four positive cases generate real pytest collection/JUnit
formats in isolated temp directories, then exercise the synthetic committed Git
chain with correct raw hashes and freshness. A separate appended skip-summary
negative preserves rejection of real skipped collection dispositions.
No synthetic data is project completion evidence, and no actual M3 record exists.
