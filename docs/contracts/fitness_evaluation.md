# Fixed synthetic Fitness evaluation foundation

KL-047 owns only pure local mechanical evaluation values. It runs no model,
provider, tool, database, notification or network operation and grants no execution
capability. `score` receives externally captured repository/scorer bytes; callers
are responsible for capturing the actual installed scorer and authoritative source
files. It verifies their SHA256 bytes against the predeclared manifest, rather
than accepting a caller's claimed digest. These values cannot register artifacts,
write S48, select a production release, authorize execution or activate a plan.
`ReleaseEvaluationService.RecordRelease` remains S48's sole writer.

The committed `synthetic_cases.json` contains eight local observations, one for
each required category: well-formed shadow artifact, refusal, malformed output,
timeout, tool failure, budget exhaustion, forbidden execution target and knowledge
cutoff violation. Each case binds its canonical captured input, expected mechanical
outcome, synthetic counterfactual provenance, cutoff/available/known times, and
exact source path, whole-file SHA256, clause and verbatim oracle excerpt. Expected
outcomes derive from strict shadow semantics, plan G-REMOTE-AI/M7, Technical Spec
23.2 and Protocol 7.2–7.4. Technical Spec 11 provides proposal categories and
immutability, without expert reference recommendations. Proposal payloads here
are opaque synthetic JSON; no production FitnessProposal contract is defined and
no planned value is represented as actual execution.

`predeclared_manifest.json` records an ordered nonempty test split containing all
cases. Train and tune are explicitly empty; no training or tuning occurred. Case,
dataset, split, configuration, fixture artifact, synthetic release and evaluation
identities bind canonical content. Duplicate case or underlying captured-input
identities, incomplete or overlapping membership, unknown/missing fields,
duplicate JSON keys, noncanonical hashes, unavailable individual data/outcome
labels, missing freeze metadata and tuned-on-test validation claims reject.
Changing cases, membership, freeze times, scorer or metrics changes identities;
changing model or thresholds cannot preserve a release identity. Only exact
source-derived boolean predicates exist; no Fitness quality weight, aggregate,
quality threshold or sample-size sufficiency judgment exists.

Freeze timestamps are declared synthetic test metadata, not proof of historical
custody. They precede observation times and cannot be changed under an old
identity. Inputs must be available and known by cutoff and dataset freeze. Used
data is checked against the captured input envelope. Protocol 7.3's limitation
persists: broad current-model training knowledge cannot be reconstructed as past
model knowledge. Every derivation is marked synthetic counterfactual, never a
historically known fact or independent validation after tuning on the same test.

Observations bind exact case/dataset/split/evaluation/release identity and the
ordered model/prompt/engine/policy fixture artifact references, versions, content
and hashes. Fixtures are explicitly LOCAL_UNREGISTERED_FIXTURE, not capabilities.
Every observation carries captured input/output hashes, execution disposition,
observed outcome, UTC observation time, elapsed/timeout evidence and evidence
references. Refusal, timeout, tool failure and budget exhaustion preserve an
explicit null output, its canonical null hash and matching absent reason. Missing,
duplicate, extra, unexecuted, altered or stale observations reject. A complete but
unexpected outcome yields mechanical FAIL, preserving the evidence.

Reports contain the full manifest and ordered observations, source provenance,
per-case boolean mechanical checks, counts and denominators per predicate,
canonical bytes and SHA256. Immutable nested models and canonical JSON snapshots
prevent later caller mutation. Parsing rechecks bindings, computed classifications,
counts and all limitations. Live S38/S42/S45/success targets remain null; the
execution disposition is NOT_EXECUTABLE and rollout provenance is
NO_ROLLOUT_DECISION. Synthetic mechanical PASS **always** retains model evaluation,
Fitness quality, product requirements, G-REMOTE-AI, M7 and release admission
NOT_RUN, with no measured model result. Empty or unexecuted input rejects and
cannot yield a successful report. Task PASS, requirement PASS, review PASS and
MERGED integration remain separate facts.

## Original quality and release obligations remain unresolved

Before genuine Fitness quality/model evaluation the project still needs a
separately reviewed representative corpus and expert labels/reference judgments,
a quantitative quality rubric, sample-size justification, weighting/aggregation
decisions, predeclared quality thresholds, corpus freeze/custody and independent
splits. These precise decisions are not supplied by Technical Spec 11 or by this
foundation. The original fixed evaluation/scorer project obligation remains open
beyond the mechanical foundation. Later governance must assign uncovered scope
an enforceable task packet before scheduling it; KL-047 creates no new task or
changes another packet.

G-REMOTE-AI still requires exact release/artifact identity, outbound allowlist and
redaction, a fixed subset covering refusal/bad-output/timeout, and captured **real
run** inputs/outputs before real context leaves the system. M7 still requires
structured FitnessProposal, bounded tools, complete F→D→N dependency semantics,
validation and reproducible real-data SHADOW_ONLY / NOT_EXECUTABLE evaluation.
Neither gate closure nor M7 entry/exit follows from these synthetic tests.

S48 still requires measured evaluation results, exact production artifact/report
provenance, declared dataset/split IDs, freeze times and metric/threshold config,
and a new release when model or thresholds change. No release may be declared
PASSED without measured results. Production selection still follows T2 activation.
Protocol 7.5 requires separate prescription, actual execution, adherence and
outcome evidence; causal or training-effect conclusions require a separate
research/experiment design. These fixtures establish none of those conclusions.

Current acceptance/release requirements, real PostgreSQL DC/WF/E2E evidence,
privacy and shadow/test gates, auto-activation, durable-change and integration
release obligations retain their existing status. Hevy plus HealthKit remain
mandatory launch scope; the retired spreadsheet task remains retired. The frozen
Protocol, DB baseline and requirement registry are unchanged.
