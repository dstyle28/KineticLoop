# Context Packet Specification

Every task packet contains: identity, goal, non-goals, dependencies, entry conditions, canonical references, invariant/transaction/table scope, expected write scope, deliverables, exact acceptance evidence, standard commands, and completion contract.

## Progressive disclosure
The packet links to documents instead of copying them. The implementation agent opens a reference only when the task needs that section. Frozen authority must be referenced by stable document ID/filename and section, not paraphrased from another chat.

## Forbidden context dependencies
- prior chat history;
- uncommitted decisions from another worktree;
- screenshots/log snippets that are not stored as evidence;
- “the other agent said” claims;
- a full Master Spec copied into every prompt.
