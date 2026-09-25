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
GLOBAL_RELATIONS = frozenset({"S49", "S50"})


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
    "S42": ("bound_content_hash", "scope", "issuance_reason", "artifact_dependency_closure_hash"),
    "S43": ("event_kind", "scope", "causation_key"), "S44": ("session_identity", "origin", "lifecycle"),
    "S45": ("binding_kind", "execution_scope"), "S46": ("replay_mode", "input_selection_hash"),
    "S47": ("artifact_kind", "artifact_hash"), "S48": ("release_namespace", "release_version", "release_status"),
    "S49": ("artifact_kind", "artifact_identity", "artifact_version", "validity_kind", "timeless_approval_policy", "timeless_approval_reason"),
    "S50": ("management_command_identity", "reason_code", "revocation_payload_hash"),
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
    "S44": ("execution_revision",), "S45": ("binding_revision",), "S50": ("registry_revision",),
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

DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "S27": ("local_date",),
    "S38": ("local_date",),
    "S39": ("local_date",),
}

# Frozen natural identities.  PostgreSQL uniqueness is the last line of defense for
# retries and concurrent writers; application-side lookup is never a substitute.
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "S02": ("subject_id", "actor_scope", "command_kind", "client_key"),
    "S03": ("subject_id", "aggregate_type", "aggregate_identity", "aggregate_revision"),
    "S04": ("subject_id", "ref_s03_id", "destination"),
    "S05": ("subject_id", "policy_namespace", "policy_version"),
    "S06": ("subject_id", "program_identity", "program_revision"),
    "S07": ("subject_id", "proposal_family_identity", "revision"),
    "S08": ("subject_id", "ref_s02_id"),
    "S10": ("subject_id", "assertion_family_identity", "revision"),
    "S11": ("subject_id", "event_identity"),
    "S12": ("subject_id", "association_family_identity", "revision"),
    "S13": ("subject_id", "ref_s10_id", "action_scope", "revision"),
    "S14": ("subject_id", "stable_fact_identity", "fact_revision"),
    "S15": ("subject_id", "factset_identity"),
    "S16": ("subject_id", "ref_s15_id", "member_kind", "logical_member_key", "action_scope"),
    "S17": ("subject_id", "control_identity", "control_revision"),
    "S18": ("subject_id", "control_identity"),
    "S19": ("subject_id", "catalog_namespace", "exercise_identity", "catalog_revision"),
    "S20": ("subject_id", "mapping_family_identity", "revision"),
    "S21": ("subject_id", "projection_kind", "input_basis_hash", "revision"),
    "S22": ("subject_id", "ref_s21_id", "dependency_kind", "dependency_semantic_key"),
    "S23": ("subject_id", "build_identity"),
    "S24": ("subject_id", "generation"),
    "S25": ("subject_id", "ref_s24_id", "projection_role"),
    "S26": ("subject_id", "ref_s29_id", "revision"),
    "S27": ("subject_id", "root_request_identity"),
    "S28": ("subject_id", "ref_s27_id", "request_revision"),
    "S29": ("subject_id", "ref_s27_id", "attempt_no"),
    "S30": ("subject_id", "quota_kind", "window_start", "window_end", "ref_s05_id"),
    "S31": ("subject_id", "ref_s27_id", "ref_s29_id", "operation_slot"),
    "S32": ("subject_id", "ref_s31_id", "transition_revision"),
    "S33": ("subject_id", "ref_s29_id", "operation_slot", "revision"),
    "S34": ("subject_id", "proposal_family_identity", "revision"),
    "S35": ("subject_id", "ref_s34_id", "method_version", "basis_hash"),
    "S36": ("subject_id", "ref_s24_id", "action_type", "action_parameters_hash"),
    "S37": ("subject_id", "ref_s29_id", "revision"),
    "S38": ("subject_id", "local_date"),
    "S39": ("subject_id", "local_date", "revision_no"),
    "S40": ("subject_id", "prescription_identity", "prescription_revision"),
    "S41": ("subject_id", "ref_s39_id", "member_kind", "session_slot"),
    "S42": ("subject_id", "ref_s02_id", "ref_s40_id", "scope"),
    "S43": ("subject_id", "causation_key"),
    "S44": ("subject_id", "session_identity"),
    "S45": ("subject_id", "ref_s44_id", "binding_revision"),
    "S46": ("subject_id", "id"),
    "S47": ("subject_id", "ref_s46_id", "artifact_kind", "revision"),
    "S48": ("subject_id", "release_namespace", "release_version"),
    "S49": ("artifact_kind", "artifact_identity", "artifact_version"),
    "S50": ("management_command_identity",),
}

REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    logical_id: frozenset(key) for logical_id, key in NATURAL_KEYS.items()
}
REQUIRED_FIELDS.update(
    {
        "S02": REQUIRED_FIELDS["S02"] | {"request_hash", "status"},
        "S05": REQUIRED_FIELDS["S05"] | {"content_hash"},
        "S09": frozenset({"subject_id", "source_connection_identity", "source_object_type", "source_object_identity", "trust_class", "source_class", "command_authority"}),
        "S14": REQUIRED_FIELDS["S14"] | {"fact_kind"},
        "S15": REQUIRED_FIELDS["S15"] | {"status", "storage_mode"},
        "S16": REQUIRED_FIELDS["S16"] | {"member_operation"},
        "S23": REQUIRED_FIELDS["S23"] | {"status", "captured_epoch"},
        "S24": REQUIRED_FIELDS["S24"] | {"captured_epoch", "manifest_hash", "registry_revision_at_publish", "valid_until"},
        "S27": REQUIRED_FIELDS["S27"] | {"purpose", "local_date", "status", "fence_token"},
        "S29": REQUIRED_FIELDS["S29"] | {"status", "captured_epoch", "fence_token"},
        "S31": REQUIRED_FIELDS["S31"] | {"status", "settlement_revision"},
        "S37": REQUIRED_FIELDS["S37"] | {"result", "valid_until"},
        "S42": REQUIRED_FIELDS["S42"] | {"bound_content_hash", "artifact_dependency_closure_hash", "valid_from", "valid_until", "registry_revision_at_issue"},
        "S44": REQUIRED_FIELDS["S44"] | {"origin", "lifecycle", "execution_revision"},
        "S45": REQUIRED_FIELDS["S45"] | {"binding_kind", "accepted_at", "execution_scope"},
        "S46": REQUIRED_FIELDS["S46"] | {"replay_mode", "knowledge_cutoff", "status"},
        "S49": (REQUIRED_FIELDS["S49"] - {"timeless_approval_policy", "timeless_approval_reason"}) | {"content_hash", "valid_from", "validity_kind"},
        "S50": REQUIRED_FIELDS["S50"] | {"reason_code", "revocation_payload_hash", "effective_at", "registry_revision"},
    }
)

