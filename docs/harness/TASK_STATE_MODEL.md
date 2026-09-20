# Task / Requirement / Integration State Model

Do not collapse independent state axes.

```text
TaskDefinition: DRAFT → READY → IN_PROGRESS → REVIEW → DONE
TaskCheck:      NOT_RUN → PASS | FAIL
Requirement:    NOT_RUN → PASS | FAIL | APPROVED_NA
Integration:    UNMERGED → MERGED
Review:         NOT_RUN → PASS | CHANGES_REQUIRED | STALE
```

`DONE` means the task's own contract and checks are satisfied and its result is integrated. It does **not** mean every product requirement it covers is PASS.

READY is derived from: merged hard dependencies, satisfied admission gates, packet refinement complete, no resource conflict, and required environment availability. There is no manually maintained READY list.
