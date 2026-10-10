# Harness Governance Contract v0.1

Task implementation PRs remain governed by one task, one result, one review and one
merge. Changes to the Harness definition itself use a separate, explicit governance
record under `docs/exec-plans/governance/<CHANGE_ID>.yaml`.

A governance PR may refine task packets, backlog metadata, validator behavior,
schemas and derived document hashes. It may not change Frozen Protocol/DB files or
`FROZEN_BASELINE.json`. The committed change record must conform to
`HARNESS_CHANGE.schema.json`, name the protected base and tested revision, enumerate
the exact changed files and refined packets, and link every executed check to
committed evidence. The selected governance record must have `change_status: PASS`;
`BLOCKED` and `SPEC_CHANGE_REQUIRED` records are durable outcomes but cannot merge.

A governance change may add a fresh follow-up task identity when newly discovered work
cannot be imposed retroactively on a merged task. The new task must begin
`NOT_STARTED`, have one complete enforceable packet and exact backlog/traceability
projections, and have no result, review, or integration artifact. Its dependencies
must preserve the already-merged work as historical input. A task definition that
already has a result at the protected base is immutable: governance must create a
new dependent task instead of changing its checks, scope, dependencies, or semantic
claims.

A governance change may retire an unstarted task by changing `NOT_STARTED` to
`SUPERSEDED`. Retirement is a disposition, never task PASS: it creates no task
result or requirement evidence and removes the task from the active count. The
governance change must preserve the task identity and requirement mapping, limit the
definition edit to the status, title, replacement dependencies, structured
`superseded_by` / `disposition_reason` metadata, deliverables and definition of done,
and replace the active packet with a traceability-only packet. A new explicit
retirement packet with structured disposition metadata must contain exactly one
standalone `Scheduling barrier: MUST NOT be scheduled.` line; pre-existing historical
supersessions retain their exact identity-bound scheduling sentence. `superseded_by`
must be a non-empty exact, ordered and duplicate-free projection of changed
replacement dependencies, and the packet must exactly project both it and the durable
reason. Completed tasks are immutable. A `SUPERSEDED` task cannot have a result and
cannot be reactivated or otherwise refined through ordinary governance.

Governance changes may add a milestone schema at the repository root and milestone
records under `docs/exec-plans/milestones/`. The schema is indexed as machine-readable
authority; individual closure instances remain revision-bound records and are not
separate authority entries. Both may be appended to the delivery manifest.

Governance reviews use `docs/exec-plans/reviews/<CHANGE_ID>/<TYPE>.json`. A PASS
GENERAL review is always required. For every task definition changed between the
protected base and reviewed head, the gate requires the union of specialist review
types declared by both revisions. A governance PR therefore cannot remove its own
PROTOCOL, DB_CONCURRENCY or SECURITY_DATA_BOUNDARY review requirement. After the
reviewed governance/result revision, only that change's review directory may be
modified without rereview.

The CI merge gate derives either exactly one task result or exactly one governance
record from the protected-base diff. Mixing both PR types, changing an undeclared
path, omitting a review, or changing implementation/governance content after review
fails closed.

One non-generalizable emergency repair is admitted for `HG-024` with `KL-073` only.
That PR may contain both records solely to break the pre-existing database-CI
deadlock caused by KL-015's calendar-decayed test clock. The validator binds the
exact identities, the single implementation path
`tests/db/test_transaction_interfaces.py`, the exact governance/packet/derived-hash
files, and only the HG-024/KL-073 result, evidence, and review directories. It
requires both records to bind the same reviewed implementation/result head, every
KL-073 check to PASS with committed evidence, and the complete GENERAL, PROTOCOL,
and DB_CONCURRENCY review sets for both identities. No production path, migration,
Frozen authority, unrelated task artifact, wildcard database-test path, second
governance ID, or second task ID is admitted. The exception is exhausted by these
literal identities and cannot authorize any later mixed PR.

An already-merged governance change that lacks its required review may use one
review-only remediation PR. CI discovers exactly one existing governance change from
changed files under `docs/exec-plans/reviews/<CHANGE_ID>/` and restricts the entire PR
to that directory. The validator replays the original record against its recorded
protected base, including declared files, write scope, derived metadata, Frozen
baseline protection, evidence binding and required review types. This exception does
not admit a review-only task PR or allow governance content to change.

For that post-merge review, the tested-to-reviewed suffix may contain the two-parent
PR reintegration merge only when exactly one parent descends from `tested_commit`, the
other parent is already an ancestor of `tested_commit`, and the merge's complete Git
tree is exactly equal to the tested-descendant parent's tree. All intervening
governance bookkeeping commits remain path-checked. The reviewed-to-HEAD suffix stays
linear and review-record-only; arbitrary, content-changing and unrelated-parent merges
remain stale.

Post-merge state is recorded separately under
`docs/exec-plans/integrations/<TASK_ID>.json` and conforms to
`INTEGRATION_RECORD.schema.json`. The record binds the task result, reviewed head,
review-record commit and merge commit; it never rewrites the pre-review task result.
The referenced result commit must contain exactly one supported representation,
`<TASK_ID>_RESULT.yaml` or `<TASK_ID>_RESULT.json`, and that artifact must parse and
conform to the result schema. The reviewed head must contain the same representation
with byte-identical content. The bound result must be PASS and satisfy all semantic
result checks, including required task checks and revision-bound evidence.

