# Independent protocol review, round 3

Outcome: CHANGES_REQUIRED. Two independent valid-collection oracle blockers prevent
successful required full-harness regression evidence from validating. The checks
below still pass for their intended negative/synthetic cases; they cannot establish
that the new parser accepts the actual current full-harness collection.

Reviewed implementation/result: `19dc5a4f8edc8869873a76a4fe27b0280761d7c9`.
Protected base: `fa729ca4bcca0f2c2e7a2aa0601890d1356b8842`.
Selected implementation test revision: `0af358014182c957eec07763aaaf9181d3e2d0c1`.

Authority was resolved through the current document index. The review read AGENTS,
the governance result, Thread Review Contract v0.2, indexed M3 closure contract,
plan/task mapping and KL028 ledger, and the repository protocol-guardian and
pr-merge-reviewer skills. Relevant frozen authorities were Protocol invariants,
§§2.1a, 5.3a–5.5, 8, 11.2 and 12; DB §§4–5 and registry/replay ownership; and
Integration Spec §10 provider text/summary authority.

The complete base-to-reviewed diff is retained in complete-diff.patch. The only
modified existing validator functions are governance_allowed_patterns and validate.
Every other existing function, including M1/M2 closure, integration/result and
HG043 regular-blob review evidence provenance, is byte-identical. Original M1/M2
schema branches and existing definitions are semantically identical. The existing
plan prefix, all frozen files/baseline, runtime, migrations, CI, task packets,
backlog, traceability and product requirement status are unchanged. No actual
milestone closure is introduced.

The new M3 branch requires exact namespaced membership KL019–KL029 plus
KL075–KL079 (16), separate KL074 support retaining M1 membership, exact M2 evidence
and recursively validated historical M1, and valid MERGED integrations for every
transitive declared dependency. Both consumer base and tested commits must follow
each dependency merge. The independent real Git ancestry audit verifies 192 such
checks, including KL078→KL076 and KL079→KL077. Both KL028 and KL029 integration
records are absent at this revision; a merged code result alone cannot substitute.
Actual M3 closure remains unavailable.

All mapped named task contracts match pinned canonical digests and preserve their
commands and full oracles. Witnesses bind exact namespaced task/check, PASS,
tested SHA, result regular blob, raw regular blob, reviewed-head revision and
SHA256; path/type/reachability and ordinary integration/review semantics fail
closed. Historical task logs are never the fresh regression.

The integrated regression requires one tested revision containing every M3 merge,
its legal own-governance tested suffix, exact ordered commands/executions, integer
zero exit codes, hashed regular stdout/JUnit/collection/raw collection logs in the
closure governance directory, positive counts, exact unique collection/JUnit
agreement and contribution from every requested selector. The independent strict
exit probe rejects both false and 0.0 at the exit-code oracle. The previously
reported omitted-selector blocker has a dedicated each-selector guard and repaired
positive fixture generating a node for every selector. The targeted review run
rechecks both hash-correct omitted-file reproductions after a successful positive
freshness/provenance/JUnit precondition and requires missing-selector specifically.

The boundary validator compares the complete authoritative 31-row ledger,
including selectors/oracles/metadata/future owners, and promotes only 19 planned
executable obligations. The exact deferred 12 stay NOT_RUN: B04@DC full TEST
reauthorization, eight actual product E2E layers, B11/B12@PU pure commit-state
evaluator, and B14@WF worker/fault evidence. Mandatory B04 registry support is
not full reauthorization. I01–I09@DC retain named KL026 checks; I04@WF stays
NOT_RUN. PU equality is not PostgreSQL equality, DC is not WF/product E2E, and
original ingress/registration/T7 denial reach is preserved by pinned oracles and
the unmodified ledger. Shadow usability and R04@E2E remain NOT_RUN.

Schema constraints keep product requirement claims empty, production activation
and shadow execution false, and historical model evidence an independently
unreproduced UNVERIFIED_HISTORICAL_DECLARATION. Frozen hash checks remain required.
No T1–T8, Authorization, Evidence Admission, command ownership, registry→S01 lock
order or external-wait rule changes. Provider text remains evidence with no
command authority. This governance introduces no M3→M4 or KL029→KL045 cycle.

The selected final captures were read as regular Git blobs at the reviewed SHA.
All retained raw SHA256/byte counts match, every selected exit code is integer
zero, and their tested/base binding is exact: 83 focused, 873 harness, 234 unit,
lint, typecheck, harness validation and diff checks PASS. The tested-to-reviewed
suffix contains only own governance/evidence additions and is linear. Prior
failed/interrupted rounds are explicitly historical and unselected.

The review uses bounded pure/Git checks in its own temporary namespace, with
PYTHONDONTWRITEBYTECODE and explicit PYTHONPATH. It runs no local DB lifecycle,
foreign fixture namespace, runtime task execution or hosted CI. A protocol PASS
is an independent review fact only; the other three exact-SHA reviews, final merge
gate and applicable hosted CI remain coordinator requirements before any merge.

## Final valid-collection blockers

The bounded targeted run passed 21 cases (62 deliberately deselected) in 288.31s.
This revalidates the prior omitted-selector repair, strict input/oracle negatives,
regular closure-source guards and synthetic positive chain. It is review evidence,
not a replacement for selected implementation tests or a fresh actual M3 regression.

An independent follow-up checked the current combined unit/harness collection:
1,107 nodes, including 25 parameter IDs containing `::` and three containing text
that resembles a skipped/error summary. Local pytest's official mangle_test_address
partitions `[` before splitting address components and restores the entire suffix.
The new validator instead splits the complete node, producing incorrect JUnit
classname/name pairs and rejecting correctly named executed cases. Independently,
the collection disposition regex scans node record lines and rejects the valid
HG044 parameter IDs `[1 skipped]`, `[1 passed, 1 skipped]` and `[1 passed, 1 error]`.

collection-probe.py constructs concise valid collection/JUnit examples using the
installed pytest implementation. Provenance is isolated to focus on the content
oracle: a plain-ID positive control passes, a delimiter-ID positive is incorrectly
rejected as incomplete-executed-collection, and a legitimate summary-text parameter
is incorrectly rejected as collection-oracle. The report retains actual collection
content hash and compact prefix/count evidence without copying enormous parameter
strings. Both failures block the required full-harness M3 exit. Repair at a new
implementation SHA, retest, and obtain fresh independent reviews; frozen semantics
do not require change.
