from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    RELATION_PROTECTIONS,
    RUNTIME_ROLE_NAMES,
    DatabaseRole,
    GuardRequirement,
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
