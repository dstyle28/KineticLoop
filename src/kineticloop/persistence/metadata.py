"""Physical PostgreSQL metadata for the frozen S01-S51 logical baseline."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem
from sqlalchemy.types import TypeEngine

from kineticloop.persistence.fact_children import FACT_CHILD_PLANS, FactFieldType
from kineticloop.persistence.schema_topology import DEFERRED_REFERENCES, LOGICAL_RELATIONS

SCHEMA = "kineticloop"


def _uuid() -> sa.Uuid:
    return sa.Uuid(as_uuid=False)


# Key protocol identities are columns, never hidden inside the typed payload.  JSONB is
# reserved for the versioned, closed content object whose schema version/hash sit beside it.
KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "S02": ("command_kind", "client_key", "actor_scope", "request_hash"),
    "S03": ("aggregate_type", "aggregate_identity", "event_type"),
    "S04": ("destination", "delivery_status"),
    "S05": ("policy_namespace", "policy_version"),
    "S06": ("program_identity",), "S07": ("proposal_family_identity", "change_class"),
    "S08": ("actor_identity", "approved_scope"),
    "S09": ("source_connection_identity", "source_object_type", "source_object_identity", "source_revision", "observation_key", "trust_class", "source_class", "command_authority"),
    "S10": ("assertion_family_identity", "predicate", "value_state", "unit"),
    "S11": ("event_identity", "event_kind"), "S12": ("association_family_identity", "association_state"),
    "S13": ("action_scope", "decision"), "S14": ("stable_fact_identity", "fact_kind"),
    "S15": ("factset_identity", "storage_mode", "membership_digest"),
    "S16": ("member_operation", "member_kind", "logical_member_key", "action_scope"),
    "S17": ("control_identity", "scope"), "S18": ("control_identity", "execution_scope"),
    "S19": ("catalog_namespace", "exercise_identity"),
    "S20": ("mapping_family_identity", "source_exercise_identity", "mapping_scope"),
    "S21": ("projection_kind", "input_basis_hash"),
    "S22": ("dependency_kind", "dependency_semantic_key", "collection_signature"),
    "S23": ("build_identity", "captured_input_frontier", "error_code"),
    "S24": ("input_frontier_hash", "manifest_hash", "dependency_closure_hash"),
    "S25": ("projection_role", "unavailable_reason", "validated_basis_hash"),
    "S26": ("context_hash",), "S27": ("purpose", "root_request_identity", "lease_owner"),
    "S28": ("constraint_fingerprint", "normalization_version"), "S29": ("failure_code",),
    "S30": ("quota_kind",), "S31": ("operation_slot", "config_fingerprint", "dispatch_owner", "provider_request_identity"),
    "S32": ("event_type", "receipt_identity"),
    "S33": ("tool_name", "tool_version", "operation_slot", "arguments_hash", "result_hash", "trust_class"),
    "S34": ("proposal_family_identity", "proposal_kind", "producer_artifact"),
    "S35": ("method_version", "feature_hash", "basis_hash"),
    "S36": ("action_type", "action_parameters_hash", "resolver_version", "query_basis_hash"),
    "S37": ("result", "validator_artifact"), "S38": ("calendar_policy", "day_lifecycle"),
    "S39": ("generation_mode",), "S40": ("prescription_identity", "prescription_kind"),
    "S41": ("member_kind", "session_slot"),
    "S42": ("bound_content_hash", "scope", "issuance_reason"),
    "S43": ("event_kind", "scope"), "S44": ("session_identity", "origin", "lifecycle"),
    "S45": ("binding_kind", "execution_scope"), "S46": ("replay_mode", "input_selection_hash"),
    "S47": ("artifact_kind", "artifact_hash"), "S48": ("release_namespace", "release_version", "release_status"),
    "S49": ("artifact_kind", "artifact_identity", "artifact_version"),
    "S50": ("reason_code", "revocation_payload_hash"),
}

COUNTER_FIELDS: dict[str, tuple[str, ...]] = {
    "S03": ("aggregate_revision",), "S04": ("attempt_count",), "S06": ("program_revision",),
    "S14": ("fact_revision",), "S15": ("delta_depth", "member_revision", "completed_member_revision"),
    "S17": ("control_revision",), "S18": ("head_revision",), "S19": ("catalog_revision",),
    "S23": ("captured_epoch",), "S24": ("generation", "captured_epoch", "registry_revision_at_publish"),
    "S26": ("captured_epoch",), "S27": ("fence_token", "stale_restart_count"),
    "S28": ("request_revision",), "S29": ("attempt_no", "captured_epoch", "fence_token"),
    "S30": ("admitted_count", "quota_limit"), "S31": ("dispatch_fence", "settlement_revision"),
    "S32": ("transition_revision",), "S38": ("head_revision",), "S39": ("revision_no",),
    "S40": ("prescription_revision",), "S41": ("member_order",),
    "S42": ("registry_revision_at_issue",), "S43": ("invalidated_epoch",),
    "S44": ("execution_revision",), "S45": ("binding_revision",),
}

TIME_FIELDS: dict[str, tuple[str, ...]] = {
    "S04": ("next_attempt_at",), "S08": ("expires_at",), "S15": ("sealed_at",),
    "S17": ("review_due_at",), "S21": ("computed_at", "valid_until"),
    "S24": ("valid_until",), "S26": ("source_cutoff",),
    "S27": ("deadline", "lease_expires_at"), "S29": ("started_at", "completed_at"),
    "S30": ("window_start", "window_end"), "S32": ("occurred_at",),
    "S36": ("resolution_expires_at",), "S37": ("valid_until",),
    "S42": ("valid_from", "valid_until"), "S44": ("started_at", "completed_at"),
    "S45": ("accepted_at",), "S46": ("knowledge_cutoff",), "S47": ("knowledge_cutoff",),
    "S49": ("valid_from", "valid_until"),
}


def _base(logical_id: str) -> list[SchemaItem]:
    if logical_id == "S01":
        return [
            sa.Column("subject_id", _uuid(), primary_key=True),
            sa.Column("decision_generation", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("authorization_epoch", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("input_frontier_hash", sa.Text()),
            sa.CheckConstraint("decision_generation >= 0 AND authorization_epoch >= 0", name="ck_s01_counters"),
        ]
    if logical_id == "S51":
        return [
            sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
            sa.Column("registry_revision", sa.BigInteger(), nullable=False, server_default="0"),
            sa.CheckConstraint("id = 1 AND registry_revision >= 0", name="ck_s51_singleton"),
        ]
    result: list[SchemaItem] = [
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subject_id", _uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("transaction_timestamp()")),
        sa.Column("known_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("content_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.Text()),
        sa.Column("hash_scheme_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text()),
        sa.Column("typed_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("subject_id", "id", name=f"uq_{logical_id.lower()}_subject_id"),
        sa.CheckConstraint("content_schema_version > 0 AND hash_scheme_version > 0 AND revision > 0", name=f"ck_{logical_id.lower()}_versions"),
    ]
    result.extend(sa.Column(name, sa.Text()) for name in KEY_FIELDS.get(logical_id, ()))
    result.extend(sa.Column(name, sa.BigInteger()) for name in COUNTER_FIELDS.get(logical_id, ()))
    result.extend(sa.Column(name, sa.DateTime(timezone=True)) for name in TIME_FIELDS.get(logical_id, ()))
    return result


def build_metadata() -> sa.MetaData:
    metadata = sa.MetaData(schema=SCHEMA)
    tables: dict[str, sa.Table] = {}
    for relation in LOGICAL_RELATIONS:
        items = _base(relation.logical_id)
        if relation.logical_id not in {"S01", "S51"}:
            for dependency in relation.dependencies:
                target_name = next(row.table_name for row in LOGICAL_RELATIONS if row.logical_id == dependency)
                if dependency == "S01":
                    items.append(sa.ForeignKeyConstraint(["subject_id"], [f"{SCHEMA}.{target_name}.subject_id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}"))
                elif dependency == "S51":
                    items.extend((sa.Column("registry_state_id", sa.SmallInteger()), sa.ForeignKeyConstraint(["registry_state_id"], [f"{SCHEMA}.{target_name}.id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}")))
                else:
                    ref = f"ref_{dependency.lower()}_id"
                    items.extend((sa.Column(ref, _uuid()), sa.ForeignKeyConstraint(["subject_id", ref], [f"{SCHEMA}.{target_name}.subject_id", f"{SCHEMA}.{target_name}.id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}")))
        tables[relation.logical_id] = sa.Table(relation.table_name, metadata, *items, comment=f"{relation.logical_id} frozen logical relation")

    for reference in DEFERRED_REFERENCES:
        source, target = tables[reference.source], tables[reference.target]
        if reference.field not in source.c:
            source.append_column(sa.Column(reference.field, _uuid()))
        local = [reference.field]
        remote = [target.c.id]
        if "subject_id" in source.c and "subject_id" in target.c:
            local.insert(0, "subject_id")
            remote.insert(0, target.c.subject_id)
        source.append_constraint(sa.ForeignKeyConstraint(local, remote, name=f"fk_{reference.source.lower()}_{reference.target.lower()}_{reference.field}", use_alter=True))

    s14, s09, s10, s13 = (tables[key] for key in ("S14", "S09", "S10", "S13"))
    for plan in FACT_CHILD_PLANS.values():
        constraint_tag = plan.table_name.removeprefix("canonical_fact_")
        child_items: list[SchemaItem] = [
            sa.Column("subject_id", _uuid(), nullable=False), sa.Column("fact_revision_id", _uuid(), nullable=False),
            sa.Column("stable_fact_id", _uuid(), nullable=False), sa.Column(plan.child_identity_field, _uuid(), nullable=False),
            sa.Column("child_kind", sa.Text(), nullable=False, server_default=plan.kind.value),
            sa.ForeignKeyConstraint(["subject_id", "fact_revision_id"], [s14.c.subject_id, s14.c.id], name=f"fk_cf_{constraint_tag}_s14"),
            sa.UniqueConstraint(*plan.revision_unique_key, name=f"uq_cf_{constraint_tag}_revision"),
            sa.CheckConstraint(f"child_kind = '{plan.kind.value}'", name=f"ck_cf_{constraint_tag}_kind"),
        ]
        for field in plan.fields:
            prefix = field.name
            value_type: TypeEngine[Any] = sa.Text() if field.value_type is FactFieldType.TEXT else (sa.BigInteger() if field.value_type is FactFieldType.NONNEGATIVE_INTEGER else sa.Numeric(20, 8))
            child_items.extend([
                sa.Column(f"{prefix}_state", sa.Text(), nullable=False), sa.Column(f"{prefix}_value", value_type, nullable=field.value_nullable), sa.Column(f"{prefix}_unit", sa.Text()),
                sa.Column(f"{prefix}_evidence_revision_id", _uuid(), nullable=False), sa.Column(f"{prefix}_assertion_id", _uuid(), nullable=False),
                sa.Column(f"{prefix}_admission_decision_id", _uuid(), nullable=False), sa.Column(f"{prefix}_source_locator", sa.Text(), nullable=False),
                sa.ForeignKeyConstraint(["subject_id", f"{prefix}_evidence_revision_id"], [s09.c.subject_id, s09.c.id]),
                sa.ForeignKeyConstraint(["subject_id", f"{prefix}_assertion_id"], [s10.c.subject_id, s10.c.id]),
                sa.ForeignKeyConstraint(["subject_id", f"{prefix}_admission_decision_id"], [s13.c.subject_id, s13.c.id]),
                sa.CheckConstraint(f"({prefix}_state = 'ACTUAL' AND {prefix}_value IS NOT NULL) OR ({prefix}_state IN ('UNKNOWN','NOT_MEASURED','NOT_APPLICABLE','PARSE_FAILED') AND {prefix}_value IS NULL)", name=f"ck_cf_{constraint_tag}_{prefix}_state"),
                sa.CheckConstraint(f"btrim({prefix}_source_locator) <> ''", name=f"ck_cf_{constraint_tag}_{prefix}_source"),
            ])
            if field.value_type is not FactFieldType.TEXT:
                child_items.append(sa.CheckConstraint(f"{prefix}_value IS NULL OR {prefix}_value >= 0", name=f"ck_cf_{constraint_tag}_{prefix}_nn"))
            if field.unit_policy.value == "REQUIRED_WHEN_ACTUAL":
                child_items.append(sa.CheckConstraint(f"({prefix}_state = 'ACTUAL' AND btrim({prefix}_unit) <> '') OR ({prefix}_state <> 'ACTUAL' AND {prefix}_unit IS NULL)", name=f"ck_cf_{constraint_tag}_{prefix}_unit"))
            else:
                child_items.append(sa.CheckConstraint(f"{prefix}_unit IS NULL", name=f"ck_cf_{constraint_tag}_{prefix}_unit"))
        sa.Table(plan.table_name, metadata, *child_items, comment=f"Typed {plan.kind.value} child of S14")

    s47 = tables["S47"]
    for target_id, label in (("S14", "fact_revision"), ("S20", "mapping_revision")):
        target = tables[target_id]
        sa.Table(f"replay_artifact_{label}_sources", metadata,
            sa.Column("subject_id", _uuid(), nullable=False), sa.Column("replay_artifact_id", _uuid(), nullable=False), sa.Column("source_revision_id", _uuid(), nullable=False),
            sa.ForeignKeyConstraint(["subject_id", "replay_artifact_id"], [s47.c.subject_id, s47.c.id]),
            sa.ForeignKeyConstraint(["subject_id", "source_revision_id"], [target.c.subject_id, target.c.id]),
            sa.PrimaryKeyConstraint("subject_id", "replay_artifact_id", "source_revision_id"), comment=f"S47 source edge to {target_id}")
    return metadata


metadata = build_metadata()