Integration review references follow the precise source binding in the Thread Review
Contract: regular Git blobs at the reviewed SHA, or review-created bookkeeping blobs
at the exact recorded review commit after proof of a linear, exclusively own-task
REVIEW_RECORD_ONLY suffix. This never substitutes reviewer logs for the task's
pre-review test evidence or uses later unbound additions. Neither delayed post-merge
review nor exact-tree squash relaxes that proof for review-created references.

An already-merged task that lacks required review or integration bookkeeping may be
closed by one governance remediation PR. That PR may add only the task's required
review records together with its integration record; a changed task review directory
without the matching changed integration record fails closed. Every required review
must be PASS and bind the exact integrated merge tree. This exception does not permit
task implementation, result, evidence, packet, requirement, or frozen-authority
changes.

The integration revision chain is intentionally asymmetric. `result_commit` must
be a Git ancestor of `reviewed_head_sha`, and `reviewed_head_sha` must be a Git
ancestor of `review_record_commit`. `merge_commit` must be a Git ancestor of the
current HEAD. Only the `review_record_commit` to `merge_commit` edge has a squash
merge exception: that edge is valid when it has normal Git ancestry or when the
two commits' complete Git tree object IDs are exactly equal. The validator does
not accept matching path subsets, selected-file content comparisons, patch
equivalence, or any other near match in place of complete tree identity.
For the governance remediation exception above, the reverse ancestry direction is
accepted only when `reviewed_head_sha` equals `merge_commit` exactly and
`merge_commit` is an ancestor of `review_record_commit`; this records a genuinely
post-merge review of the integrated tree without relabeling a later commit as the
historical merge.


## HG-046 workflow compatibility

The authorized prospective local-first CI change has an exact task-specific scope.
It may update only the final generic `ci.yml`/`db.yml` compatibility assertions in
`tests/db/test_startup_readiness.py`, replacing the legacy workflow hashes with
structural assertions for the new approved triggers and hosted fallback. All
KL-074-specific exact workflow bytes/hash, negative mutations, hosted provenance,
probe behavior, fixtures, packets and historical results remain unchanged. This
named compatibility scope also updates the old `paths-ignore` string check in
`tests/db/test_workflow.py` to require exclusively manual full-DB dispatch and no
historical auto-writeback. These two exact test paths do not authorize other database test or runtime edits, and the
exception applies only to HG-046. The full DB suite must pass at the new tested SHA.

The same unmerged HG-046 concern also owns conservative DB classification, the
externally installed local controller/App client and isolated trusted validation/
pytest entrypoints, their negative tests and local installation contract. Master
protection configuration is explicitly authorized by the user and recorded in
HG-046 setup evidence. No signing credential is a repository artifact. The
controller is activated only after independent review of its implementation;
required checks may be installed earlier to block merges pending validation.

Prospective compact evidence follows [Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md);
all existing revision bindings and PASS oracles remain mandatory.

HG051 authorizes only the exact four KL080 historical current-tree representations
pinned by [Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md) and
`HISTORICAL_EVIDENCE_MAPPING.schema.json`. Original bytes, Git commits, result/review
bindings and failures remain historical. Archival mapping/retrieval is never
execution evidence or task/requirement/review/M3 PASS. Migration precedes new testing;
no post-test overwrite or post-review suffix exception is added. Normal ancestry
must retain originals, and unavailable original revisions fail original verification.

HG051 requires fresh SHA-bound GENERAL, PROTOCOL, DB_CONCURRENCY and
SECURITY_DATA_BOUNDARY review. Its exact implementation/schema/contract/test paths
and own governance/evidence/review directories are enumerated in its committed scope
and validator allowlist. It may refine only unmerged KL080 preservation language;
all checks, oracles, resources, dependencies and frozen semantics remain identical.
It does not migrate KL080 artifacts, close KL080/M3, install a trusted validator,
admit a controller version or confer product/release PASS.

HG054 prospectively authorizes optional bounded xz-v1 execution storage and explicit
same-owner already-compact unmerged forward re-encoding as specified in
[Evidence Storage Policy](EVIDENCE_STORAGE_POLICY.md). Default gzip, all budgets,
original bound records/Git ancestry, failed checks and stale-review rules remain
unchanged. Its validator allowlist exactly matches its preserved execution packet.
Fresh SHA-bound GENERAL, PROTOCOL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY reviews
are mandatory. It changes no runtime, DB, frozen/product/release or CI authority,
migrates no other task artifacts, reuses no HG051 exception and installs/adopts no
credentialed controller. Installation/admission and App/fullDB stay separate gates.

## HG057 clean successor recovery

HG057 defines only the exact KL036 SUPERSEDED disposition, NOT_STARTED enforceable
KL081 functional successor, unmerged KL038/KL039/KL064 dependency projections and
prospective HG058 execution packet. Its literal validator scope includes these
packets, backlog/traceability/plan, own governance/evidence/reviews, derived index
and manifest, and only scope/projection validator tests. Eight author checks and
fresh GENERAL, PROTOCOL, DB_CONCURRENCY and SECURITY_DATA_BOUNDARY are mandatory.
The three dependency-only edits preserve all remaining definitions, including
existing refinement barriers; they do not make their templates ENFORCEABLE.

Original KL036 local 1fee7a4ef9ecb484da24522962a6df4d4c2bd9b9/PR99 and HG056
final 8bfb977f67f9e1fa8af8fb43fe98ad5bebd89aea/PR102, tested
1cb64a1baef54fc7801e4084a18db962c3528a70 and result
0b089d7d3b0212a4e5458dc7891cbb4e831cd6f6 stay immutable unmerged failed/blocked
history. No old evidence/result/review or branch ancestry is adopted. Replacement
links precede coordinator-owned eventual closure; no deletion or historical rewrite.
Disposition and governance PASS are never functional or requirement PASS.

