# HG-040 preparation barrier and upstream source assessment

Identity: harness-governance-v0.1/HG-040. Initial source/protected baseline:
`d0470badf0ccf6bec28a9bc7e6836b57d9df93ce` (normal KL075 PR74 merge).
Only this evidence directory may be written until actual normal HG039 PR75 merge.
No implementation, shared metadata, active packet, validator, task result or
product/release PASS is created during preparation. KL078 is absent at this base;
recheck identity availability after HG039 merge before appending it.

Read independently: AGENTS/index; governance/result/review/merge contracts;
task-thread-runner/protocol-guardian/db-transaction-reviewer skills; actual KL076
packet; KL076 external-worktree BLOCKER.md, upstream_gateway_probe.py, raw log and
upstream-feasibility-d0470ba.json. Source analysis confirms:

- metadata.py NATURAL_KEYS S21 requires revision; transactions.py _INSERT_COLUMNS
  S21 omits it. RestrictedSqlSession.insert runs required/allowed column checks
  before SQL. Migration S21 immutable revision default=1 is unreachable today.
- execute_preparation creates no verified factset basis; _require_insert_bindings
  requires locked factset_revisions for every S22/S23 nonnull ref_s15_id. Neither
  owner has an exact source-validation capability. No generic FK exemption is valid.
- Actual _prepare_manifest_publication joins S23 to same-subject S15, requires
  SEALED and exact current S01 epoch/frontier/program/policy/factset, all required
  role dependencies and exact FACTSET references. Omitting references, SUBJECT
  translation, raw output seeds or fabricated lock inventories cannot bridge it.
- Frozen DB S21 requires ProjectionService.RecordResult in independent short
  preparation transaction, no S01 generation update; S22 dependencies seal in the
  same S21 transaction. S23 completed candidate is immutable after READY. Frozen
  DB T3 current-basis/registry rechecks exclude computation from publication.

This is missing implementation of existing semantics. New prerequisite KL078 must
repair exactly these owner capabilities without changing frozen Protocol/DB,
public wire/owner matrix/Boundary.PREPARATION, execute_command rejection,
SafetyRegistry/S01 order, admission, authority or shadow separation.

Smallest prospective scope: transactions.py plus new persistence/preparation.py
for exact trusted typed owner recipes and immutable source identity/replay;
new tests/unit/persistence/test_preparation.py, tests/db/test_preparation.py and
docs/contracts/preparation.md. No metadata.py change is indispensable: preserve
REQUIRED_FIELDS and caller capability restrictions; server supplies revision
only at exact RecordProjection path with explicit immutable provenance. Existing
factsets.py and protocol_execution.py remain read-only prerequisites. All fixture
and namespace helpers fit the declared test modules; no wildcard helper permission.
Shared resource transaction_interfaces serializes KL075/076/077 and every
other overlapping transaction writer. DB/Compose namespace is task/SHA/root bound.

After actual HG039 merge, rebase latest protected master, confirm no KL076 result,
append complete NOT_STARTED KL078 and refine only unmerged KL076 dependency/read
context/source requirement; preserve completed artifacts and failed evidence.
Final GENERAL/PROTOCOL/DB_CONCURRENCY reviews must bind final governance SHA.
Coordinator owns merge ordering (allow KL026 first if ready); do not race master.

## Research diagnostic limits

original-gateway-d0470ba-rerun.log independently reproduces all five actual base
pre-SQL failures. candidate-gateway-d0470ba-rerun.log executes an in-memory
research candidate of the actual gateway: four positive insert-capability paths
and nine negative controls, including preserved READY completeness. Exact source
and candidate hashes are logged. Neither is PostgreSQL/task/product acceptance.
No application file changes or database/lifecycle occur. The candidate isolates
server revision injection and exact immutable same-subject SEALED lookup only;
it does not prove full typed ingress, provenance, closure/replay, S23 local lock,
READY immutability or T3 behavior. Named real-PG KL078 checks must prove all those.
Original setup failure logs are preserved and do not count as PASS.

S23 update additionally requires exact manifest_builds row lock in
_require_locked_identity; complete BUILDING→READY must use only a local S23 lock,
never S01 coordination. Existing READY insertion validation must remain active.
All proposed helper code remains under HG040 evidence until metadata release.

Prospective write-set clarification: S23 local row-lock completion is included in
transactions.py; all new typed owner identity/replay/closure helpers belong only
to declared preparation.py. No separate namespace helper or fixture module is
indispensable; helpers remain in the declared unit/DB test modules. Exact scope
is pinned by task definition/packet hashes and explicit negative harness tests.

## Optional KL075 bookkeeping disposition

Actual normal PR74 merge, result byte identity, required PASS reviews and linear
review-only suffix are independently verified in integration-provenance.json.
However, three independent raw review files were committed only after
reviewed_head_sha 5543bfb, and the existing integration validator requires every
review evidence_ref to exist at reviewed_head_sha. Thus no KL075 integration
record is appended: the optional record would not validate. This bounded repair
does not rewrite historical review/results, backdate files or weaken guards.
Historical KL075 normal merge remains established independently; review-evidence
bookkeeping needs separate consideration if an integration record is required.
