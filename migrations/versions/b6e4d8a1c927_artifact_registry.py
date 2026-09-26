"""trusted artifact registration and bounded dependency admission"""

from alembic import op

revision = "b6e4d8a1c927"
down_revision = "a3f91c7d2e10"
branch_labels = None
depends_on = None

MAX_DEPENDENCY_NODES = 128
MAX_DEPENDENCY_DEPTH = 16

PREFLIGHT_SQL = """
DO $preflight$
DECLARE
  role_name text;
  role_record record;
  unsafe_memberships bigint;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'kl_migration_owner', 'kl_writer_safety_registry', 'kl_application',
    'kl_auditor', 'kl_trusted_admin'
  ]
  LOOP
    SELECT * INTO role_record FROM pg_roles WHERE rolname = role_name;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_MISSING:%', role_name;
    END IF;
    IF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb
       OR role_record.rolcreaterole OR role_record.rolinherit
       OR role_record.rolreplication OR role_record.rolbypassrls THEN
      RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_UNSAFE:%', role_name;
    END IF;
  END LOOP;

  SELECT count(*) INTO unsafe_memberships
  FROM pg_roles parent_role
  CROSS JOIN pg_roles member_role
  WHERE parent_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_writer_safety_registry', 'kl_application',
          'kl_auditor', 'kl_trusted_admin'
        ])
    AND member_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_writer_safety_registry', 'kl_application',
          'kl_auditor', 'kl_trusted_admin'
        ])
    AND parent_role.oid <> member_role.oid
    AND pg_has_role(member_role.oid, parent_role.oid, 'MEMBER');
  IF unsafe_memberships <> 0 THEN
    RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_PROTECTED_MEMBERSHIP';
  END IF;

  IF session_user <> 'kl_migration_deployer' THEN
    RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_DEPLOYER:%', session_user;
  END IF;
  IF (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = session_user) THEN
    RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_DEPLOYER_ELEVATED';
  END IF;
  IF (SELECT count(*)
      FROM pg_auth_members memberships
      JOIN pg_roles member_role ON member_role.oid = memberships.member
      WHERE member_role.rolname = session_user) <> 2
     OR EXISTS (
    SELECT 1
    FROM pg_auth_members memberships
    JOIN pg_roles parent_role ON parent_role.oid = memberships.roleid
    JOIN pg_roles member_role ON member_role.oid = memberships.member
    WHERE member_role.rolname = session_user
      AND (
        parent_role.rolname NOT IN ('kl_migration_owner', 'kl_writer_safety_registry')
        OR NOT memberships.set_option
        OR memberships.inherit_option
        OR memberships.admin_option
      )
  )
     OR EXISTS (
    SELECT 1
    FROM pg_roles reachable_role
    WHERE reachable_role.rolname <> session_user
      AND reachable_role.rolname NOT IN (
        'kl_migration_owner', 'kl_writer_safety_registry', 'pg_database_owner'
      )
      AND pg_has_role(session_user, reachable_role.rolname, 'SET')
  ) THEN
    RAISE EXCEPTION 'KL_ARTIFACT_REGISTRY_ROLE_PREFLIGHT_DEPLOYER_MEMBERSHIP';
  END IF;
END
$preflight$
"""