HG058's exact prospective scope and complete acceptance/installation requirements
are in docs/exec-plans/active/HG-058.md. It requires GENERAL and
SECURITY_DATA_BOUNDARY; its source-inspection purpose proves source availability
only, with reviewed SHA first and absence-only exact original review-record fallback
under regular-blob/linear own suffix proof. HG057 activates no reader implementation,
storage trust, schema field, inspection caller or controller. Unsupported routing
must be a concrete packet issue, never guessed permission. Execution/M3/storage/
global history guards and original failure facts stay enforced. Actual merged HG058,
reviewed complete installation/pins, exact controller admission and installed App
unit/harness/fullDB/cleanup readiness precede KL081; five merged functional owners
and all 16 fresh checks remain required. No runtime/frozen/release PASS is conferred.

## HG059 definitions and HG058 continuation

HG059 is definitions-only governance under its committed PACKET.md: explicit
REVIEW_SOURCE_DECLARATIONS schema/six tuples, non-execution REVIEW_SOURCE_LINEAGE,
caller boundaries and prospective repaired-current-candidate acceptance. Its exact
scope includes only those definitions, three named contracts, HG058 packet,
validator scope/review/index projection enforcement and tests, derived index/manifest
and own governance/evidence/reviews. Eight author checks and fresh GENERAL plus
SECURITY_DATA_BOUNDARY reviews are required. No routing/classifier implementation,
old artifacts/ancestry, frozen authority, requirement, installation or DB changes.
`packets_refined` remains [] because HARNESS_CHANGE accepts KL identities only;
summary/files explicitly enumerate the HG058 packet refinement.

HG058 may read the exact indexed declaration/schema after HG059 normal merge; it
may not write them or expand THREAD_REVIEW schema. Its four review availability
callers and all exclusions are defined in THREAD_REVIEW_CONTRACT.md. That contract
intentionally replaces storage-aware RRO only for declared source retrieval with
separate REVIEW_SOURCE_LINEAGE. No execution/storage/freshness verdict is supplied;
HG047's actual strict RRO failure remains. Definitions PASS is never HG058 PASS.
The first-commit HG058 FAIL and conditional repaired-candidate disposition in
EVIDENCE_STORAGE_POLICY.md are authoritative; no historical rewrite or waiver.

After HG059 normally merges, the coordinator regrants the five exclusive HG058
resources. Retain original HG058 final ada3b2f0e4f24f2b1fe857ad32c95e8ff6c6b983,
tested 36b942f3087497d0c6609839df5e04398ec8bc4e and result
6081301453f30496e6a06b12e20098c4a05a9fa4, with both CHANGES_REQUIRED reviews.
Continue the existing task first-parent lineage through a normal forward merge of
live protected master; never rebase/squash/cherry-pick away original map sources or
import HG056 ancestry. Inspect/resolve only authorized paths and do not overwrite
new governance with old packet text. Retained-map base advance must satisfy the
existing HG054 storage contract: exact pre-import map bytes on task first-parent
lineage, original admission/unique merge-base, unchanged old-base-to-pre-import
audit, source still unmerged, and no mapped path or record used in base advance.
Verify every own and inherited map (the inherited map owner is HG054, not HG055).
If these conditions fail, report the exact conflict before inventing an exception.

Two base identities are mandatory: the immutable original audit base is
9700a1b95d05c856897f74f125cfdf6fb3f6e646; the new HARNESS_CHANGE base_commit is the
actual live protected PR base, as the unchanged governance-base-mismatch guard
requires. Preserve original audit-base identity in the own verification/check index
and result limitations. Run complete original-base-to-candidate storage/history
inventory as well as actual-live-base candidate audit/ci-pr; no earlier audit is
rebound. New stable T follows base adoption/implementation; every required author
command runs freshly and new result R precedes independent GENERAL/SECURITY review.
Only exact own REVIEW_RECORD_ONLY append follows R. A later protected-base change
requires a new stable tested/result revision and reviews as existing guards demand.

Root independently reviews complete ASSETS/controller_files and actual release,
validator/decoder/controller/installed commit/image/policy identities before install,
creates exact repository/PR/base/head/controller admission, and owns installed App
unit/harness/fullDB, cleanup, hosted checks and normal merge. No author install,
sign/admit or DB/App lease follows from these definitions. KL081 dependencies and
all 16 functional checks remain unchanged; all release/production/shadow boundaries
remain enforced.

## HG060 bounded recovery definitions

HG060 is one definitions-only governance task under its committed PACKET.md. Its
literal write scope and exact eight checks (definitions, validator, unit, harness,
lint, typecheck, authority, diff) are enforced by the validator; fresh SHA-bound
GENERAL and SECURITY_DATA_BOUNDARY reviews are mandatory. Only derived index hashes
and own delivery/derived manifest changes are admitted. packets_refined remains []
under the unchanged KL-only schema; summary/files explicitly enumerate the HG058
packet refinement. No schema, source dispatcher, classifier, global-state runtime,
controller, DB, frozen, product, installation or admission change occurs here.

### Durable governance inventory versus selected acceptance

