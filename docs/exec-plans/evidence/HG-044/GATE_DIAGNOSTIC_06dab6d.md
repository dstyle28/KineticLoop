# Unselected repaired-gate diagnostic

The normal PR gate executed the repaired plan-prefix guard at 06dab6dbb38221e7111c18811cb20b42b8cc2397 without the previous exception. The exact retained diagnostic returned only governance-review-stale-change errors for the source repair and git-worktree-not-clean because newly captured test reports were still uncommitted. These are expected pre-review failures, preserved unchanged and unselected. New selected test evidence, a committed result, four fresh SHA-bound reviews and a clean final exact-head gate remain required.
