# Remaining historical reports — prospective rule proposal

This is a separate governance definition draft, not current authority, a runtime
implementation, a task PASS, or a merge recommendation. Protected base is
4e9c60a242d84b81b6e82b635da6c7227af68912. Human authorization: “Prepare a separately
reviewed rule for the remaining unsupported historical report forms, then resume
HG-058 after it merges.” All old bytes, outcomes, captures and failures remain.

## Concrete problem and proposed decision

Five bound structured reports have original producer commands whose observed exits
are absent. Their fields cannot satisfy HG061's closed nine-predicate source form.
Some contain successful child-run exits; these do not observe their own producing
command. Some producers were external temporary scripts; no stored source should
be invented. Original immutable report and review linkage can be verified, but that
is weaker than independently verifying the original computation.

Add a separate global archival observation for these closed report structures:
`documentary_validation=BOUND_ORIGINAL_CLAIM`,
`semantic_validation=UNVERIFIED_ORIGINAL_COMPUTATION`,
`historical_execution=UNVERIFIED_MISSING_PRODUCER_EXIT`,
`historical_review_acceptance=NOT_CERTIFIED`,
`acceptance_eligible=false`.

These are unverified claims, never VERIFIED semantic assertions. Do not reuse the
HG061 VERIFIED result or infer exit0, completed execution, successful computation,
execution PASS or retrospective correction. Preserve all original PASS labels as
claims. An explicit diagnostic identifies each missing fact and each preserved
component observation. Original component exits stay bound to their own commands.

Prospectively amend HG060 global inventory only: an eligible original claim with
this explicit observation may be recorded as archival inventory coherent. Such
coherence validates immutable identity, supported structure and consistent claims;
it does not validate the claimed execution or semantics. Every record/check remains
enumerated. A PASS label alone never qualifies. Fresh, selected, unmerged and newly
introduced reports do not use this rule. The observer returns a typed observation,
not a success Boolean; only the global archival inventory may consume it.

## Eligibility, independent of task identity

Resolve O/D/B/T/R/original GENERAL review/containing original merged delivery M via
existing canonical record/review identity and protected-history contracts and protected first-parent history.
Require B ancestor T ancestor R ancestor M ancestor current protected base. The
report, result and original review documents must exist at M. Require the current
record/report byte-identical to M and current copies byte-identical to the exact
validation_revision blobs. Both must be immutable regular Git blobs. Original review bytes/schema/owner/R/reference-chain binding is documentary
provenance, not proof of original review PASS or full RRO. Existing independent
global review/source-reference guards remain required; all selected freshness and
full RRO guards remain unchanged. A known historical RRO failure stays failure,
never a documentary success Boolean. Current additions cannot create eligibility;
selected owner cannot request this route. BINDING_RULES.md defines the deterministic
original-index and direct-or-one-record reference chain. Reject ambiguous original
linkage, unknown fields/form, changed bytes or missing provenance.

The original record uniquely binds check_id, declared command, B/T and report ref.
Command is attribution only; tokenize without shell expansion and never execute it.
No hash, path, task number, date or caller-provided role grants eligibility. The
sample identities in ORIGINAL_BINDINGS.json are regression/provenance inputs only.
A coherently governed owner-neutral equivalent must qualify by identical rules.

## Closed documentary forms

All forms use strict UTF-8 JSON with no BOM, duplicate keys, nonfinite values,
trailing data, type coercion or unknown keys. CLOSED_DOCUMENTARY_FORMS.json supplies the complete nested object/array/type
grammars prospectively, with no sample owner/hash/value allowlist. The governance
packet must freeze its digest before runtime implementation. This table fixes
the top-level forms and each supported report's limited interpretation:

