# HG054 prospective execution packet draft — bounded XZ evidence storage

Status: proposal for root dispatch, not an executed governance result or PASS. Read-only preflight used protected master `af09be228fbc89d074b6e863c83e1fdda343d55b` and immutable KL036 head `e71e599885de45da5bcc0a1a9f817939a3fdbcf2`; no owner files, database, network, private quarantined logs, or installed controller were changed/read beyond ordinary repository sources.

## Finding and measured choice

KL036 has 645 added/changed evidence/review regular blobs totaling **18,194,008 bytes**, versus unchanged **16,777,216** aggregate limit. Its earlier own blocker measures 18,097,388 before later records. There are 286 gzip payloads, 592,706 non-payload bytes and 148,274,287 recovered bytes across independent artifacts. Pure global sharing of byte-identical raw content offers only **11,224 bytes**, insufficient. Current capture already uses deterministic gzip level 9.

Measured stdlib `lzma.compress(raw, format=FORMAT_XZ, check=CHECK_CRC64, preset=6)` round-tripped every committed gzip payload under a **64 MiB decoder memory limit**. Projected total with all payloads changed is **2,577,426 bytes**, before small envelope length changes. Largest recovered object: 20,521,783 bytes; largest XZ object: 132,568 bytes. Total compression CPU/wall measurement across payloads was about 10.83 seconds on this host, not a performance gate or cross-platform reproducibility claim.

The smallest useful application is the four largest own unmerged harness-log payloads: gzip 9,695,205 bytes -> XZ 528,100 bytes, saving **9,167,105 bytes**, projecting **9,026,903 total** before record/envelope changes. Their raw hashes are:

- `96d7fa1d43e857aca623e8c4c8102d32df948cf5f8089ad2915080035192517b`
- `a80f15c54a610683d2d0e4d4250d1d49d77e7b5214525d9209fc2ae11d5e7182`
- `044a3e54104607ce182b3f9ef53a4c0b5db3f5fa9e0727829589099507e4fddf`
- `4fad4b1a54ccc9196841a040beac3209a40ab0c84ac5d829a49311dff7b47840`

Exact paths, per-object hashes/sizes and reproducible read-only measurement script are in `/private/tmp/kl036-storage-measure.json` and `/private/tmp/kl036-storage-measure.py`. The script accesses only committed Git blobs and does not print recovered output. These measurements demonstrate feasibility, not permission to migrate KL036 in this governance PR.

## Goal and boundaries

Add an optional deterministic `xz-v1` lossless execution-evidence representation, with existing `gzip-v1` remaining fully supported and the default capture format. Add narrowly enforced prospective forward re-encoding of **already compact, same-owner, unmerged task evidence only**. This must preserve original execution metadata, original bound objects in normal Git ancestry, raw bytes, historical failures and SHA-bound reviews. It does not authorize any plain-log historical migration or reuse/extension of HG051.

Unchanged limits: plain/envelope 256 KiB; each stored payload 8 MiB; each recovered payload 64 MiB; all changed PR evidence/review blobs 16 MiB. No exemption, split fake execution, truncated output, external archive, modified test oracle, count-based PASS, or requirement/release promotion.

HG054 changes tooling/policy/tests only. It does not change any KL036 implementation, packet, result, review, evidence or integration. After HG054 is merged and its controller installation is independently accepted, the KL036 owner may adopt it in a forward merge/commit, convert selected own compact representations before a new tested revision, rerun applicable checks, create fresh result and four reviews, and retain every earlier failed/blocked binding at its original commit. Root separately owns KL036 final App gate and normal merge. New tests on the updated runtime are real new executions; historical re-encoding never becomes a fresh execution.

## Exact scope

One fresh `codex/` branch/worktree/PR based on the current clean protected master. Before starting, inspect active tasks/open PRs and reserve exclusive governance resources. Suggested scheduler resource keys (root must reserve consistently with live owners): `harness_governance`, `harness_validator`, `evidence_storage`, `trusted_local_ci_controller`. Do not acquire KL036's `transaction_interfaces`, `user_coordination`, or `planning_ledger`; do not edit shared transaction code or databases.

