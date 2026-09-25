from kineticloop.persistence.immutability import (
    PROTECTION_BY_ID,
    RELATION_PROTECTIONS,
    DatabaseRole,
    SqlPermission,
    StorageClass,
    permissions_for,
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
        application = permissions_for(protection, DatabaseRole.APPLICATION)
        auditor = permissions_for(protection, DatabaseRole.AUDITOR)
        owner = permissions_for(protection, DatabaseRole.COMMAND_OWNER)

        assert application == auditor == frozenset({SqlPermission.SELECT})
        assert SqlPermission.DELETE not in owner
        assert {SqlPermission.SELECT, SqlPermission.INSERT} <= owner
        if protection.storage_class is StorageClass.IMMUTABLE:
            assert owner == frozenset({SqlPermission.SELECT, SqlPermission.INSERT})
        else:
            assert owner == frozenset(
                {SqlPermission.SELECT, SqlPermission.INSERT, SqlPermission.UPDATE}
            )

        sql = render_permission_sql(
            protection,
            schema="kineticloop",
            application_role="kl_application",
            auditor_role="kl_auditor",
        )
        assert f"REVOKE ALL ON TABLE kineticloop.{protection.table_name} FROM PUBLIC;" in sql
        assert f"TO {role_name_for(protection)};" in sql
        if protection.storage_class is StorageClass.IMMUTABLE:
            assert "GRANT SELECT, INSERT ON TABLE" in sql
            assert "GRANT SELECT, INSERT, UPDATE ON TABLE" not in sql


def test_build_to_immutable_relations_are_explicit() -> None:
    assert {
        row.logical_id
        for row in RELATION_PROTECTIONS
        if row.storage_class is StorageClass.BUILD_TO_IMMUTABLE
    } == {"S15", "S16"}
    assert {
        row.logical_id
        for row in RELATION_PROTECTIONS
        if row.storage_class is StorageClass.BUILD
    } == {"S23"}
