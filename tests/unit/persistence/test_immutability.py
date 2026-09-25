from kineticloop.persistence.immutability import (
    COMMAND_ENTRYPOINTS,
    ENTRYPOINT_BY_ID,
    PROTECTION_BY_ID,
    RELATION_PROTECTIONS,
    RUNTIME_ROLE_NAMES,
    DatabaseRole,
    GuardRequirement,
    LockTarget,
    SqlPermission,
    StorageClass,
    permissions_for_role,
    render_permission_sql,
    role_name_for,
)
from kineticloop.persistence.schema_topology import LOGICAL_RELATIONS


def test_permission_matrix_enforced() -> None:
    expected_relations = {relation.logical_id: relation.table_name for relation in LOGICAL_RELATIONS}

    assert len(RELATION_PROTECTIONS) == 51
    assert {row.logical_id: row.table_name for row in RELATION_PROTECTIONS} == expected_relations
    assert set(PROTECTION_BY_ID) == set(expected_relations)

    for protection in RELATION_PROTECTIONS:
        declared = {
            role_name_for(writer.principal): writer.permissions
            for writer in protection.writers
        }
        for role in RUNTIME_ROLE_NAMES:
            actual = permissions_for_role(protection, role)
            if role in {DatabaseRole.APPLICATION.value, DatabaseRole.AUDITOR.value}:
                assert actual == frozenset({SqlPermission.SELECT})
            elif role in declared:
                assert actual == declared[role]
            else:
                assert actual == frozenset()
            assert SqlPermission.DELETE not in actual

        sql = render_permission_sql(protection, schema="kineticloop")
        assert f"REVOKE ALL ON TABLE kineticloop.{protection.table_name} FROM PUBLIC;" in sql
        for role in RUNTIME_ROLE_NAMES:
            assert f"REVOKE ALL ON TABLE kineticloop.{protection.table_name} FROM {role};" in sql
        for role, permissions in declared.items():
            rendered = ", ".join(
                permission.value
                for permission in SqlPermission
                if permission in permissions
            )
            assert (
                f"GRANT {rendered} ON TABLE kineticloop.{protection.table_name} TO {role};"
                in sql
            )


def test_split_and_atomic_command_ownership_is_explicit() -> None:
    outbox = PROTECTION_BY_ID["S04"]
    origin = role_name_for("originating_domain_command")
    dispatcher = role_name_for("outbox_dispatcher")
    assert permissions_for_role(outbox, origin) == frozenset(
        {SqlPermission.SELECT, SqlPermission.INSERT}
    )
    assert permissions_for_role(outbox, dispatcher) == frozenset(
        {SqlPermission.SELECT, SqlPermission.UPDATE}
    )

    registry_role = role_name_for("safety_registry")
    assert permissions_for_role(PROTECTION_BY_ID["S50"], registry_role) == frozenset(
        {SqlPermission.SELECT, SqlPermission.INSERT}
    )
    assert permissions_for_role(PROTECTION_BY_ID["S51"], registry_role) == frozenset(
        {SqlPermission.SELECT, SqlPermission.INSERT, SqlPermission.UPDATE}
    )
    assert GuardRequirement.SAME_TRANSACTION in PROTECTION_BY_ID["S50"].guards
    assert GuardRequirement.SAME_TRANSACTION in PROTECTION_BY_ID["S51"].guards
    assert GuardRequirement.REGISTRY_GATE in PROTECTION_BY_ID["S50"].guards
    assert GuardRequirement.REGISTRY_GATE in PROTECTION_BY_ID["S51"].guards


def test_lifecycle_guard_requirements_are_machine_readable() -> None:
    assert all(
        GuardRequirement.COMMAND_ENTRYPOINT in protection.guards
        for protection in RELATION_PROTECTIONS
    )
    for protection in RELATION_PROTECTIONS:
        if protection.storage_class is not StorageClass.IMMUTABLE:
            assert protection.guards != frozenset({GuardRequirement.COMMAND_ENTRYPOINT})

    assert GuardRequirement.BUILD_WRITE_GATE in PROTECTION_BY_ID["S15"].guards
    assert GuardRequirement.PARENT_BUILD_WRITE_GATE in PROTECTION_BY_ID["S16"].guards
    assert GuardRequirement.BUILD_WRITE_GATE in PROTECTION_BY_ID["S23"].guards
    assert GuardRequirement.EVALUATION_ISOLATION in PROTECTION_BY_ID["S46"].guards
    assert GuardRequirement.EVALUATION_ISOLATION in PROTECTION_BY_ID["S47"].guards