Exact write_paths:

- `tools/harness/compact_evidence.py`
- `tools/harness/validate_harness.py`
- `tests/harness/test_compact_evidence.py`
- `tests/harness/test_review_evidence_provenance.py`
- `tests/harness/test_m3_milestone_closure.py`
- `tests/harness/test_validator.py`
- `tests/harness/test_local_gate.py`
- `docs/harness/EVIDENCE_STORAGE_POLICY.md`
- `docs/harness/HARNESS_GOVERNANCE_CONTRACT.md`
- `docs/harness/LOCAL_DB_CI.md`
- `tools/harness/README.md`
- `CURRENT_DOCUMENT_INDEX.json` (derived hashes only)
- `HARNESS_DOCUMENT_MANIFEST.json` (own append/derived hashes only)
- `docs/exec-plans/governance/HG-054.yaml`
- `docs/exec-plans/evidence/HG-054/**`
- `docs/exec-plans/reviews/HG-054/**`

No frozen documents/baseline, requirements, backlog/traceability, historical mappings, CI workflows, installer configuration, credentials, runtime or other task paths. Explicit HG054 allowlist in validator must equal this scope; no wildcard broadening. Specialist reviews required: GENERAL, PROTOCOL, DB_CONCURRENCY, SECURITY_DATA_BOUNDARY.

## Required behavior

1. `capture --codec xz` (default remains gzip) emits the same exact envelope fields/provenance checks, marker `xz-v1`, and same-directory `<raw_sha256>.xz`. Pin FORMAT_XZ, CRC64 and preset 6; prove repeated compression determinism on each supported runner, without assuming all liblzma versions emit identical bytes. Refuse conflicting pre-existing payloads as today. No extension guessing or fallback decoder.
2. Decoder validates regular Git objects and exact bound revision/ancestry; stored lengths/hashes before decoding; one XZ stream, CRC64, EOF and no unused/trailing bytes; bounded output `raw_bytes + 1`; fixed 64 MiB decoder memlimit; exact raw hash/length afterward. Reject unsupported/corrupt/truncated/concatenated streams, excessive dictionary requests, raw/stored bombs, wrong codec, and renamed/wrapped/nested reserved metadata. Keep UTF-8/16/32 classification, command, tested SHA, exit code and execution-count semantics unchanged. No multi-stream convenience decompression that silently accepts concatenation.
3. Audit recognizes `.xz` as a payload alongside `.gz`; orphan, duplicate-bulk, ownership, same-directory, same-revision, regular-file and total accounting rules remain intact. Both codec copies count if retained; duplicate raw bytes in separate payloads remain forbidden. Existing HG051 historical-gzip handling/schema/pinned original objects remain byte-identical and archival-only; `xz-v1` must not become a bypass into archive-read or vice versa.
4. Forward re-encoding requires a separate explicit tool action or validated manifest, never implicit conversion during read/audit/capture. Source is a full existing commit, ancestor of resulting head; source envelopes and payloads are regular valid **gzip-v1/xz-v1** blobs owned by selected identity and absent at the PR's protected base. Reject any path already present at protected base, any foreign owner, archival/plain/invalid/sanitized-as-original source, unavailable source commit, or renamed owner. Original command/tested commit/exit/timestamp/test counts/raw hash/raw length stay exactly equal. Only representation marker, payload extension/path, stored hash and stored length may differ.
5. Persist machine-validated original-to-new representation bindings: source full revision, original envelope/payload Git blob IDs and SHA256/length, new paths/hash/length, exact unchanged raw identity/metadata. Use a small task-owned ordinary audit record (e.g. `COMPACT_REENCODING.json` under a uniquely named child directory); do not embed reserved envelope objects in plain JSON or introduce an unvalidated alternate evidence format. Source snapshots remain read at original revisions; new result refs are hashes of new envelopes at new evidence revisions. Old records keep original bindings and failures. Auditing must validate every mapping and reject missing/mutated originals and untracked/remapped deletions. Remove obsolete current-tree payload only when all current-tree refs have been accounted for and original ancestry/record proofs exist. No modification of historical result/review record bytes is a migration side effect.
6. All representation mutations occur before the new tested/result/review revisions; they are not REVIEW_RECORD_ONLY. On the later KL036 adoption, preserve existing failed/blocked record snapshots, rerun checks as required at a new tested SHA, then obtain fresh four reviews. Any unresolved provenance ambiguity stays BLOCKED.