REGISTER_ROUTINE_SQL = f"""
CREATE FUNCTION kineticloop.registry_register_artifact(
  p_artifact_id uuid,
  p_artifact_kind text,
  p_content_hash text,
  p_dependency_ids uuid[],
  p_artifact_identity text,
  p_artifact_version text,
  p_validity_spec text,
  p_lock_timeout_ms integer
) RETURNS TABLE(
  artifact_id uuid,
  registered_at timestamptz,
  operator_identity text,
  replayed boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  current_revision bigint;
  validity jsonb;
  validity_kind text;
  valid_from timestamptz;
  valid_until timestamptz;
  approval_policy text;
  approval_policy_id uuid;
  approval_reason text;
  binding_kind text;
  binding_id uuid;
  policy_id uuid;
  catalog_id uuid;
  release_id uuid;
  new_registered_at timestamptz;
  new_event_id uuid;
  new_delivery_id uuid;
  existing_artifact record;
  existing_dependencies uuid[];
  dependency_count integer;
  maximum_depth integer;
  cycle_found boolean;
BEGIN
  IF NOT pg_has_role(session_user, 'kl_trusted_admin', 'MEMBER') THEN
    RAISE EXCEPTION 'KL_REGISTRY_COMMAND_NOT_AUTHORIZED';
  END IF;
  IF p_lock_timeout_ms IS NULL OR p_lock_timeout_ms <= 0
     OR p_artifact_id IS NULL
     OR p_artifact_kind IS NULL OR btrim(p_artifact_kind) = ''
     OR p_content_hash IS NULL OR p_content_hash !~ '^[0-9a-f]{{64}}$'
     OR p_artifact_identity IS NULL OR btrim(p_artifact_identity) = ''
     OR p_artifact_version IS NULL OR btrim(p_artifact_version) = ''
     OR p_validity_spec IS NULL OR btrim(p_validity_spec) = ''
     OR p_dependency_ids IS NULL
     OR cardinality(p_dependency_ids) <> (
       SELECT count(DISTINCT value) FROM unnest(p_dependency_ids) AS supplied(value)
     ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_INVALID_ARGUMENT';
  END IF;
  BEGIN
    validity := p_validity_spec::jsonb;
    validity_kind := validity ->> 'validity_kind';
    valid_from := (validity ->> 'valid_from')::timestamptz;
    valid_until := (validity ->> 'valid_until')::timestamptz;
    approval_policy := validity ->> 'timeless_approval_policy';
    approval_reason := validity ->> 'timeless_approval_reason';
    binding_kind := validity ->> 'binding_kind';
    binding_id := (validity ->> 'binding_id')::uuid;
  EXCEPTION WHEN OTHERS THEN
    RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
  END;
  IF validity_kind IS NULL OR btrim(validity_kind) = ''
     OR valid_from IS NULL OR binding_kind IS NULL OR btrim(binding_kind) = ''
     OR binding_id IS NULL
     OR coalesce((validity ->> 'closure_complete')::boolean, false) IS NOT TRUE
     OR NOT ((
       (validity_kind = 'BOUNDED' AND valid_until > valid_from
        AND approval_policy IS NULL AND approval_reason IS NULL)
       OR
       (validity_kind = 'TIMELESS' AND valid_until IS NULL
        AND btrim(approval_policy) <> '' AND btrim(approval_reason) <> '')
     ) IS TRUE) THEN
    RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
  END IF;
  IF validity_kind = 'TIMELESS' THEN
    BEGIN
      approval_policy_id := approval_policy::uuid;
    EXCEPTION WHEN OTHERS THEN
      RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
    END;
  END IF;
  IF NOT (
    (p_artifact_kind IN ('POLICY', 'POLICY_BUNDLE') AND binding_kind = 'POLICY_BUNDLE')
    OR (p_artifact_kind IN ('TOOL', 'EXERCISE_CATALOG') AND binding_kind = 'EXERCISE_CATALOG')
    OR (p_artifact_kind IN ('MODEL', 'PROMPT', 'RUNTIME', 'EVALUATION_RELEASE')
        AND binding_kind = 'EVALUATION_RELEASE')
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_INVALID_ARGUMENT';
  END IF;
  policy_id := CASE WHEN binding_kind = 'POLICY_BUNDLE' THEN binding_id END;
  catalog_id := CASE WHEN binding_kind = 'EXERCISE_CATALOG' THEN binding_id END;
  release_id := CASE WHEN binding_kind = 'EVALUATION_RELEASE' THEN binding_id END;

  PERFORM set_config('lock_timeout', p_lock_timeout_ms::text || 'ms', true);
  SELECT state.registry_revision INTO current_revision
  FROM kineticloop.safety_registry_state AS state
  WHERE state.id = 1
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'KL_REGISTRY_UNAVAILABLE';
  END IF;

  SELECT artifact.* INTO existing_artifact
  FROM kineticloop.safety_artifacts AS artifact
  WHERE artifact.id = p_artifact_id;
  IF FOUND THEN
    SELECT coalesce(array_agg(edge.dependency_artifact_id ORDER BY edge.dependency_artifact_id), '{{}}'::uuid[])
      INTO existing_dependencies
    FROM kineticloop.safety_artifact_dependencies AS edge
    WHERE edge.artifact_id = p_artifact_id;
    IF existing_artifact.artifact_kind IS DISTINCT FROM p_artifact_kind
       OR existing_artifact.content_hash IS DISTINCT FROM p_content_hash
       OR existing_artifact.artifact_identity IS DISTINCT FROM p_artifact_identity
       OR existing_artifact.artifact_version IS DISTINCT FROM p_artifact_version
       OR existing_artifact.validity_kind IS DISTINCT FROM validity_kind
       OR existing_artifact.valid_from IS DISTINCT FROM valid_from
       OR existing_artifact.valid_until IS DISTINCT FROM valid_until
       OR existing_artifact.timeless_approval_policy IS DISTINCT FROM approval_policy
       OR existing_artifact.timeless_approval_reason IS DISTINCT FROM approval_reason
       OR existing_artifact.ref_s05_id IS DISTINCT FROM policy_id
       OR existing_artifact.ref_s19_id IS DISTINCT FROM catalog_id
       OR existing_artifact.ref_s48_id IS DISTINCT FROM release_id
       OR existing_dependencies IS DISTINCT FROM (
         SELECT coalesce(array_agg(value ORDER BY value), '{{}}'::uuid[])
         FROM unnest(p_dependency_ids) AS supplied(value)
       ) THEN
      RAISE EXCEPTION 'KL_REGISTRY_IMMUTABLE_ARTIFACT';
    END IF;
    RETURN QUERY SELECT existing_artifact.id, existing_artifact.recorded_at,
      receipt.operator_identity, true
    FROM kineticloop.registry_artifact_receipts AS receipt
    WHERE receipt.artifact_id = existing_artifact.id;
    RETURN;
  END IF;

  IF p_artifact_id = ANY(p_dependency_ids) THEN
    RAISE EXCEPTION 'KL_REGISTRY_DEPENDENCY_CYCLE';
  END IF;
  IF (SELECT count(*) FROM kineticloop.safety_artifacts
      WHERE id = ANY(p_dependency_ids)) <> cardinality(p_dependency_ids) THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_UNKNOWN';
  END IF;
  IF cardinality(p_dependency_ids) > {MAX_DEPENDENCY_NODES} THEN
    RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
  END IF;
  IF validity_kind = 'TIMELESS' THEN
    IF NOT EXISTS (
      SELECT 1 FROM kineticloop.safety_artifacts AS policy
      WHERE policy.id = approval_policy_id
    ) THEN
      RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_UNKNOWN';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM kineticloop.safety_artifacts AS policy
      WHERE policy.id = approval_policy_id
        AND policy.artifact_kind IN ('POLICY', 'POLICY_BUNDLE')
    ) OR NOT (approval_policy_id = ANY(p_dependency_ids)) THEN
      RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
    END IF;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM kineticloop.safety_artifact_dependencies AS edge
    WHERE edge.artifact_id = ANY(p_dependency_ids)
      AND NOT edge.dependency_artifact_id = ANY(p_dependency_ids)
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_DEPENDENCY_INCOMPLETE';
  END IF;

  WITH RECURSIVE walk(node_id, depth) AS (
    SELECT supplied.value, 0
    FROM unnest(p_dependency_ids) AS supplied(value)
    UNION
    SELECT edge.dependency_artifact_id, walk.depth + 1
    FROM walk
    JOIN kineticloop.safety_artifact_dependencies AS edge
      ON edge.artifact_id = walk.node_id
    WHERE walk.depth < {MAX_DEPENDENCY_DEPTH + 1}
  )
  SELECT count(DISTINCT node_id), coalesce(max(depth), 0)
    INTO dependency_count, maximum_depth
  FROM walk;
  WITH RECURSIVE reach(origin_id, node_id) AS (
    SELECT edge.artifact_id, edge.dependency_artifact_id
    FROM kineticloop.safety_artifact_dependencies AS edge
    WHERE edge.artifact_id = ANY(p_dependency_ids)
    UNION
    SELECT reach.origin_id, edge.dependency_artifact_id
    FROM reach
    JOIN kineticloop.safety_artifact_dependencies AS edge
      ON edge.artifact_id = reach.node_id
  )
  SELECT EXISTS (SELECT 1 FROM reach WHERE origin_id = node_id)
    INTO cycle_found;
  IF cycle_found IS TRUE THEN
    RAISE EXCEPTION 'KL_REGISTRY_DEPENDENCY_CYCLE';
  END IF;
  IF dependency_count > {MAX_DEPENDENCY_NODES}
     OR maximum_depth > {MAX_DEPENDENCY_DEPTH} THEN
    RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
  END IF;

  new_registered_at := clock_timestamp();
  new_event_id := gen_random_uuid();
  new_delivery_id := gen_random_uuid();
  INSERT INTO kineticloop.safety_artifacts (
    id, recorded_at, known_at, effective_at, artifact_kind, artifact_identity,
    artifact_version, content_hash, validity_kind, valid_from, valid_until,
    timeless_approval_policy, timeless_approval_reason, ref_s05_id, ref_s19_id,
    ref_s48_id, status, typed_payload
  ) VALUES (
    p_artifact_id, new_registered_at, new_registered_at, valid_from,
    p_artifact_kind, p_artifact_identity, p_artifact_version, p_content_hash,
    validity_kind, valid_from, valid_until, approval_policy, approval_reason,
    policy_id, catalog_id, release_id, 'REGISTERED',
    jsonb_build_object('registration_validity_spec', validity)
  );
  INSERT INTO kineticloop.safety_artifact_dependencies (
    artifact_id, dependency_artifact_id
  ) SELECT p_artifact_id, supplied.value
    FROM unnest(p_dependency_ids) AS supplied(value);
  INSERT INTO kineticloop.registry_artifact_receipts (
    artifact_id, artifact_kind, artifact_identity, artifact_version, content_hash,
    operator_identity, registered_at, event_id, outbox_delivery_id
  ) VALUES (
    p_artifact_id, p_artifact_kind, p_artifact_identity, p_artifact_version,
    p_content_hash, session_user, new_registered_at, new_event_id, new_delivery_id
  );
  INSERT INTO kineticloop.artifact_registration_events (
    event_id, artifact_id, operator_identity, registered_at
  ) VALUES (new_event_id, p_artifact_id, session_user, new_registered_at);
  INSERT INTO kineticloop.artifact_registration_outbox (
    delivery_id, event_id, artifact_id, recorded_at
  ) VALUES (new_delivery_id, new_event_id, p_artifact_id, new_registered_at);

  RETURN QUERY SELECT p_artifact_id, new_registered_at, session_user::text, false;
EXCEPTION
  WHEN lock_not_available OR query_canceled THEN
    RAISE EXCEPTION 'KL_REGISTRY_TIMEOUT';
  WHEN unique_violation THEN
    RAISE EXCEPTION 'KL_REGISTRY_IMMUTABLE_ARTIFACT';
END
$routine$
"""


