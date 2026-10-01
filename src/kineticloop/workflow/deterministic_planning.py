"""Mechanical TEST fixture policy, immutable F/D/N and source-bound checks.

Fixture units have no nutritional, physiological or clinical interpretation.
No function issues an authorization or infers actual execution from a plan.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from kineticloop.workflow.planning import PlanningDenied, digest
from kineticloop.workflow.planning_progress import ProgressBasis, hash_identity

VERSION = "kl076-mechanical-test-v1"
RULES: dict[str, Any] = {
    "version": VERSION,
    "domain": "ISOLATED_TEST_ONLY",
    "exercise": "fixture:cycle",
    "units": "minutes_and_fixture_units",
    "window": "explicit_half_open",
    "dedup": "underlying_event_id_exact",
    "unknown_exposure": "DENY",
    "actual_replacement": "actual_replaces_exact_reservation_slot",
    "maximum_minutes": 60,
    "rolling_minutes": 90,
    "fuel_per_minute": 3,
    "estimate_per_minute": 2,
    "semantic_classes": ["PRESCRIBED_QUANTITY", "TARGET", "ESTIMATE"],
    "maximum_members": 64,
    "coverage": "all_sealed_fixture_facts_admissions_associations",
}
OWNERS = {
    "FITNESS": ("RecordProposal", "S34", "FITNESS"),
    "DEMAND": ("RecordDemandFeatures", "S35", "DEMAND_FEATURES"),
    "NUTRITION": ("RecordProposal", "S34", "NUTRITION"),
    "RESOLUTION": ("ResolveEvidence", "S36", "VALIDATING"),
    "VALIDATION": ("RecordValidation", "S37", "VALIDATING"),
}
INPUTS = {
    "FITNESS": {"snapshot"},
    "DEMAND": {"snapshot", "fitness"},
    "NUTRITION": {"snapshot", "fitness", "demand"},
    "RESOLUTION": {"snapshot", "fitness", "demand", "nutrition"},
    "VALIDATION": {"snapshot", "fitness", "demand", "nutrition", "resolution"},
}


@dataclass(frozen=True, slots=True, kw_only=True)
class PreparationRequest(ProgressBasis):
    kind: str
    sources: Mapping[str, Mapping[str, str]]
    parent_id: UUID | None = None

    def __post_init__(self) -> None:
        ProgressBasis.__post_init__(self)
        if self.kind not in OWNERS or self.source_state != OWNERS[self.kind][2]:
            raise PlanningDenied("exact fixture owner/stage required")
        if not isinstance(self.sources, Mapping) or set(self.sources) != INPUTS[self.kind]:
            raise PlanningDenied("complete exact fixture source set required")
        for source in self.sources.values():
            if set(source) != {"id", "hash"} or str(UUID(source["id"])) != source["id"]:
                raise PlanningDenied("canonical source identity required")
            hash_identity(source["hash"])
        if self.parent_id is not None and (
            type(self.parent_id) is not UUID or self.kind != "FITNESS"
        ):
            raise PlanningDenied("only FITNESS repairs bind a typed parent")


class Immutable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    def payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @property
    def content_hash(self) -> str:
        return digest(self.payload())


class Action(Immutable):
    exercise: Literal["fixture:cycle"] = "fixture:cycle"
    minutes: int = Field(ge=1, le=60)
    slot: Literal["new-fixture-slot"] = "new-fixture-slot"
    semantic_class: Literal["PRESCRIBED_QUANTITY"] = "PRESCRIBED_QUANTITY"


class Basis(Immutable):
    subject_id: str
    root_id: str
    attempt_id: str
    request_id: str
    request_revision: int = Field(ge=1)
    snapshot_id: str
    context_hash: str
    manifest_id: str
    policy_id: str
    policy_hash: str
    captured_epoch: int = Field(ge=0)
    version: Literal["kl076-mechanical-test-v1"] = "kl076-mechanical-test-v1"

    @field_validator(
        "subject_id",
        "root_id",
        "attempt_id",
        "request_id",
        "snapshot_id",
        "manifest_id",
        "policy_id",
    )
    @classmethod
    def exact_id(cls, value: str) -> str:
        if str(UUID(value)) != value:
            raise ValueError("canonical UUID required")
        return value

    @field_validator("context_hash", "policy_hash")
    @classmethod
    def exact_hash(cls, value: str) -> str:
        hash_identity(value)
        return value


class Fitness(Basis):
    kind: Literal["FITNESS"] = "FITNESS"
    id: str
    revision: int = Field(ge=1)
    parent_id: str | None
    parent_hash: str | None
    action: Action
    constraints_hash: str
    citations: tuple[str, ...] = ()


class Demand(Basis):
    kind: Literal["DEMAND"] = "DEMAND"
    id: str
    fitness_id: str
    fitness_hash: str
    method_version: Literal["kl076-mechanical-test-v1"] = "kl076-mechanical-test-v1"
    window: tuple[str, str]
    prescribed_minutes: int
    target_units: int
    estimate_interval: tuple[int, int]
    semantic_classes: tuple[tuple[str, str], ...]


class Nutrition(Basis):
    kind: Literal["NUTRITION"] = "NUTRITION"
    id: str
    fitness_id: str
    fitness_hash: str
    demand_id: str
    demand_hash: str
    fuel_units: int
    semantic_class: Literal["TARGET"] = "TARGET"


class Fact(Immutable):
    fact_id: str
    fact_hash: str
    admission_id: str
    admission_hash: str
    association_id: str
    association_hash: str
    event_id: str
    subject_id: str
    policy_id: str
    exercise: str
    scope: str
    admission: str
    association: str
    semantic_class: str
    effective_at: str
    valid_until: str
    lower_minutes: int = Field(ge=0)
    upper_minutes: int | None = Field(default=None, ge=0)
    contradicts: bool
    replaces_slot: str | None = None
    retracted: bool = False


class Resolution(Basis):
    kind: Literal["RESOLUTION"] = "RESOLUTION"
    id: str
    fitness_id: str
    fitness_hash: str
    action_type: Literal["TRAINING"] = "TRAINING"
    action_parameters_hash: str
    manifest_hash: str
    source_hash: str
    source_ranges: tuple[str, str]
    source_members: tuple[str, ...]
    facts: tuple[Fact, ...]
    supporting_events: tuple[str, ...]
    contradicting_events: tuple[str, ...]
    superseded_or_retracted_items: tuple[str, ...]
    event_association_status: str
    coverage: str
    consistency: str
    truncation_status: str
    resolution_expires_at: str


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise PlanningDenied("explicit aware source time required")
    return result


def policy(configuration: Mapping[str, Any]) -> None:
    if configuration.get("rules") != RULES or set(configuration) != {
        "rules",
        "window",
        "required_members",
        "reservations",
        "valid_until",
    }:
        raise PlanningDenied("exact mechanical TEST fixture policy required")
    window = configuration["window"]
    if (
        not isinstance(window, (list, tuple))
        or len(window) != 2
        or instant(window[0]) >= instant(window[1])
    ):
        raise PlanningDenied("explicit nonempty half-open fixture window required")
    members = configuration["required_members"]
    if (
        not isinstance(members, list)
        or not 0 < len(members) <= RULES["maximum_members"]
        or len(set(members)) != len(members)
    ):
        raise PlanningDenied("bounded explicit complete source membership required")
    for slot, minutes in configuration["reservations"].items():
        if type(slot) is not str or not slot or type(minutes) is not int or minutes < 0:
            raise PlanningDenied("typed fixture reservations required")
    instant(configuration["valid_until"])


def compute_fitness(
    basis: Basis, output: str, constraints: Mapping[str, Any], parent: Fitness | None
) -> Fitness:
    if (
        set(constraints) != {"minutes", "equipment"}
        or constraints["equipment"] != []
        or type(constraints["minutes"]) is not int
    ):
        raise PlanningDenied("fixture only accepts exact mechanical minutes/equipment constraints")
    if (basis.request_revision == 1) != (parent is None):
        raise PlanningDenied("repair must bind original immutable parent")
    if parent and (
        parent.subject_id != basis.subject_id
        or parent.root_id != basis.root_id
        or parent.request_revision + 1 != basis.request_revision
        or parent.attempt_id == basis.attempt_id
    ):
        raise PlanningDenied("repair requires next actual same-root request/new attempt")
    return Fitness(
        **basis.payload(),
        id=output,
        revision=basis.request_revision,
        parent_id=parent.id if parent else None,
        parent_hash=parent.content_hash if parent else None,
        action=Action(minutes=constraints["minutes"]),
        constraints_hash=digest(dict(constraints)),
    )


def compute_demand(fitness: Fitness, output: str, configuration: Mapping[str, Any]) -> Demand:
    policy(configuration)
    minutes = fitness.action.minutes
    base = {k: fitness.payload()[k] for k in Basis.model_fields}
    return Demand(
        **base,
        id=output,
        fitness_id=fitness.id,
        fitness_hash=fitness.content_hash,
        window=tuple(configuration["window"]),
        prescribed_minutes=minutes,
        target_units=minutes,
        estimate_interval=(minutes * 2, minutes * 2 + 1),
        semantic_classes=(
            ("prescribed_minutes", "PRESCRIBED_QUANTITY"),
            ("target_units", "TARGET"),
            ("estimate_interval", "ESTIMATE"),
        ),
    )


def compute_nutrition(
    fitness: Fitness, demand: Demand, output: str, configuration: Mapping[str, Any]
) -> Nutrition:
    if demand != compute_demand(fitness, demand.id, configuration):
        raise PlanningDenied("demand is not the deterministic exact F computation")
    base = {k: fitness.payload()[k] for k in Basis.model_fields}
    return Nutrition(
        **base,
        id=output,
        fitness_id=fitness.id,
        fitness_hash=fitness.content_hash,
        demand_id=demand.id,
        demand_hash=demand.content_hash,
        fuel_units=demand.prescribed_minutes * 3,
    )


def resolve(
    fitness: Fitness,
    output: str,
    configuration: Mapping[str, Any],
    facts: tuple[Fact, ...],
    *,
    manifest_hash: str,
    source_hash: str,
    members: tuple[str, ...],
    expires_at: str,
) -> Resolution:
    policy(configuration)
    if len(facts) > RULES["maximum_members"]:
        raise PlanningDenied("fixture source must never truncate")
    observed = {
        value for fact in facts for value in (fact.fact_id, fact.admission_id, fact.association_id)
    }
    complete = set(members) == set(configuration["required_members"]) == observed and len(
        members
    ) == len(set(members))
    if any(fact.exercise != RULES["exercise"] for fact in facts):
        raise PlanningDenied("source outside the exact mechanical fixture domain")
    start, end = map(instant, configuration["window"])
    relevant = tuple(
        sorted(
            (
                fact
                for fact in facts
                if fact.exercise == "fixture:cycle" and start <= instant(fact.effective_at) < end
            ),
            key=lambda fact: fact.fact_id,
        )
    )
    if not relevant or len({f.fact_id for f in facts}) != len(facts):
        raise PlanningDenied("missing or duplicated fixture facts")
    if any(
        f.subject_id != fitness.subject_id
        or f.policy_id != fitness.policy_id
        or f.scope != "TEST_ONLY"
        or f.admission != "ADMITTED"
        or f.semantic_class != "ACTUAL_EXECUTION"
        or f.upper_minutes is None
        or f.upper_minutes < f.lower_minutes
        for f in relevant
    ):
        raise PlanningDenied("wrong subject/basis, unknown exposure or planned/actual substitution")
    by_event: dict[str, Fact] = {}
    for fact in relevant:
        old = by_event.get(fact.event_id)
        if old and (old.lower_minutes, old.upper_minutes, old.contradicts, old.replaces_slot) != (
            fact.lower_minutes,
            fact.upper_minutes,
            fact.contradicts,
            fact.replaces_slot,
        ):
            raise PlanningDenied("duplicate underlying event has conflicting actual payload")
        by_event[fact.event_id] = fact
    associations = all(f.association == "CONFIRMED" for f in relevant)
    supporting = sorted(
        f.event_id for f in by_event.values() if not f.contradicts and not f.retracted
    )
    contrary = sorted(f.event_id for f in by_event.values() if f.contradicts)
    expiry = min(
        map(instant, [expires_at, configuration["valid_until"], *(f.valid_until for f in relevant)])
    )
    base = {k: fitness.payload()[k] for k in Basis.model_fields}
    return Resolution(
        **base,
        id=output,
        fitness_id=fitness.id,
        fitness_hash=fitness.content_hash,
        action_parameters_hash=digest(fitness.action.payload()),
        manifest_hash=manifest_hash,
        source_hash=source_hash,
        source_ranges=tuple(configuration["window"]),
        source_members=tuple(sorted(members)),
        facts=relevant,
        supporting_events=tuple(supporting),
        contradicting_events=tuple(contrary),
        superseded_or_retracted_items=tuple(sorted(f.fact_id for f in relevant if f.retracted)),
        event_association_status="CONFIRMED" if associations else "UNRESOLVED",
        coverage="COMPLETE_FOR_POLICY" if complete else "PARTIAL",
        consistency="CONSISTENT" if not contrary and associations else "CONFLICTED",
        truncation_status="NOT_TRUNCATED",
        resolution_expires_at=expiry.isoformat(),
    )


def validate(
    fitness: Fitness,
    demand: Demand,
    nutrition: Nutrition,
    resolution: Resolution,
    configuration: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    policy(configuration)
    if demand != compute_demand(
        fitness, demand.id, configuration
    ) or nutrition != compute_nutrition(fitness, demand, nutrition.id, configuration):
        raise PlanningDenied("mixed or hash-swapped F/D/N; explicit recalculation required")
    if (
        resolution.fitness_id != fitness.id
        or resolution.fitness_hash != fitness.content_hash
        or resolution.action_parameters_hash != digest(fitness.action.payload())
        or any(resolution.payload()[k] != fitness.payload()[k] for k in Basis.model_fields)
        or resolution.coverage != "COMPLETE_FOR_POLICY"
        or resolution.consistency != "CONSISTENT"
        or resolution.event_association_status != "CONFIRMED"
        or resolution.truncation_status != "NOT_TRUNCATED"
        or resolution.contradicting_events
        or resolution.superseded_or_retracted_items
        or now >= instant(resolution.resolution_expires_at)
    ):
        raise PlanningDenied(
            "missing/contradictory/incomplete/truncated/mismatched/expired resolution"
        )
    rebuilt = resolve(
        fitness,
        resolution.id,
        configuration,
        resolution.facts,
        manifest_hash=resolution.manifest_hash,
        source_hash=resolution.source_hash,
        members=resolution.source_members,
        expires_at=resolution.resolution_expires_at,
    )
    if rebuilt != resolution:
        raise PlanningDenied("resolution status cannot be supplied by citations or self-labels")
    actual = {fact.event_id: fact for fact in resolution.facts}
    if any(instant(fact.effective_at) > now for fact in actual.values()):
        raise PlanningDenied("future effective source cannot declare actual exposure")
    reservations = dict(configuration["reservations"])
    replaced: set[str] = set()
    for fact in actual.values():
        if fact.replaces_slot:
            if fact.replaces_slot not in reservations or fact.replaces_slot in replaced:
                raise PlanningDenied("actual replacement needs one exact reserved slot")
            replaced.add(fact.replaces_slot)
    rolling = (
        sum(f.upper_minutes or 0 for f in actual.values())
        + sum(minutes for slot, minutes in reservations.items() if slot not in replaced)
        + fitness.action.minutes
    )
    if (
        rolling > RULES["rolling_minutes"]
        or nutrition.fuel_units != fitness.action.minutes * RULES["fuel_per_minute"]
    ):
        raise PlanningDenied("mechanical single/rolling or cross-domain envelope failed")
    return {
        "semantic_validation": "PASS",
        "policy_envelope": "PASS",
        "rolling_minutes": rolling,
        "deduplicated_events": sorted(actual),
        "replaced_slots": sorted(replaced),
        "fixture_policy_version": VERSION,
        "source_ranges": list(resolution.source_ranges),
    }


class Validation(Basis):
    kind: Literal["VALIDATION"] = "VALIDATION"
    id: str
    fitness_hash: str
    demand_hash: str
    nutrition_hash: str
    resolution_hash: str
    execution_basis_event_id: str
    semantic_validation: Literal["PASS"] = "PASS"
    policy_envelope: Literal["PASS"] = "PASS"
    valid_until: str
    rolling_minutes: int
    deduplicated_events: tuple[str, ...]
    replaced_slots: tuple[str, ...]
    source_ranges: tuple[str, str]
    fixture_policy_version: Literal["kl076-mechanical-test-v1"] = "kl076-mechanical-test-v1"