| Form | Exact top-level keys | Documentary checks and limitation |
|---|---|---|
| Controller lifecycle receipt | controller,format,policy,run_id,snapshot,status,test_only,tree,worker | Bind original format/controller/policy/tree/snapshot and declared command to the immutable original report/record and review reference chain; no original controller execution is certified. Preserve test_only and worker component checks/exits. Parent producer exit remains unknown; no current controller/admission authority. |
| Committed integrity report | status,tested_commit,result_commit,governance_schema,suffix,audit,selected_raw_bytes,reconstructed_artifacts,full_database_required | Bind tested/result revisions and original structured audit identity/base/head. Preserve reported suffix/audit/errors/counts as claims; neither original audit computation nor producer exit is newly certified. |
| Cross-mode comparison | tested_commit,same_collection_all_runs,tests,runs,hardware,limitations | Bind tested and each run descriptor to the distinct originally referenced benchmark execution. Child exits/counts/phase outcomes remain their own observations. No parent exit or new execution-identity equality is inferred. |
| Frozen scope report | base_commit,tested_commit,files_changed,frozen_and_execution_policy_unchanged,pinned_controller_assets_changed,compatibility_note,errors,requirements_status | Bind B/T and canonical duplicate-free path lists to original scope/review declaration. Preserve frozen/scope claims, error list and explicit requirement non-PASS. Do not certify scope/frozen equality from a true field. |
| Benchmark packaging index | tested_commit,base_commit,codec_source,final_runs,development_runs,quality,roundtrips,excluded_development_artifacts | Bind B/T and explicit raw references using original contracts/readers; retain the closed codec tuple only as unverified original attribution. Distinguish final executions from different-revision development attempts; preserve interrupted130. Packaging command exit remains unknown; no new benchmark or roundtrip PASS. |

This rule does not accept arbitrary JSON shaped like these reports. The original governance check and SHA-bound review reference chain
must corroborate documentary membership and all parameter bindings; no original
producer algorithm or arbitrary prose is interpreted. The nested schemas are new prospective grammars derived from immutable report
structure; they are not claimed to have existed historically. BINDING_RULES.md
defines the exact reference-selection and consistency checks. No implementer
discretion to parse arbitrary prose or recognize further forms is authorized.

## Contradictions, bounds and caller separation

Any authenticated unstarted/interrupted/incomplete/nonzero/error/skip/failure observation
for the exact producing owner/check/B/T/command/report tuple rejects this route.
Conflicting observations, report-versus-record identity mismatch, false affirmative
claims conflicting with original PASS, or nonempty reported failure/error collections
make INVALID. Distinct earlier development failures remain separate preserved
facts and cannot be relabeled, omitted, or attached to final success. BINDING_RULES.md restricts contradiction inputs to immutable bound fields and authenticated existing native observations. Absence of the
producer exit alone stays unknown. Receipt status and child exits never substitute.

Retain strict storage decoding/reference integrity; decoder denial is INVALID,
never archival fallback. Preserve HG061's original profile unchanged. Ordinary
executed checks and the HG055 CHECK_INDEX control continue to require real integer
exit binding, exact command/T and raw output identity. Fresh HG058 collection,
execution/JUnit/observer identities, selected checks, review freshness/full RRO,
prerequisites, M3, requirements, storage/history, installation/admission, App and
release cannot consume this observation. Unknown purpose fails closed.

Use a separately frozen documentary budget, retaining HG061's byte/read/parser ceilings and adding the explicit metadata-entry ceiling: 32 unique
blobs actually read,512 secondary metadata entries resolved,32MiB aggregate,4MiB validator/1MiB other blob,4096 diff paths,1MiB diff output,
64 Git operations,262144 parser nodes,depth64 JSON/YAML (AST depth256 where needed).
Retain classifier256KiB/1024/1MiB budgets. Native original-review/decoding guards retain their own exact-context budgets;
this observer cannot replace them. No source execution, network, recursive
owner scanning, raised limit or ambient fallback. Budget exhaustion is INVALID.
Caches bind immutable object IDs/profile version; no execution/selected cache entry.

## Required review, implementation matrix and delivery

Before stable definition T, pin these nested schemas and original-reference
binding rules for all five forms; prepare positive owner-neutral fixtures and negatives for each
eligibility/type/schema/identity/claim/capture/byte/bound/caller condition. Definitions
checks validate the specified matrix and immutable research only; they do not claim
future runtime recognition PASS. Require independently reviewed GENERAL and
SECURITY_DATA_BOUNDARY at exact definition result R. All existing normal publication,
full installed bundle review, admission/App/fullDB/cleanup/hosted gates apply.

Use one separately assigned governance identity, fresh chat/worktree/branch/PR and
literal enforceable packet. Do not allocate an identity or mutate HG058 from this
draft. The coordinator owns resource scheduling and root gates. After normal merge
and regrant, SAME HG058 implements only the refined scope, starting clean3965,
retaining first-parent/maps/failures and separate original9700/live bases. Pre-import
has no PASS verdict yet; fresh full author acceptance/reviews remain mandatory.