def upgrade() -> None:
    # Catalog-only role validation must precede every object change.
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("ALTER TABLE kineticloop.safety_artifacts DROP CONSTRAINT ck_s49_exact_typed_binding")
    op.execute("ALTER TABLE kineticloop.safety_artifacts DROP CONSTRAINT ck_s49_validity_spec")
    op.execute("""
        ALTER TABLE kineticloop.safety_artifacts
        ADD CONSTRAINT ck_s49_validity_spec CHECK ((
          (validity_kind = 'BOUNDED' AND valid_until > valid_from
            AND timeless_approval_policy IS NULL AND timeless_approval_reason IS NULL)
          OR (validity_kind = 'TIMELESS' AND valid_until IS NULL
            AND btrim(timeless_approval_policy) <> ''
            AND btrim(timeless_approval_reason) <> '')
        ) IS TRUE)
    """)
    op.execute("""
        ALTER TABLE kineticloop.safety_artifacts
        ADD CONSTRAINT ck_s49_exact_typed_binding CHECK (
          (artifact_kind IN ('POLICY', 'POLICY_BUNDLE') AND ref_s05_id IS NOT NULL
            AND ref_s19_id IS NULL AND ref_s48_id IS NULL)
          OR (artifact_kind IN ('TOOL', 'EXERCISE_CATALOG') AND ref_s05_id IS NULL
            AND ref_s19_id IS NOT NULL AND ref_s48_id IS NULL)
          OR (artifact_kind IN ('MODEL', 'PROMPT', 'RUNTIME', 'EVALUATION_RELEASE')
            AND ref_s05_id IS NULL AND ref_s19_id IS NULL AND ref_s48_id IS NOT NULL)
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.registry_artifact_receipts (
          artifact_id uuid PRIMARY KEY REFERENCES kineticloop.safety_artifacts(id),
          artifact_kind text NOT NULL,
          artifact_identity text NOT NULL,
          artifact_version text NOT NULL,
          content_hash text NOT NULL,
          operator_identity text NOT NULL,
          registered_at timestamptz NOT NULL,
          event_id uuid NOT NULL UNIQUE,
          outbox_delivery_id uuid NOT NULL UNIQUE
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.artifact_registration_events (
          event_id uuid PRIMARY KEY,
          artifact_id uuid NOT NULL UNIQUE REFERENCES kineticloop.safety_artifacts(id),
          operator_identity text NOT NULL,
          registered_at timestamptz NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.artifact_registration_outbox (
          delivery_id uuid PRIMARY KEY,
          event_id uuid NOT NULL UNIQUE REFERENCES kineticloop.artifact_registration_events(event_id),
          artifact_id uuid NOT NULL UNIQUE REFERENCES kineticloop.safety_artifacts(id),
          recorded_at timestamptz NOT NULL,
          delivered_at timestamptz
        )
    """)
    for table in (
        "registry_artifact_receipts",
        "artifact_registration_events",
        "artifact_registration_outbox",
    ):
        op.execute(f"REVOKE ALL ON kineticloop.{table} FROM PUBLIC")
        op.execute(f"GRANT SELECT, INSERT ON kineticloop.{table} TO kl_writer_safety_registry")
        op.execute(f"GRANT SELECT ON kineticloop.{table} TO kl_auditor")
    op.execute(
        "CREATE TRIGGER registry_artifact_receipts_immutable BEFORE UPDATE OR DELETE "
        "ON kineticloop.registry_artifact_receipts FOR EACH ROW EXECUTE FUNCTION "
        "kineticloop.reject_immutable_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER artifact_registration_events_immutable BEFORE UPDATE OR DELETE "
        "ON kineticloop.artifact_registration_events FOR EACH ROW EXECUTE FUNCTION "
        "kineticloop.reject_immutable_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER artifact_registration_outbox_immutable BEFORE DELETE "
        "ON kineticloop.artifact_registration_outbox FOR EACH ROW EXECUTE FUNCTION "
        "kineticloop.reject_immutable_history_mutation()"
    )
    op.execute("GRANT CREATE ON SCHEMA kineticloop TO kl_writer_safety_registry")
    op.execute("SET LOCAL ROLE kl_writer_safety_registry")
    op.execute(REGISTER_ROUTINE_SQL)
    signature = (
        "kineticloop.registry_register_artifact("
        "uuid,text,text,uuid[],text,text,text,integer)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO kl_trusted_admin")
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("REVOKE CREATE ON SCHEMA kineticloop FROM kl_writer_safety_registry")


