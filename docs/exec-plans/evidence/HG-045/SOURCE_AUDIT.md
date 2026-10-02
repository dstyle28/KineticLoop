# Protected-base source-decision audit

Protected base: 26906bd7f4444914c228e98377f2b164fee0dd5d, normal HG044 PR88 merge.
This worktree was clean, detached at that base before creating the own codex branch.
The temporary handoff is planning input only; these findings were independently
reproduced against protected-base source and the frozen indexed authorities.

Protocol 3.2–3.3 defines ELIGIBLE / NOT_ELIGIBLE / UNRESOLVED. DB S13 confirms
this decision enum; DB S12 defines MATCHED / AMBIGUOUS / RETRACTED. Persistence
`_facts` copies physical S13 decision and S12 association_state directly to Fact.
The actual pure resolver instead requires ADMITTED and CONFIRMED; actual full T6
also filters S13 decision='ADMITTED'. Full resolution delegates to the same resolver.
`source_probe.py` and `source-probe-26906bd.json` execute both actual pure pipelines:
ADMITTED+CONFIRMED succeeds; ELIGIBLE+CONFIRMED, ADMITTED+MATCHED and
ELIGIBLE+MATCHED fail. Both malformed successes have rolling_minutes=40. This is
defect diagnosis, never KL080 or product PASS. Runtime/tests/fixtures remain unchanged.

S27 PlanningIntent ADMITTED is valid (Protocol 6.2 / DB S27). S36 derived aggregate
CONFIRMED is distinct from physical S12 and remains valid. TEST_ONLY is an explicit
isolated policy scope; Protocol purpose list is open ('at least'), not a closed enum.
No product-purpose remapping or missing specification is required by this correction.

The four older fixture files have six identified source literal corrections:
factsets S12 UNRESOLVED→AMBIGUOUS, ALL S13 DENIED→NOT_ELIGIBLE;
preparation actual-event S12 UNRESOLVED→AMBIGUOUS and TEST_ONLY S13
ADMITTED→ELIGIBLE; protocol_interleavings TEST_ONLY S13 ACCEPTED→ELIGIBLE;
transaction_interfaces OUTSIDE_ADMISSION EXECUTION S13 ADMITTED→ELIGIBLE.
No current assertion directly compares those source values, so the enforceable
content guard permits exactly those six edits with all other bytes unchanged.
Preserve uncertain S12 meaning and the existing action_scope/purpose. Names such as
seed_admitted_source, PlanningIntent ADMITTED and FACT_ACCEPTED are distinct.

The actual full T6 path calls _progress_sources → _verify_full_progress before its
later exact S13 freshness query. Invalid source values therefore deny at the earlier
reconstruction guard. KL080 must prove canonical end-to-end freshness reach, invalid
end-to-end earlier denial with complete zero effects, and a separate labeled real-PG
exact predicate support test. A narrowly extracted shared internal read helper is
feasible; no forged certificates or bypassed reconstruction are permitted.

All checks in the new KL080 packet are prospective NOT_RUN. No runtime implementation,
fixture changes, immutable-row changes, M3 closure, product PASS or release claim
is made by HG045. Frozen files/baseline and existing HG044 ledgers remain untouched.
Hevy/HealthKit stay mandatory and spreadsheet retirement remains unchanged.