REQUIRED_DEPENDENCIES: dict[str, frozenset[str]] = {
    "S03": frozenset({"S02"}), "S04": frozenset({"S03"}), "S10": frozenset({"S09"}),
    "S13": frozenset({"S05", "S09", "S10"}), "S14": frozenset({"S10", "S11", "S13"}),
    "S16": frozenset({"S15"}), "S18": frozenset({"S17"}), "S22": frozenset({"S21"}),
    "S24": frozenset({"S05", "S06", "S15", "S23", "S49", "S51"}),
    "S25": frozenset({"S24"}), "S28": frozenset({"S02", "S27"}),
    "S29": frozenset({"S24", "S27", "S28"}), "S31": frozenset({"S27", "S29"}),
    "S32": frozenset({"S31"}), "S33": frozenset({"S26", "S29"}),
    "S35": frozenset({"S34"}), "S36": frozenset({"S05", "S24"}),
    "S37": frozenset({"S05", "S24", "S28", "S29", "S34", "S35", "S36"}),
    "S39": frozenset({"S02", "S24", "S27", "S29", "S37", "S38"}),
    "S40": frozenset({"S34", "S49"}), "S41": frozenset({"S39", "S40"}),
    "S42": frozenset({"S02", "S05", "S24", "S36", "S37", "S40", "S49", "S51"}),
    "S45": frozenset({"S02", "S40", "S42", "S44"}), "S46": frozenset({"S24", "S48"}),
    "S47": frozenset({"S46"}),
    "S50": frozenset({"S49", "S51"}),
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
    global_relation = logical_id in GLOBAL_RELATIONS
    required = REQUIRED_FIELDS.get(logical_id, frozenset())
    result: list[SchemaItem] = [
        sa.Column("id", _uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("transaction_timestamp()")),
        sa.Column("known_at", sa.DateTime(timezone=True)),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable="effective_at" not in required),
        sa.Column("content_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content_hash", sa.Text(), nullable="content_hash" not in required),
        sa.Column("hash_scheme_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable="status" not in required),
        sa.Column("typed_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("content_schema_version > 0 AND hash_scheme_version > 0 AND revision > 0", name=f"ck_{logical_id.lower()}_versions"),
    ]
    if not global_relation:
        result.insert(1, sa.Column("subject_id", _uuid(), nullable=False))
        result.append(sa.UniqueConstraint("subject_id", "id", name=f"uq_{logical_id.lower()}_subject_id"))
    result.extend(sa.Column(name, sa.Text(), nullable=name not in required) for name in KEY_FIELDS.get(logical_id, ()))
    result.extend(sa.Column(name, sa.BigInteger(), nullable=name not in required) for name in COUNTER_FIELDS.get(logical_id, ()))
    result.extend(sa.Column(name, sa.DateTime(timezone=True), nullable=name not in required) for name in TIME_FIELDS.get(logical_id, ()))
    result.extend(sa.Column(name, sa.Date(), nullable=name not in required) for name in DATE_FIELDS.get(logical_id, ()))
    if logical_id == "S42":
        result.append(sa.Column("validity_certificate", postgresql.JSONB(), nullable=False))
    return result


def build_metadata() -> sa.MetaData:
    metadata = sa.MetaData(schema=SCHEMA)
    tables: dict[str, sa.Table] = {}
    for relation in LOGICAL_RELATIONS:
        items = _base(relation.logical_id)
        if relation.logical_id not in {"S01", "S51"}:
            for dependency in relation.dependencies:
                target_name = next(row.table_name for row in LOGICAL_RELATIONS if row.logical_id == dependency)
                required = dependency in REQUIRED_DEPENDENCIES.get(relation.logical_id, frozenset())
                target_is_global = dependency in GLOBAL_RELATIONS or dependency == "S51"
                source_is_global = relation.logical_id in GLOBAL_RELATIONS
                if dependency == "S01":
                    items.append(sa.ForeignKeyConstraint(["subject_id"], [f"{SCHEMA}.{target_name}.subject_id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}"))
                elif dependency == "S51":
                    items.extend((sa.Column("registry_state_id", sa.SmallInteger(), nullable=not required), sa.ForeignKeyConstraint(["registry_state_id"], [f"{SCHEMA}.{target_name}.id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}")))
                elif source_is_global or target_is_global:
                    ref = f"ref_{dependency.lower()}_id"
                    items.extend((sa.Column(ref, _uuid(), nullable=not required), sa.ForeignKeyConstraint([ref], [f"{SCHEMA}.{target_name}.id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}")))
                else:
                    ref = f"ref_{dependency.lower()}_id"
                    items.extend((sa.Column(ref, _uuid(), nullable=not required), sa.ForeignKeyConstraint(["subject_id", ref], [f"{SCHEMA}.{target_name}.subject_id", f"{SCHEMA}.{target_name}.id"], name=f"fk_{relation.logical_id.lower()}_{dependency.lower()}")))
        natural_key = NATURAL_KEYS.get(relation.logical_id)
        if natural_key:
            items.append(sa.UniqueConstraint(*natural_key, name=f"uq_{relation.table_name}_natural"))
        if relation.logical_id == "S09":
            items.extend(
                (
                    sa.CheckConstraint("source_revision IS NOT NULL OR observation_key IS NOT NULL", name="ck_s09_source_identity"),
                    sa.CheckConstraint("command_authority = 'NONE'", name="ck_s09_no_command_authority"),
                )
            )
        elif relation.logical_id == "S15":
            items.extend(
                (
                    sa.CheckConstraint("status IN ('BUILDING','READY','SEALED','STALE','ABANDONED')", name="ck_s15_status"),
                    sa.CheckConstraint("storage_mode IN ('FULL','DELTA')", name="ck_s15_storage_mode"),
                )
            )
        elif relation.logical_id == "S16":
            items.append(sa.CheckConstraint("member_operation IN ('SET','REMOVE')", name="ck_s16_member_operation"))
        elif relation.logical_id == "S42":
            items.append(sa.CheckConstraint("valid_until > valid_from", name="ck_s42_validity_interval"))
        elif relation.logical_id == "S43":
            items.extend(
                (
                    sa.CheckConstraint(
                        "(ref_s42_id IS NOT NULL)::int + (invalidated_epoch IS NOT NULL)::int = 1",
                        name="ck_s43_target_xor",
                    ),
                    sa.CheckConstraint(
                        "ref_s02_id IS NOT NULL OR ref_s13_id IS NOT NULL OR ref_s17_id IS NOT NULL",
                        name="ck_s43_cause_present",
                    ),
                )
            )
        elif relation.logical_id == "S49":
            items.extend(
                (
                    sa.CheckConstraint(
                        "(validity_kind = 'BOUNDED' AND valid_until > valid_from AND timeless_approval_policy IS NULL AND timeless_approval_reason IS NULL) OR "
                        "(validity_kind = 'TIMELESS' AND valid_until IS NULL AND btrim(timeless_approval_policy) <> '' AND btrim(timeless_approval_reason) <> '')",
                        name="ck_s49_validity_spec",
                    ),
                    sa.CheckConstraint(
                        "(artifact_kind = 'POLICY_BUNDLE' AND ref_s05_id IS NOT NULL AND ref_s19_id IS NULL AND ref_s48_id IS NULL) OR "
                        "(artifact_kind = 'EXERCISE_CATALOG' AND ref_s05_id IS NULL AND ref_s19_id IS NOT NULL AND ref_s48_id IS NULL) OR "
                        "(artifact_kind = 'EVALUATION_RELEASE' AND ref_s05_id IS NULL AND ref_s19_id IS NULL AND ref_s48_id IS NOT NULL)",
                        name="ck_s49_exact_typed_binding",
                    ),
                )
            )
        elif relation.logical_id == "S50":
            items.extend(
                (
                    sa.CheckConstraint("registry_revision > 0", name="ck_s50_registry_revision"),
                    sa.UniqueConstraint("registry_revision", name="uq_s50_registry_revision"),
                )
            )
        elif relation.logical_id == "S39":
            items.append(sa.UniqueConstraint("subject_id", "ref_s02_id", name="uq_s39_commit_receipt"))
        table = sa.Table(relation.table_name, metadata, *items, comment=f"{relation.logical_id} frozen logical relation")
        tables[relation.logical_id] = table
        if relation.logical_id == "S09":
            sa.Index(
                "uq_s09_provider_revision",
                table.c.subject_id,
                table.c.source_connection_identity,
                table.c.source_object_type,
                table.c.source_object_identity,
                table.c.source_revision,
                unique=True,
                postgresql_where=table.c.source_revision.is_not(None),
            )
            sa.Index(
                "uq_s09_observation_key",
                table.c.subject_id,
                table.c.source_connection_identity,
                table.c.observation_key,
                unique=True,
                postgresql_where=table.c.source_revision.is_(None),
            )
        elif relation.logical_id == "S45":
            sa.Index(
                "uq_s45_one_start",
                table.c.subject_id,
                table.c.ref_s44_id,
                unique=True,
                postgresql_where=table.c.binding_kind == "START",
            )

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

    s42, s49 = tables["S42"], tables["S49"]
    sa.Table(
        "safety_artifact_dependencies",
        metadata,
        sa.Column("artifact_id", _uuid(), nullable=False),
        sa.Column("dependency_artifact_id", _uuid(), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], [s49.c.id], name="fk_s49_dependency_artifact"),
        sa.ForeignKeyConstraint(["dependency_artifact_id"], [s49.c.id], name="fk_s49_dependency_target"),
        sa.PrimaryKeyConstraint("artifact_id", "dependency_artifact_id"),
        sa.CheckConstraint("artifact_id <> dependency_artifact_id", name="ck_s49_dependency_not_self"),
        comment="Normalized closed S49 declared dependency edge",
    )
    sa.Table(
        "authorization_artifact_closure",
        metadata,
        sa.Column("subject_id", _uuid(), nullable=False),
        sa.Column("authorization_id", _uuid(), nullable=False),
        sa.Column("artifact_id", _uuid(), nullable=False),
        sa.Column("artifact_revision", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["subject_id", "authorization_id"], [s42.c.subject_id, s42.c.id], name="fk_s42_closure_authorization"),
        sa.ForeignKeyConstraint(["artifact_id"], [s49.c.id], name="fk_s42_closure_artifact"),
        sa.PrimaryKeyConstraint("subject_id", "authorization_id", "artifact_id"),
        sa.CheckConstraint("artifact_revision > 0", name="ck_s42_closure_revision"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_s42_closure_validity"),
        comment="Materialized S42 artifact dependency closure",
    )
    return metadata


metadata = build_metadata()