Global validation enumerates every durable governance record; none is skipped by
identity or outcome. Schema, canonical path/unique representation, namespaced
identity, unique checks, state, base/tested provenance and available revision-bound
references remain mandatory. Validate every PASS claim against its actual evidence,
including a PASS check inside a non-PASS record. A BLOCKED or SPEC_CHANGE_REQUIRED
outcome can contain actual FAIL and truthful NOT_RUN checks; those states never
become success. A change_status PASS record containing any FAIL or NOT_RUN check
is contradictory and globally invalid. Validating a non-PASS record never promotes
its outcome. Global validation success means the inventory is coherent, never
merge/admission/release authorization. Historical failed records remain at original
SHAs; no relabeling or future PASS pre-seeding is allowed.

For global inventory, validation_revision is the exact immutable Git commit being
validated: the author's committed current T, or ci-pr's exact supplied candidate C.
Load every durable governance record and its check evidence/diagnostic references
as regular Git blobs at that same validation_revision. Any working-tree copy must
be byte-identical to its bound blob; uncommitted records are still enumerated and
fail durable binding rather than being skipped. No new evidence_revision field is
added to HARNESS_CHANGE. The record's tested_commit identifies the producer T; it
does not claim that later results or evidence already existed at T. Existing
review, integration and declared-source references retain their own specific bound
SHAs; validation_revision never replaces those bindings or permits ambient fallback.

For every executed check, bind the exact command and tested SHA to the actual
lossless output at the record's immutable evidence revision (validation_revision
for this global inventory). PASS requires observed
integer exit0 and the existing positive execution/semantic oracle; FAIL requires an
actual nonzero integer command exit and preserved failure output/diagnostics. A
receipt saying PASS or exit0 cannot fabricate execution. Historical executed
checks retain their originally governed evidence formats and positive execution
oracles; this definition imposes no retroactive collector/JUnit format migration.
Where existing authorities require collection/execution/JUnit identities, all of
them remain mandatory; fresh HG060/HG058 author checks require full identities and
no skips/errors/failures. Original valid plain execution logs retain their original
bindings and actual observed command/exit evidence. A status-only diagnostic is
never such a log or a substitute for actual execution.
Nonzero exit, failed/error/skipped/incomplete observed execution contradicts PASS.
An absent/invalid output or mismatched command/tested revision is invalid even in a
failed record. Do not turn decoder errors into status-only validity. Global
validation never substitutes source availability for execution evidence.

NOT_RUN uses a bounded ordinary plain diagnostic JSON reference, not an execution
envelope, resolving as a regular Git blob at the record's immutable evidence
revision under its own evidence subtree. Its status or result must explicitly be
NOT_RUN, with a nonempty truthful reason and exact tested_commit (or tested);
base, when present, must equal the record base. The record's check_id/command/ref
binds each covered non-execution check; a diagnostic checks list, when present,
must contain that exact check_id/command/NOT_RUN tuple once and no contradictory
claim. A shared diagnostic without a checks list covers only the referencing
record's NOT_RUN entries at that exact tested SHA. Missing execution metadata means
non-execution only, never an implicit exit0. Any supplied aliases must agree;
execution status/PASS, output/exit/count/success claims contradict an unstarted
NOT_RUN assertion. Optional execution_state UNSTARTED requires execution_started
false, command_exit_code null and output_refs []; all must agree if supplied.
Unknown execution-like fields must fail closed rather than certify success.

An interrupted command may remain NOT_RUN only with explicit execution_state
INTERRUPTED, execution_started true, command_exit_code null, truthful termination
reason and complete preserved partial output refs bound to that command/tested SHA
and record revision. Bind driver exit separately as driver_exit_code; it never
becomes the unknown child command exit. If the child exit is known nonzero, record
FAIL with its real output, not unstarted NOT_RUN. Interrupted/unknown-exit output
cannot be a successful execution envelope or supply test PASS. Diagnostics do not
assert that the planned command ran. SKIPPED cannot be stored as a governance check
result under the unchanged HARNESS_CHANGE schema; schema rejection remains. Observed
skips in real execution never count as success. No identity exemption or whole-record
short circuit is authorized.

Selected ci-pr independently requires change_status PASS, every actual required
check PASS with valid evidence, exact base/T/R bindings, unchanged tested suffix,
fresh required reviews/full REVIEW_RECORD_ONLY proof, exact files/scope/derived
metadata, global storage/history and every existing guard. Non-PASS checks or record
states reject selected acceptance even when globally coherent. This breaks the
fresh T -> author checks -> truthful R cycle without weakening selected gates.
HG060 defines this behavior only; HG058 receives the narrow implementation grant
below. Global inventory must still report contradictions and invalid provenance.

### Same HG058 continuation after HG060 normal merge

HG058 stays frozen at 3965cac382d333bd97f6c67fec8ecbe805b5932f (failed tested
7496d0d0696a6a870d164b15cf1bbe201e942d5e). Only after normal HG060 merge may the
coordinator regrant its same five exclusive resources; no DB/App reservation.
Continue SAME task by normal forward merge of live protected master retaining
first-parent3965, original maps/source commits and every failed result/review.
Original auditbase9700 and live PR base remain separate. Rerun retained-map
base-advance conditions only for genuinely changed base and retain their prior
bound proof when base is unchanged; every map/history/original guard still applies.

HG058 may implement global durable-record state/provenance validation exactly as
above in tools/harness/validate_harness.py and existing scoped tests, alongside its
four already-authorized source callers. This adds no selected/M3/task/product/runtime
semantics. Fresh tests must cover blocked/not-run inventory, real failure provenance,
interrupted unknown exits, contradictory status/exit/evidence and fabricated-PASS
negatives, plus independent selected rejection. Prior record artifacts at original
SHAs remain unchanged; new diagnostics/records describe new observations only.

