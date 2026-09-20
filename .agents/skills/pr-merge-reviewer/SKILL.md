---
name: pr-merge-reviewer
description: Perform a fresh-context independent review of a KineticLoop task PR against its packet, frozen authorities and acceptance evidence.
---
1. Do not rely on the implementation thread's reasoning; inspect the diff and evidence directly.
2. Read the task packet, then only relevant frozen references.
3. Check scope creep, command ownership, authority boundaries, idempotency, concurrency, test layer and failure behavior.
4. Verify required evidence actually ran and is tied to the diff/revision.
5. Classify findings as BLOCKER / REQUIRED_FOLLOWUP / NONBLOCKING.
6. Merge recommendation is allowed only with zero BLOCKER findings and satisfied DoD.
7. If review discovers a frozen-spec issue, request ADR/spec change rather than approving a local workaround.