## Enforceable checks and acceptance

Run on an immutable implementation revision and record exact commands, outputs, positive case identities and actual statuses. Suggested check IDs/commands:

- `codec_security_and_budget`: `uv run pytest tests/harness/test_compact_evidence.py -q` covering both codecs and boundary/hostile cases above, unchanged inclusive numerical thresholds and HG051 regression isolation.
- `bound_reader_regressions`: `uv run pytest tests/harness/test_review_evidence_provenance.py tests/harness/test_m3_milestone_closure.py tests/harness/test_validator.py -q` proving same exact output semantics for plain/gzip/xz and same stale/missing/wrong-SHA rejection.
- `installed_decoder_isolation`: `uv run pytest tests/harness/test_local_gate.py -q` including subprocess installed-only XZ decode, poisoned candidate decoder rejection, missing/changed pinned decoder rejection and no source checkout dependency.
- `forward_reencoding_guards`: focused tests in test_compact_evidence.py for own unmerged conversion, old bound read unchanged, metadata equality, source ancestry, unavailable source, protected-base/foreign/archive/plain rejection, all-ref payload removal, mappings and changed-byte accounting. Build fixture Git histories; never mutate KL036.
- `representative_roundtrip`: `uv run python docs/exec-plans/evidence/HG-054/measure_codec.py` using deterministic non-secret representative large repeated-output fixtures, plus optional read-only pinned KL036 Git blobs available locally. Record old/new/raw hashes and bytes, reject mismatches; do not ship multi-megabyte copied KL036 logs. Demonstrate useful headroom under 16 MiB and give exact projected and actual HG054 budget separately.
- `unit`: `uv run kl test-unit -q`.
- `harness`: `uv run kl test-harness --workers 2 --evidence-dir <unique-scratch> -q`.
- `lint`: `uv run kl lint`; `typecheck`: `uv run kl typecheck`; `authority`: `uv run kl check-harness`.
- `scope`: own exact-path/frozen-byte audit; `diff`: `git diff --check <base> <tested>`.
- Before final review/merge: `python tools/harness/compact_evidence.py audit --base <base> --head <head> --identity HG-054` and `uv run kl check-harness --ci-pr-base <base> --ci-pr-head <head>` with actual passing output. Four independent reviews bind final implementation/result/evidence SHA; suffix only own REVIEW_RECORD_ONLY. Hosted and App checks bind exact final head.

A source implementation with only one codec's happy-path tests, measurements without raw hash equality, or failure status relabeling is not accepted. Any compatibility/security finding requires fix and fresh review. Runtime PostgreSQL is outside HG054 author scope; required full DB CI remains executed by the existing isolated trusted gate after independent admission, not waived as docs-only.

## Installed controller and approval implications

`compact_evidence.py` and `validate_harness.py` are pinned assets of `local_gate.ASSETS` and copied into the isolated worker. The current installed release cannot validate the new representation/rules. Root must arrange normal independently reviewed complete installation, compare all asset pins and controller identity, and obtain a new exact-head/controller admission before the HG054 App gate. A candidate PR must never load or install itself in the credentialed controller, mutate active pins, run with a signing key, reuse a stale receipt, or republish an earlier gate. Existing configuration's stale installed_commit metadata must not substitute for actual asset hashes.

