# Canonical fact typed-child contract

This contract defines the physical child-table plan beneath frozen logical relation S14
`canonical_fact_revisions`. It does not add a new fact kind, write path, or transaction.
The S14 root and its children are accepted together only by
`CanonicalFactService.AcceptFactRevision` inside T2-IN.

## Closed child inventory

| Child kind | Relation | Required S14 fact kind | Stable child identity | Typed values |
|---|---|---|---|---|
| `STRENGTH_SET` | `canonical_fact_strength_sets` | `WORKOUT_ACTUAL` | `set_id` | exercise identity, repetitions, load |
| `CARDIO_BOUT` | `canonical_fact_cardio_bouts` | `WORKOUT_ACTUAL` | `bout_id` | activity identity, duration, distance |
| `HEALTH_OBSERVATION` | `canonical_fact_health_observations` | `HEALTH_OBSERVATION` | `observation_id` | metric identity, observed value |
| `NUTRITION_INTAKE` | `canonical_fact_nutrition_intakes` | `NUTRITION_INTAKE` | `intake_item_id` | nutrient identity, consumed amount |

This inventory is closed: a generic kind discriminator plus JSON/EAV payload is not an
allowed substitute, and an undeclared child kind must be rejected. The frozen S14 union
also includes `BODY_MEASUREMENT` and `OUTCOME_OBSERVATION`; this task does not invent
physical children for them. They remain typed S14 payloads until a separately authorized
task defines their physical shape.

Each child uses `(subject_id, fact_revision_id)` as a same-subject composite foreign key
to S14. Its stable child identity is revision-local content: corrections append a new S14
revision and new child rows rather than updating prior actuals. No child points to S40
prescriptions, and no plan value may populate an actual field.

## Value and missingness semantics

Every typed value stores an explicit `FactValueState`:

- `ACTUAL` requires a typed value. Numeric zero is stored as `ACTUAL` plus zero; it is
  neither missing nor unknown.
- `UNKNOWN`, `NOT_MEASURED`, `NOT_APPLICABLE`, and `PARSE_FAILED` carry no value. They
  remain distinct states and may not be coerced to zero.

This plan deliberately has no implicit nullable-value meaning. A PostgreSQL realization
must constrain state/value consistency. Unknown exposure bounds remain unknown; they are
never copied from a prescription or collapsed to a finite zero.

## Mandatory field provenance

Every typed value, including an explicit missingness state, binds all of:

- S09 evidence revision identity;
- S10 candidate assertion identity;
- S13 admission decision identity for the applicable action scope;
- a stable source locator such as a provider field, text span, or document coordinate.

Those identities are mandatory and non-blank. Acceptance must verify same-subject
references, S14 fact-kind/child-kind agreement, and provenance/admission alignment before
the T2-IN commit. Provider data remains evidence, not command authority. External actuals
may be accepted without an authorization, and that absence must not create an S45
execution binding.

## Downstream DDL obligations

KL-013 must materialize the four relations with closed kind checks, same-subject composite
foreign keys, non-null provenance identities, stable child identity uniqueness, and
state/value consistency constraints. Later command implementation must preserve the
S14/S44 writer and T2 boundary; this document authorizes no direct-write bypass.
