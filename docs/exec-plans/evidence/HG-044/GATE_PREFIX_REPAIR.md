# HG-044 exact-head gate repair

The normal PR gate at ec0713f614359b502045d09edea59e7c85f3994b failed with a TypeError at the new HG044 plan-prefix guard. Normal governance PRs intentionally leave optional governance_target unset; review-only PRs set it to the reviewed revision. Concatenating the optional target with the plan path prevented the normal gate from running. The failure and exact traceback are retained without relabelling.

The guard now compares the explicit protected-base and committed reviewed revisions in both modes. Two isolated real-Git tests accept the valid appended prefix and reject an edited protected prefix while proving ambient working-tree content is not used. Existing frozen/legacy functions remain unchanged. Fresh selected checks and four independent reviews must bind the repair; r5 reviews are retained historically under rounds/027bc23 and do not approve the new source.