No new frozen/product specification, credentials, paid service or numerical-budget approval appears necessary. This is authorized prospective Harness governance under standing instructions. Any actual installation/publication refusal remains a concrete user intervention point; do not assume approval or bypass a denial. Policy authorization for unmerged compact re-encoding must be explicit and reviewed before KL036 adoption. If reviewers conclude that preserving source-bound Git snapshots is insufficient for a particular protected historical artifact, exclude it and return that concrete limitation rather than generalize HG051.

## Resolved HG054 admission and execution

Identity: `harness-governance-v0.1/HG-054`; base B is the exact af09be commit above.
The draft above is preserved as received. Result uses existing
HARNESS_CHANGE.schema.json at docs/exec-plans/governance/HG-054.yaml (no KL result).
Merged HG047/HG049/HG051/HG053 inputs exist at B. Open PR inspection returned []
before work. Exclusive reservation: harness_governance, harness_validator,
evidence_storage, trusted_local_ci_controller. No KL036 resources or database.
Exact write_paths remain those in the draft and match the literal validator list.

The shell lacks uv. Concrete command runner is the existing Python 3.12 environment
`/Users/davetian/Personal_Projects/KineticLoop/.venv/bin/python`, with explicit
`PYTHONPATH=<this worktree>/src` selecting candidate code. Replace draft `uv run
pytest` by `python -m pytest`, `uv run python` by that Python, and `uv run kl` by
`python -m kineticloop.cli`; selectors, checks and oracles are identical. No uv shim.
The own scope check is `python docs/exec-plans/evidence/HG-054/verify_scope.py`;
actual commands/environments/output/revisions are captured by run_checks.py.
Provisional exploratory checks are not final PASS authority. Exact-path/frozen-byte
scope and diff checks, positive non-skipped tests, bound final compact audit and
four required review sets are mandatory. Immutable final runs record all failures.

One explicit reencode action persists mappings in the conversion commit, before new
testing. Mapping pins source full revision/regular blob IDs and both hashes/lengths;
only representation fields change. Maps are immutable, never execution output.
A second conversion of a previously mapped envelope in the same unmerged branch is
excluded; independent envelopes may use distinct child records. All-current-ref
payload accounting and ancestral commit auditing reject hidden/deleted/reverted
conversions. Existing same-owner exact-metadata filename/JSON-encoding compatibility
is retained. Root separately owns installation/admission, exact-head App/fullDB and
normal merge. HG054 never publishes or modifies KL036, even if measured locally.

The first immutable b8498 run is superseded after two independent review blockers;
its actual successful, failed and interrupted statuses remain committed unchanged.
Collection failed with exit 4 because the reused environment lacked pytest-xdist;
bound-reader and authority checks were deliberately interrupted after review findings,
not promoted to PASS. Initial exploratory corrected-copy probe is not final evidence.
Final executions include task-owned `/private/tmp/hg054-dependencies` on PYTHONPATH:
pytest-xdist 3.8.0 and execnet 2.1.2 copied from the existing local uv package cache,
matching declared locked/dev requirements. No primary environment, dependency lock,
CI, credentials or installed controller was changed. Run metadata records exact
package versions. Re-encoding requires serialized exclusive local mutation; ordinary
single-writer rollback is not concurrent-writer or crash recovery. Interrupted state
must remain blocked until restored/validated.
Final mapping audit also verifies already admitted protected-base maps without
allowing new historical migrations, and recognizes removed markers in encoded or
wrapped records. These are enforcement of the same preservation/reserved-metadata
requirements, not an additional format or write-scope expansion. Exact byte-pins
stay implementation/runtime specific; measurements do not assume identical XZ
sizes across liblzma versions.

Fresh corrected-source SECURITY_DATA_BOUNDARY review found that inherited-source
verification still covered only the selected owner. The d0a394 run is also preserved
as superseded with successful checks and actual deliberate interruption statuses;
no interrupted/full-harness evidence is promoted. Final correction validates admitted
canonical maps globally with each recorded owner/base, including unrelated/no-change
PRs. New conversion admission remains selected-owner-only. Cross-owner source-blob
loss and mapping mutation/deletion have isolated negative Git fixtures. No numerical
budget, execution oracle, controller installation or write-path scope changed.
