"""Physical creation topology for the frozen S01-S51 logical inventory.

``dependencies`` contains references that must exist when a relation is created.
Authoritative forward pointers which would make table creation cyclic are listed in
``DEFERRED_REFERENCES`` and are added only after every relation exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


class SchemaTopologyError(ValueError):
    """Raised when a physical schema dependency graph is incomplete or cyclic."""


@dataclass(frozen=True)
class LogicalRelation:
    """One frozen logical relation and its table-creation dependencies."""

    logical_id: str
    table_name: str
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeferredReference:
    """A foreign key added after table creation to avoid an authority-pointer cycle."""

    source: str
    field: str
    target: str
    reason: str


# This is physical creation order, not frozen logical-number order. In particular,
# the independent global/evaluation roots S48 and S51 are created before their
# lower-numbered dependents. Self-references are added with their own table and do
# not form graph edges.
LOGICAL_RELATIONS: tuple[LogicalRelation, ...] = (
    LogicalRelation("S01", "user_decision_state"),
    LogicalRelation("S02", "command_receipts"),
    LogicalRelation("S05", "policy_bundles"),
    LogicalRelation("S06", "program_versions"),
    LogicalRelation("S09", "evidence_revisions"),
    LogicalRelation("S11", "underlying_events"),
    LogicalRelation("S19", "exercise_catalog_revisions"),
    LogicalRelation("S48", "evaluation_releases"),
    LogicalRelation("S51", "safety_registry_state"),
    LogicalRelation("S03", "domain_events", ("S02",)),
    LogicalRelation("S04", "outbox_deliveries", ("S03",)),
    LogicalRelation("S10", "candidate_assertions", ("S09",)),
    LogicalRelation("S12", "event_association_decisions", ("S09", "S11")),
    LogicalRelation("S13", "admission_decisions", ("S05", "S09", "S10")),
    LogicalRelation("S14", "canonical_fact_revisions", ("S10", "S11", "S13")),
    LogicalRelation("S07", "durable_change_proposals", ("S06",)),
    LogicalRelation("S08", "approval_issuances", ("S02", "S05", "S06", "S07")),
    LogicalRelation("S17", "control_events", ("S02", "S05", "S09", "S13")),
    LogicalRelation("S18", "control_heads", ("S17",)),
    LogicalRelation("S20", "exercise_mapping_decisions", ("S08", "S19")),
    LogicalRelation("S15", "factset_revisions", ("S12", "S13", "S20")),
    LogicalRelation("S16", "factset_members", ("S12", "S13", "S14", "S15", "S20")),
    LogicalRelation("S21", "projection_versions"),
    LogicalRelation(
        "S22",
        "projection_dependencies",
        ("S05", "S06", "S14", "S15", "S19", "S20", "S21"),
    ),
    LogicalRelation("S23", "manifest_builds", ("S05", "S06", "S15", "S21")),
    LogicalRelation("S49", "safety_artifacts", ("S05", "S19", "S48")),
    LogicalRelation("S50", "artifact_revocation_events", ("S49", "S51")),
    LogicalRelation(
        "S24",
        "decision_manifests",
        ("S05", "S06", "S15", "S19", "S20", "S23", "S49", "S51"),
    ),
    LogicalRelation("S25", "manifest_projection_bindings", ("S21", "S24")),
    LogicalRelation("S27", "planning_intents", ("S01",)),
    LogicalRelation("S28", "planning_request_revisions", ("S02", "S27")),
    LogicalRelation("S29", "planning_attempts", ("S24", "S27", "S28")),
    LogicalRelation("S26", "decision_snapshots", ("S24", "S28", "S29")),
    LogicalRelation("S30", "planning_quota_buckets", ("S05",)),
    LogicalRelation("S31", "call_reservations", ("S27", "S29")),
    LogicalRelation("S32", "call_ledger_events", ("S31",)),
    LogicalRelation("S33", "tool_evidence_records", ("S26", "S29")),
    LogicalRelation("S34", "proposal_revisions", ("S26", "S29")),
    LogicalRelation("S35", "prescription_demand_features", ("S34",)),
    LogicalRelation(
        "S36", "evidence_resolutions", ("S05", "S09", "S12", "S14", "S24")
    ),
    LogicalRelation(
        "S37",
        "validation_results",
        ("S03", "S05", "S24", "S28", "S29", "S34", "S35", "S36"),
    ),
    LogicalRelation("S38", "daily_plan_heads", ("S01",)),
    LogicalRelation(
        "S39", "daily_bundle_revisions", ("S02", "S24", "S27", "S29", "S37", "S38")
    ),
    LogicalRelation("S40", "prescription_revisions", ("S34", "S49")),
    LogicalRelation("S41", "bundle_prescription_members", ("S39", "S40")),
    LogicalRelation(
        "S42",
        "authorization_issuances",
        ("S02", "S05", "S24", "S37", "S40", "S49", "S51"),
    ),
    LogicalRelation("S43", "authorization_events", ("S02", "S13", "S17", "S42")),
    LogicalRelation("S44", "workout_sessions", ("S01", "S11", "S14")),
    LogicalRelation("S45", "execution_bindings", ("S02", "S40", "S42", "S44")),
    LogicalRelation("S46", "replay_runs", ("S24", "S48")),
    LogicalRelation("S47", "replay_artifacts", ("S46",)),
)


RELATION_BY_ID: Mapping[str, LogicalRelation] = MappingProxyType(
    {relation.logical_id: relation for relation in LOGICAL_RELATIONS}
)


# These pointers express current authority but point from an early-created mutable
# root to immutable rows created later. Adding them in the second migration phase
# prevents creation cycles without weakening the final referential contract.
DEFERRED_REFERENCES: tuple[DeferredReference, ...] = (
    DeferredReference("S01", "current_factset_id", "S15", "current input authority"),
    DeferredReference("S01", "active_program_id", "S06", "active program authority"),
    DeferredReference(
        "S01", "active_policy_bundle_id", "S05", "active policy authority"
    ),
    DeferredReference("S01", "current_manifest_id", "S24", "published decision authority"),
    DeferredReference("S01", "last_control_event_id", "S17", "control barrier authority"),
    DeferredReference(
        "S01", "execution_basis_event_id", "S03", "execution exposure authority"
    ),
    DeferredReference("S03", "correlation_intent_id", "S27", "optional event correlation"),
    DeferredReference("S07", "base_manifest_id", "S24", "proposal basis"),
    DeferredReference("S07", "origin_proposal_id", "S34", "proposal provenance"),
    DeferredReference("S27", "current_request_revision_id", "S28", "request authority"),
    DeferredReference("S27", "current_attempt_id", "S29", "attempt authority"),
    DeferredReference("S27", "result_bundle_revision_id", "S39", "terminal result"),
    DeferredReference("S27", "result_authorization_id", "S42", "terminal result"),
    DeferredReference("S29", "snapshot_id", "S26", "attempt snapshot"),
    DeferredReference("S34", "demand_feature_id", "S35", "nutrition dependency"),
    DeferredReference("S38", "current_bundle_revision_id", "S39", "daily head authority"),
    DeferredReference("S51", "last_revocation_id", "S50", "registry head authority"),
)


# Explicit authority-root ordering obligations. These are narrower than reachability:
# every listed dependent must be created after the authority it directly consumes.
AUTHORITY_ROOT_CONSTRAINTS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "S01": ("S27", "S38", "S44"),
        "S02": ("S03", "S08", "S17", "S28", "S39", "S42", "S43", "S45"),
        "S05": ("S08", "S13", "S17", "S22", "S23", "S24", "S30", "S36", "S42"),
        "S06": ("S07", "S08", "S22", "S23", "S24"),
        "S09": ("S10", "S12", "S13", "S17", "S36"),
        "S11": ("S12", "S14", "S44"),
        "S19": ("S20", "S22", "S24", "S49"),
        "S21": ("S22", "S23", "S25"),
        "S24": ("S25", "S26", "S29", "S36", "S37", "S39", "S42", "S46"),
        "S27": ("S28", "S29", "S31", "S39"),
        "S31": ("S32",),
        "S38": ("S39",),
        "S44": ("S45",),
        "S46": ("S47",),
        "S48": ("S46", "S49"),
        "S49": ("S24", "S40", "S42", "S50"),
        "S51": ("S24", "S42", "S50"),
    }
)


def topological_order(
    relations: Iterable[LogicalRelation] = LOGICAL_RELATIONS,
) -> tuple[str, ...]:
    """Return a stable dependency-first order, rejecting missing or cyclic graphs."""

    relation_rows = tuple(relations)
    by_id = {relation.logical_id: relation for relation in relation_rows}
    if len(by_id) != len(relation_rows):
        raise SchemaTopologyError("logical relation IDs must be unique")

    unknown = sorted(
        {
            dependency
            for relation in relation_rows
            for dependency in relation.dependencies
            if dependency not in by_id
        }
    )
    if unknown:
        raise SchemaTopologyError(f"unknown relation dependencies: {unknown}")

    pending = {relation.logical_id: set(relation.dependencies) for relation in relation_rows}
    declared_order = {relation.logical_id: index for index, relation in enumerate(relation_rows)}
    ordered: list[str] = []

    while pending:
        ready = sorted(
            (logical_id for logical_id, dependencies in pending.items() if not dependencies),
            key=declared_order.__getitem__,
        )
        if not ready:
            blocked = {key: sorted(value) for key, value in sorted(pending.items())}
            raise SchemaTopologyError(f"cyclic relation dependencies: {blocked}")
        logical_id = ready[0]
        ordered.append(logical_id)
        del pending[logical_id]
        for dependencies in pending.values():
            dependencies.discard(logical_id)

    return tuple(ordered)