Existing generic classifier correction for giant quoted values and nonassignable
speculative prefixes is within HG058 scope only under unchanged 256KiB candidate,
1024-work/1MiB aggregate and native fail-closed exhaustion rules. No XML/path/hash
exceptions, truncation, decoder-error swallowing or output transformation. Exact
triage execution objects are regression inputs, never decoding bypass sources.
No test_planning_fixture_scope write-scope expansion merely to shorten future IDs.
Run affected reproductions first, prove the finite known-failure set clears, then
run expensive full author checks. Later defects remain real findings. New stable
T -> fresh commands -> truthful R -> fresh GENERAL/SECURITY -> final audits is
mandatory; root retains installed review/install, exact admission, App/fullDB,
cleanup, hosted gates and normal merge. All prior HG059/storage/release boundaries
remain enforced. Definitions PASS supplies no HG058/product/review/merge PASS.

## HG061 historical semantic report definitions

HG061 is definitions-only governance under its byte-pinned PACKET.md,
INITIAL_FORM.md and AUTHORITY_MAPPING.md in docs/exec-plans/evidence/HG-061/.
Its literal scope, exactly eight checks (definitions, validator, unit, harness,
lint, typecheck, authority, diff), no new authority/product projection and fresh
GENERAL plus SECURITY_DATA_BOUNDARY reviews are enforced. packets_refined stays []
under the unchanged KL-only schema; summary/files name the HG058 packet refinement.
All source declarations, codecs, storage/history, classifier, controller, schema,
frozen and product behavior remain unchanged. No runtime recognizer is installed.

The following normative initial form defines a narrow global archival observation,
separate from historical process execution. It prospectively refines HG060's global
inventory definition for this closed form only. Original PASS labels remain claims.
A VERIFIED observation certifies coherent tree facts and exposes missing historical
exit capture; it never supplies selected task/governance check PASS, prerequisite
execution, review PASS, M3, requirement, storage/history, controller admission or
release success. No generic success Boolean may cross that boundary. No task/path/
hash/date exception or invented historical machine declaration is authorized.

# HG061 initial historical-semantic form — normative definition input

This appendix resolves the dispatch definition point in AUTHORITY_MAPPING.md. It is a prospective closed compatibility profile, not a claim that an original nine-predicate machine declaration existed. The implementation belongs to HG058 after HG061 normal merge. Unknown forms fail closed; extend this profile only through separately reviewed governance. The original HG044 pins in AUTHORITY_MAPPING.md are provenance and regression samples, never runtime success conditions.

## Immutable eligibility and corroboration

Resolve the historical namespaced owner O, display identifier D, B, T, result R, original GENERAL review and containing original merged delivery M through existing governance record/review contracts and protected-prerequisite history. Require B ancestor T ancestor R ancestor M ancestor current candidate base. Read the governance record/report at the current candidate and M and require byte identity; read source and indexed authorities at T and R with identical source/authority bytes unless an original valid review-only suffix explicitly permits the particular artifact. The original result and review may postdate T. The report, original result and original reviews must already exist at M. Current candidate additions cannot create eligibility, and selected owner O cannot take this route. Existing original review validity/suffix rules remain required; this profile does not repair original reviews.

Require unique original scope check in the original governance record. Its declared command must tokenize without shell expansion as exactly an interpreter path followed by one canonical owner-evidence .py source path; no flags/operators/substitutions/extra operands. The interpreter path is an attribution string, never executed. The sole reference must identify the regular unchanged report. Bind B/T/owner to the record, source literals, report and independent review evidence; all mismatches reject.