def downgrade() -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_writer_safety_registry")
    op.execute(
        "DROP FUNCTION kineticloop.registry_register_artifact("
        "uuid,text,text,uuid[],text,text,text,integer)"
    )
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("DROP TABLE kineticloop.artifact_registration_outbox")
    op.execute("DROP TABLE kineticloop.artifact_registration_events")
    op.execute("DROP TABLE kineticloop.registry_artifact_receipts")
    op.execute("ALTER TABLE kineticloop.safety_artifacts DROP CONSTRAINT ck_s49_exact_typed_binding")
    op.execute("ALTER TABLE kineticloop.safety_artifacts DROP CONSTRAINT ck_s49_validity_spec")
    op.execute("""
        ALTER TABLE kineticloop.safety_artifacts
        ADD CONSTRAINT ck_s49_validity_spec CHECK (
          (validity_kind = 'BOUNDED' AND valid_until > valid_from
            AND timeless_approval_policy IS NULL AND timeless_approval_reason IS NULL)
          OR (validity_kind = 'TIMELESS' AND valid_until IS NULL
            AND btrim(timeless_approval_policy) <> ''
            AND btrim(timeless_approval_reason) <> '')
        )
    """)
    op.execute("""
        ALTER TABLE kineticloop.safety_artifacts
        ADD CONSTRAINT ck_s49_exact_typed_binding CHECK (
          (artifact_kind = 'POLICY_BUNDLE' AND ref_s05_id IS NOT NULL
            AND ref_s19_id IS NULL AND ref_s48_id IS NULL)
          OR (artifact_kind = 'EXERCISE_CATALOG' AND ref_s05_id IS NULL
            AND ref_s19_id IS NOT NULL AND ref_s48_id IS NULL)
          OR (artifact_kind = 'EVALUATION_RELEASE' AND ref_s05_id IS NULL
            AND ref_s19_id IS NULL AND ref_s48_id IS NOT NULL)
        )
    """)