def test_command_guards_bind_to_divergent_transaction_paths() -> None:
    def mutation_shape(command_id: str) -> set[tuple[str, SqlPermission, str]]:
        return {
            (mutation.logical_id, mutation.permission, mutation.writer_principal)
            for mutation in ENTRYPOINT_BY_ID[command_id].mutations
        }

    assert len(ENTRYPOINT_BY_ID) == len(COMMAND_ENTRYPOINTS)
    for entrypoint in COMMAND_ENTRYPOINTS:
        assert entrypoint.transaction_group
        assert GuardRequirement.COMMAND_ENTRYPOINT in entrypoint.guards
        for mutation in entrypoint.mutations:
            writer_role = role_name_for(mutation.writer_principal)
            assert mutation.permission in permissions_for_role(
                PROTECTION_BY_ID[mutation.logical_id], writer_role
            )

    assert mutation_shape("record_domain_event_with_outbox") == {
        ("S03", SqlPermission.INSERT, "originating_domain_command"),
        ("S04", SqlPermission.INSERT, "originating_domain_command"),
    }
    assert mutation_shape("dispatch_outbox_delivery") == {
        ("S04", SqlPermission.UPDATE, "outbox_dispatcher")
    }
    assert mutation_shape("build_factset") == {
        ("S15", SqlPermission.INSERT, "canonical_view_service"),
        ("S15", SqlPermission.UPDATE, "canonical_view_service"),
        ("S16", SqlPermission.INSERT, "canonical_view_service"),
        ("S16", SqlPermission.UPDATE, "canonical_view_service"),
    }
    assert mutation_shape("seal_factset") == {
        ("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
        ("S02", SqlPermission.INSERT, "command_gateway"),
        ("S02", SqlPermission.UPDATE, "command_gateway"),
        ("S03", SqlPermission.INSERT, "originating_domain_command"),
        ("S04", SqlPermission.INSERT, "originating_domain_command"),
        ("S15", SqlPermission.UPDATE, "canonical_view_service"),
    }
    assert mutation_shape("accept_external_execution") == {
        ("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
        ("S02", SqlPermission.INSERT, "command_gateway"),
        ("S02", SqlPermission.UPDATE, "command_gateway"),
        ("S03", SqlPermission.INSERT, "originating_domain_command"),
        ("S04", SqlPermission.INSERT, "originating_domain_command"),
        ("S14", SqlPermission.INSERT, "canonical_fact_service"),
        ("S44", SqlPermission.INSERT, "execution_service"),
        ("S44", SqlPermission.UPDATE, "execution_service"),
    }
    assert mutation_shape("start_or_resume_session") == {
        ("S01", SqlPermission.UPDATE, "decision_state_coordinator"),
        ("S02", SqlPermission.INSERT, "command_gateway"),
        ("S02", SqlPermission.UPDATE, "command_gateway"),
        ("S03", SqlPermission.INSERT, "originating_domain_command"),
        ("S04", SqlPermission.INSERT, "originating_domain_command"),
        ("S44", SqlPermission.INSERT, "execution_service"),
        ("S44", SqlPermission.UPDATE, "execution_service"),
        ("S45", SqlPermission.INSERT, "execution_service"),
    }
    assert mutation_shape("revoke_safety_artifact") == {
        ("S50", SqlPermission.INSERT, "safety_registry"),
        ("S51", SqlPermission.UPDATE, "safety_registry"),
    }

    build = ENTRYPOINT_BY_ID["build_factset"]
    seal = ENTRYPOINT_BY_ID["seal_factset"]
    assert build.lock_order == (LockTarget.BUILD,)
    assert LockTarget.USER not in build.lock_order
    assert LockTarget.REGISTRY_SHARED not in build.lock_order
    assert seal.lock_order == (LockTarget.USER, LockTarget.BUILD)

    external = ENTRYPOINT_BY_ID["accept_external_execution"]
    start = ENTRYPOINT_BY_ID["start_or_resume_session"]
    assert external.lock_order == (LockTarget.USER, LockTarget.EXECUTION)
    assert GuardRequirement.ACTUAL_FACT_ACCEPTANCE in external.guards
    assert GuardRequirement.REGISTRY_GATE not in external.guards
    assert start.lock_order == (
        LockTarget.REGISTRY_SHARED,
        LockTarget.USER,
        LockTarget.EXECUTION,
    )
    assert GuardRequirement.CURRENT_AUTHORIZATION in start.guards
    assert GuardRequirement.REGISTRY_GATE in start.guards

    revoke = ENTRYPOINT_BY_ID["revoke_safety_artifact"]
    assert revoke.lock_order == (LockTarget.REGISTRY_EXCLUSIVE,)