Original authority recognition is conjunctive, using only these recognized structures, not arbitrary prose interpretation:
1. Original indexed validator contains one top-level governance_allowed_patterns function whose first executable statement after an optional docstring is one direct branch comparing change_id == D and returning a literal list. Each resolved top-level string constant must have a unique binding with no reassignment. Its seven ordinary paths (literals or single top-level string constants) equal the source allowed set; the remaining three entries are exactly owner evidence/review /** patterns and the owner governance .yaml path. No arbitrary glob/alias/expression resolution. The profile requires seven distinct ordinary paths and these three owned entries, with a complete set comparison.
2. Original indexed validator has a unique top-level prefix guard with parameters root, base, reviewed; it reads B and reviewed PROJECT_PLAN through git show and returns [] exactly on after.split(marker,1)[0] == before + '\n', otherwise one literal diagnostic. Its separate marker guard requires marker count == 1. The marker, plan path and LF suffix must equal the source parameters. Function names/diagnostic literals may vary; ambiguity or additional semantic conditions in the prefix guard reject. Permit only an optional docstring in this three-statement guard; parse recognized expressions structurally, never execute them.
3. Original governance known_limitations contain the exact declaration `Synthetic isolated Git fixture data is validator input only, never actual project completion evidence. Existing canonical M1/M2/integration/provenance validator functions are byte-identical.` as a complete limitation item (surrounding whitespace only may normalize). Original GENERAL assessment is explanatory read-only provenance, not an executable eligibility condition or prose oracle; the literal limitation and structured inventory/audit supply the defined corroboration. The original GENERAL review must bind R and explicitly reference the regular inventory and structured audit. The inventory has changed_existing, added and unchanged_hashes; selected six names are absent from changed_existing/added and present in unchanged_hashes with lowercase 64-hex SHA256 equal to recomputed T spans. Names in each list/map are unique. Extra inventory entries describe the independent review's preservation superset; they are not additional report predicates. The declaration is a literal supported legacy form, not a semantic parser or an owner exception.
4. The original indexed closure contract contains the literal two-sentence declaration `a later governance PR may create \`<instance-path>\` only after all prerequisites and fresh integrated executions exist. <owner-token> creates no instance.` Match after folding ASCII whitespace between words, retaining punctuation/backticks/path bytes. owner-token is D with hyphens removed, derived rather than whitelisted. instance-path must equal the source absence path and be a canonical .json path below docs/exec-plans/milestones/. This closed declarative form supplies the non-creation authority; unrelated prose is not parsed.
5. Original referenced structured review audit binds base=B,tested=T,reviewed=R and has literal true checks record_identity_revisions_status, path_mode_scope, tested_ancestry_and_suffix, no_actual_closure, only_legacy_function_edits_are_dispatch_scope and committed_plan_prefix. Its status is the original PASS claim. Validate existing raw review hash/reference integrity; no current caller-provided audit. Its changed_path_count is the original review B..R count, not the report's B..T count: never conflate them. These historical assertions are corroboration only; the new verifier independently recomputes the nine tree predicates.

The literal declarations above are a closed legacy syntax, not a hash/date/task exemption. A coherent owner-neutral fixture with a different O/D/B/T/R/M, marker, ordinary paths, instance path, six function names and references qualifies under the same structure and all original authority checks. Altered parameters without matching independently original authorities reject. O, D, fixed sample hashes and task number must never decide success.

## Source recognition as data

Require a complete recognized AST skeleton for the original audit. Ignore only comments, one optional module docstring and location attributes; retain statement order, operators, calls, comprehension targets and assignment structure. No extra executable statement, assignment or binding is accepted. The skeleton consists solely of:
- imports ast, hashlib, json, subprocess and from pathlib import Path;
- root=Path.cwd(), base=<B literal>, head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(); old=check_output(['git','show',base+':'+<validator-path>],text=True), new=(root/<validator-path>).read_text();
- one undecorated synchronous functions(text) containing lines=text.splitlines(keepends=True) and the exact dict comprehension n.name to ''.join(lines[n.lineno-1:n.end_lineno]) over ast.parse(text).body filtered by isinstance(n,ast.FunctionDef);
- before,after=functions(old),functions(new); preserved=<six distinct identifier strings>; checks={name:before[name]==after[name] for name in preserved}; changed=check_output(['git','diff','--name-only',base,head],text=True).splitlines(); allowed=<seven distinct canonical path string set>;
- checks['scope']=all(p in allowed or p.startswith(<owned-evidence-prefix>) or p.startswith(<owned-review-prefix>) or p==<owned-governance-path> for p in changed);
- old_plan=check_output(['git','show',base+':'+<plan-path>],text=True); new_plan=(root/<plan-path>).read_text(); checks['plan_prefix']=new_plan.split(<marker>,1)[0]==old_plan+'\n'; checks['no_instance']=not (root/<instance-path>).exists();
- report=dict(base_commit=base,tested_commit=head,checks=checks,changed=changed,status='PASS' if all(checks.values()) else 'FAIL',preserved_function_sha256={n:hashlib.sha256(after[n].encode()).hexdigest() for n in preserved});
- p=root/f'<owned-evidence-prefix>scope-{head[:7]}.json'; assert not p.exists(); p.write_text(json.dumps(report,indent=2)+'\n'); print(report['status']); raise SystemExit(0 if all(checks.values()) else 1).

Every abbreviated check_output above means exactly subprocess.check_output; unqualified or aliased calls reject. Each base/path expression is exactly BinOp(Name('base'), Add, Constant(':' + path)), where the constant is one already literal string in the parsed AST. The notation does not permit evaluating arbitrary concatenation. Variable names above are fixed syntax, paths/owner/marker/B/preserved literals are parameter slots. This skeleton is recognized without running any call, importing original modules or evaluating expressions. A command AST does not establish that it ran, that its workspace matched T, or that it produced the report. Independent original authority conjunction is mandatory even when the whole skeleton matches.

## Types, bytes and limits

Report strict UTF-8 JSON, no BOM, duplicate keys, nonfinite values or trailing non-whitespace; exactly base_commit,tested_commit,checks,changed,status,preserved_function_sha256. B/T are lowercase full Git commit strings; status exactly PASS as original claim; checks exactly six selected names plus scope,plan_prefix,no_instance, all actual JSON true booleans. Hash map exactly six selected names to lowercase64hex. changed is a duplicate-free list of canonical relative path strings, no NUL, backslash, CR/LF, absolute paths or dot traversal; it must equal the complete byte-order-sorted B..T changed-path set, not a subset. Six names cannot collide with scope/plan_prefix/no_instance. Reject empty marker, path or names.

Use immutable regular Git blobs only (100644/100755); reject symlink/submodule/tree inputs. Resolve full revisions to commits and use argv Git, no shell, no working-tree substitution. Use bounded NUL-separated diff with --no-renames and no external diff/textconv; deletions/renames contribute all affected path names. Reject paths not representable by this profile. No-instance means no Git tree entry of any mode at that exact T path. Report/path/source/authority references retain existing storage decoding and reference guards.

Recompute preserved spans using strict UTF-8 LF-only validator source, no CR/NUL/BOM. Each selected name must occur exactly once as top-level synchronous FunctionDef at B and T; a same-name async or duplicate top-level definition rejects. Ignore decorators in span comparison as explicitly limited assertion; do not claim their preservation/runtime equivalence. Span is full def line through end_lineno retaining LF and EOF state; compare bytes and hash T bytes. Plan files use same byte rules, require exactly one marker at T and compare its prefix bytes to full B plan bytes plus one LF. No normalized whitespace semantic equality.

Existing source classifier budgets remain 256KiB candidate,1024 work and1MiB aggregate; this route cannot use a raised classifier limit to make source admissible. Separately cap immutable semantic verification to 32 unique bound blobs, 32MiB aggregate raw bytes, 4MiB per validator blob, 1MiB per other blob, 4096 diff paths, 1MiB diff output, 262144 AST nodes and depth256 per validator; audit source uses existing smaller classifier budgets. JSON/YAML parsing uses depth64 and262144 aggregate scalar/container nodes under byte caps. Maximum64 Git read/diff/revision operations per report; deduplicate same object reads. Exhaustion is INVALID/explicit bounded diagnostic, not VERIFIED or fallback. No unbounded recursion, external network, subprocess source execution or generic expression interpreter. Caches must bind immutable object IDs and profile version, never path/owner alone, and cannot waive selected freshness or existing inventory budgets.

## Outcomes and required decision matrix

Only a fully coherent archived report whose sole missing execution fact is the unrecorded observed command exit may produce semantic_validation=VERIFIED, historical_execution=UNVERIFIED_MISSING_EXIT, acceptance_eligible=false. Execution contradictions refer to this exact owner/check/B/T/declared-command/report binding; superseded executions and unrelated checks remain preserved separate facts, never silently reassigned to this report. Missing original source/authority/lineage, known nonzero/failure/skip/error/interruption, known unstarted execution, incomplete observed capture or conflicting observations make semantic_validation=INVALID with truthful diagnostic; coincidentally true tree predicates never override these. Missing old exit must not become exit0 or fresh command observation. No new fact retroactively repairs original captures.

HG058 must implement positives for the immutable pinned regression and coherent owner-neutral equivalent, and negatives covering each eligibility/conjunction/structure/type/bound/byte/caller boundary above. Mutation cases include weakened source equality/all, inserted assignments/calls, unmatched original scope, invented review linkage, hash/path omission/excess, false values, known interruption/unstarted, same-owner selection, new candidate self-archival, ambiguous AST/duplicates, symlink inputs, limits, and a true semantic report routed to any selected check/review/M3/storage-history/admission consumer. No generic success Boolean crosses the caller boundary. HG061 verifies these are unambiguous definitions and preserves runtime; implementation tests await HG058.

### HG061 required implementation decision matrix and caller separation

This matrix is normative for SAME HG058's later implementation and tests. HG061
checks definitions and immutable research facts only; none of these rows asserts
that the future production recognizer ran or passed.

| Case | Required global observation | Acceptance consumers |
|---|---|---|
| Unchanged pinned original report, complete original governed/review conjunction, all nine recomputed predicates, only observed old exit absent | VERIFIED / UNVERIFIED_MISSING_EXIT / acceptance_eligible=false | No execution PASS |
| Coherent owner-neutral equivalent with different governed owner, paths, marker, six names and original references | Same observation under identical structural rules | No owner exemption or execution PASS |
| New or modified candidate claim self-designates archival | INVALID | Reject |
| Selected historical owner requests its own report route | INVALID | Selected command/exit, freshness and reviews remain required |
| True tree predicates but known interrupted, unstarted, failed, nonzero, skipped, erroneous, incomplete or conflicting bound execution | INVALID with truthful diagnostic | Reject; preserve each distinct execution |
| Status-only report, unsupported form/fields, false/empty/unknown predicates, ambiguous definitions/keys, omitted/excess hashes or paths | INVALID | Reject |
| Missing or unmatched original scope/declaration/review linkage, changed authority, weakened equality/all or inserted statements/calls | INVALID | Reject |
| Nonregular/missing/oversized blobs, bad byte/path encodings, parser/Git bounds exhausted or decoder failure | INVALID with bounded diagnostic | Reject; no fallback |
| Otherwise true semantic observation routed to selected check, prerequisite, review, M3, requirement, storage/history or admission | Ineligible by caller role | Reject; no generic success conversion |

Only the global archival governance inventory caller may request this semantic
observation. Selected task/governance checks, all review consumers, M3, requirements,
compact decoding, storage/history and admission must retain existing evidence
readers and never consume it as success. A caller cannot relabel purpose based on
report status, command source, path or content. The four HG059 source-availability
callers remain their separate declared role with all eight HG060 tuples unchanged.

### Same HG058 continuation after HG061 normal merge

This entry requirement supersedes the earlier HG059/HG060 continuation trigger:
HG058 remains frozen at 3965cac382d333bd97f6c67fec8ecbe805b5932f until actual normal
HG061 merge and coordinator regrant of harness_core, harness_governance,
harness_validator, evidence_storage and trusted_local_ci_controller. DB/App is not
reserved. Continue SAME HG058 by normal forward merge retaining first-parent3965,
all old maps/source pins and failures; no rebase/squash/imported HG056 ancestry.
Original auditbase9700a1b95d05c856897f74f125cfdf6fb3f6e646 remains distinct from the
actual live HARNESS_CHANGE base. All retained-map base-advance/original/history
proofs, nine ordinary metadata preservation rules and prior interruptions remain.
First-commit FAIL never changes; prospective repaired-candidate acceptance is new.

HG058 alone implements this closed form within its existing literal write scope,
under unchanged 256KiB candidate / 1024-work / 1MiB aggregate classifier budgets and
the semantic-specific bounds above. Exact original HG044 mapping/pins are read-only
regression/provenance inputs, never runtime exemptions or old exit inference.
Prepare all positive/negative matrix cases before stable T; then execute the full
existing HG058 author checks freshly with actual command/exits and required
collection/execution/JUnit identities. Preserve selected/freshness/RRO/M3/admission
and all source, storage, production/shadow boundaries. Fresh result R and independent
GENERAL/SECURITY reviews precede final audits. Root retains complete installed
bundle review, install, exact admission, App/unit/harness/fullDB, cleanup, hosted
gates and normal merge. Definitions PASS does not confer any of those facts.


## HG062 unverified historical documentary report definitions

HG062 is definitions-only governance under its exact PACKET.md in
`docs/exec-plans/evidence/HG-062/`. Its literal nine write patterns, eight checks
(definitions, validator, unit, harness, lint, typecheck, authority, diff), empty
new-authority/product projection, and fresh exact-R GENERAL plus
SECURITY_DATA_BOUNDARY reviews are enforced. No production observer is implemented.
`packets_refined` remains [] under the unchanged KL-only schema; summary/files
explicitly identify the HG058 packet refinement.

### Normative inputs and their authority

The six byte-pinned appendices in `docs/exec-plans/evidence/HG-062/` are incorporated
as this prospective closed definition: RULE_PROPOSAL.md, BINDING_RULES.md,
CLOSED_DOCUMENTARY_FORMS.json, ORIGINAL_BINDINGS.json, AUTHORITY_MAPPING.json and
DECISION_MATRIX.json. REVIEW_INPUTS.json pins their exact bytes and the four
preparation inputs. The original draft labels are preserved as provenance;
normal HG062 merge activates only the prospective rule, binding text, grammar and
required matrix through this contract. ORIGINAL_BINDINGS and AUTHORITY_MAPPING
remain immutable research/regression pins, never owner/hash/path exemptions or
historical certification. The other preparation inputs and R3 advisories are
non-authoritative research, not executed HG062 checks or actual task reviews.
The task-owned definition oracle and fixtures test the definition only; they are
not a production recognizer or a new evidence reader.

Only the five closed forms in that catalog are defined: controller lifecycle
receipt, committed integrity report, cross-mode comparison, frozen scope report,
and benchmark packaging index. All original record/report/review/B/T/R/M/validation
bindings, strict regular-object/byte/type/grammar/reference/lineage rules, finite
read/metadata/operation budgets, authenticated contradiction and completed native
observation requirements in BINDING_RULES.md apply conjunctively. Immutable original
linkage selects the form; PASS labels and sample identities never select it.
Absolute host attribution stays inert. The closed codec tuple remains CLAIM_ONLY;
no companion scan, source lookup/hash computation, source availability or execution
certification is authorized. Missing original producer source is never invented.

The only result is the typed observation documentary_validation=BOUND_ORIGINAL_CLAIM,
semantic_validation=UNVERIFIED_ORIGINAL_COMPUTATION,
historical_execution=UNVERIFIED_MISSING_PRODUCER_EXIT,
historical_review_acceptance=NOT_CERTIFIED, acceptance_eligible=false. No old
computation, parent exit0, PASS or review acceptance is inferred. Component claims
and distinct development exit130 remain separate. Authenticated exact-parent
nonzero/interrupted/unstarted/incomplete/error/failure/skip or conflicting evidence
rejects; observed parent exit0 uses the ordinary native evidence path. Only the
global archival governance inventory may consume this observation. Unknown purpose,
selected owner/aliases, fresh or modified candidate self-archival, malformed input,
decoder denial or exhausted bounds rejects, with no fallback or reusable success
Boolean. No selected/execution/source/decoder/storage/RRO cache receives it.

### Explicit inventory limitations and count

A current global archival inventory may complete with these unverified entries
only after all independent normal native observation and other mandatory guards
complete. It must emit each entry's five typed dimensions and limitations, plus a
machine-readable `documentary_unverified_count` equal to the exact cardinality of
these entries. This is a nonnegative integer (never a Boolean), zero iff no such
entries exist. Missing, mismatched, hidden or falsely zero counts reject inventory
completion. Nonzero must remain visible in machine-readable and human summaries;
completion must never be labeled all historical semantics or execution verified.
This is a prospective output contract only; HG062 does not implement inventory.

All selected/freshness/full REVIEW_RECORD_ONLY, global review/source-reference,
storage/history, source, decoder, M3, requirements, admission/App/release guards
remain independent and unchanged. HG047's actual historical strict RRO failure
remains failure; this observation cannot repair or replace it. HG061's distinct
source-verifiable semantic form and its original rules remain unchanged. Frozen
Protocol/DB, authorization, Evidence Admission, T1–T8, lock order, provider trust,
production/shadow separation and production auto-activation are unchanged.

### Same HG058 continuation after HG062 normal merge

This trigger supersedes the earlier HG059/HG060/HG061 triggers. SAME HG058 stays
clean at 3965cac382d333bd97f6c67fec8ecbe805b5932f without regrant until actual normal
HG062 merge and coordinator regrant of harness_core, harness_governance,
harness_validator, evidence_storage and trusted_local_ci_controller. Then retain
first-parent3965 through normal forward merge, all old report/result/failure/map/
source bytes, original auditbase9700 versus actual live base, eight source tuples,
four callers, nine ordinary metadata and all finite budgets. No second task,
history rewrite or retrospective PASS is authorized. All HG058 fresh author
acceptance/reviews/final audits remain required. Root retains complete installed
bundle review/install, exact admission, App/unit/harness/fullDB, cleanup, live
hosted gates and normal protected merge. No DB/App executor is reserved here.
