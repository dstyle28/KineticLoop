"""migrated SafetyRegistry integration and role-owner hardening"""

from alembic import op

revision = "a3f91c7d2e10"
down_revision = "76fd67f76bd4"
branch_labels = None
depends_on = None

PROTECTED_ROLES = (
    "kl_migration_owner",
    "kl_writer_safety_registry",
    "kl_application",
    "kl_auditor",
    "kl_trusted_admin",
)

SHARED_ROUTINES = (
    "registry_guard_publish_manifest",
    "registry_guard_commit_bundle",
    "registry_guard_reauthorize",
    "registry_guard_start_session",
    "registry_guard_resume_session",
    "registry_guard_continue_session",
)

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
      RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_MISSING:%', role_name;
    END IF;
    IF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb
       OR role_record.rolcreaterole OR role_record.rolinherit
       OR role_record.rolreplication OR role_record.rolbypassrls THEN
      RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_UNSAFE:%', role_name;
    END IF;
  END LOOP;

  SELECT count(*) INTO unsafe_memberships
  FROM pg_auth_members memberships
  JOIN pg_roles parent_role ON parent_role.oid = memberships.roleid
  JOIN pg_roles member_role ON member_role.oid = memberships.member
  WHERE parent_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_writer_safety_registry', 'kl_application',
          'kl_auditor', 'kl_trusted_admin'
        ])
    AND member_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_writer_safety_registry', 'kl_application',
          'kl_auditor', 'kl_trusted_admin'
        ]);
  IF unsafe_memberships <> 0 THEN
    RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_PROTECTED_MEMBERSHIP';
  END IF;

  IF session_user <> 'kl_migration_deployer' THEN
    RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_DEPLOYER:%', session_user;
  END IF;
  IF (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = session_user) THEN
    RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_DEPLOYER_ELEVATED';
  END IF;
  IF NOT pg_has_role(session_user, 'kl_migration_owner', 'SET')
     OR NOT pg_has_role(session_user, 'kl_writer_safety_registry', 'SET') THEN
    RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_DEPLOYER_MEMBERSHIP';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM pg_auth_members memberships
    JOIN pg_roles parent_role ON parent_role.oid = memberships.roleid
    JOIN pg_roles member_role ON member_role.oid = memberships.member
    WHERE member_role.rolname = session_user
      AND parent_role.rolname NOT IN ('kl_migration_owner', 'kl_writer_safety_registry')
      AND memberships.set_option
  ) THEN
    RAISE EXCEPTION 'KL_SAFETY_REGISTRY_ROLE_PREFLIGHT_DEPLOYER_MEMBERSHIP';
  END IF;
END
$preflight$
"""


def _shared_routine_sql(name: str) -> str:
    if name in {"registry_guard_commit_bundle", "registry_guard_reauthorize"}:
        command_eligibility_sql = """
  IF current_manifest_id IS NULL OR active_policy_bundle_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM kineticloop.decision_manifests AS manifest
    WHERE manifest.id = current_manifest_id
      AND manifest.subject_id = p_subject_id
      AND manifest.ref_s05_id = active_policy_bundle_id
      AND manifest.captured_epoch = current_authorization_epoch
      AND manifest.registry_revision_at_publish <= current_revision
      AND manifest.valid_until > authoritative_now
      AND manifest.ref_s49_id = ANY(p_artifact_ids)
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_AUTHORIZATION_INELIGIBLE';
  END IF;
"""
    elif name in {
        "registry_guard_start_session",
        "registry_guard_resume_session",
        "registry_guard_continue_session",
    }:
        command_eligibility_sql = """
  IF NOT EXISTS (
    SELECT 1
    FROM kineticloop.authorization_issuances AS auth
    WHERE auth.subject_id = p_subject_id
      AND auth.valid_from <= authoritative_now
      AND authoritative_now < auth.valid_until
      AND auth.registry_revision_at_issue <= current_revision
      AND auth.registry_state_id = 1
      AND auth.ref_s49_id = ANY(p_artifact_ids)
      AND (auth.validity_certificate ->> 'authorization_epoch')::bigint
            = current_authorization_epoch
      AND NOT EXISTS (
        SELECT 1
        FROM kineticloop.authorization_events AS event
        WHERE event.subject_id = p_subject_id
          AND event.ref_s42_id = auth.id
      )
      AND (
        SELECT count(*)
        FROM kineticloop.authorization_artifact_closure AS closure
        WHERE closure.subject_id = p_subject_id
          AND closure.authorization_id = auth.id
          AND closure.artifact_id = ANY(p_artifact_ids)
          AND closure.valid_from <= authoritative_now
          AND (closure.valid_until IS NULL OR authoritative_now < closure.valid_until)
      ) = cardinality(p_artifact_ids)
      AND (
        SELECT count(*)
        FROM kineticloop.authorization_artifact_closure AS closure
        WHERE closure.subject_id = p_subject_id
          AND closure.authorization_id = auth.id
      ) = cardinality(p_artifact_ids)
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_AUTHORIZATION_INELIGIBLE';
  END IF;
"""
    else:
        command_eligibility_sql = ""
    return f"""
CREATE FUNCTION kineticloop.{name}(
  p_subject_id uuid,
  p_artifact_ids uuid[],
  p_minimum_registry_revision bigint,
  p_lock_timeout_ms integer
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $routine$
DECLARE
  current_revision bigint;
  current_authorization_epoch bigint;
  current_manifest_id uuid;
  active_policy_bundle_id uuid;
  authoritative_now timestamptz;
BEGIN
  IF p_lock_timeout_ms <= 0 THEN
    RAISE EXCEPTION 'KL_REGISTRY_INVALID_LOCK_TIMEOUT';
  END IF;
  IF p_artifact_ids IS NULL OR cardinality(p_artifact_ids) = 0
     OR cardinality(p_artifact_ids) <> (
       SELECT count(DISTINCT value) FROM unnest(p_artifact_ids) AS supplied(value)
     ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_DEPENDENCY_INCOMPLETE';
  END IF;
  PERFORM set_config('lock_timeout', p_lock_timeout_ms::text || 'ms', true);
  SELECT state.registry_revision INTO current_revision
  FROM kineticloop.safety_registry_state AS state
  WHERE state.id = 1
  FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'KL_REGISTRY_UNAVAILABLE';
  END IF;
  IF current_revision < p_minimum_registry_revision THEN
    RAISE EXCEPTION 'KL_REGISTRY_STALE';
  END IF;
  SELECT subject_state.authorization_epoch, subject_state.current_manifest_id,
         subject_state.active_policy_bundle_id
    INTO current_authorization_epoch, current_manifest_id, active_policy_bundle_id
  FROM kineticloop.user_decision_state AS subject_state
  WHERE subject_state.subject_id = p_subject_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'KL_REGISTRY_AUTHORIZATION_INELIGIBLE';
  END IF;
  authoritative_now := clock_timestamp();
  IF (SELECT count(*) FROM kineticloop.safety_artifacts AS artifact
      WHERE artifact.id = ANY(p_artifact_ids)) <> cardinality(p_artifact_ids) THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_UNKNOWN';
  END IF;
  IF EXISTS (
    SELECT 1 FROM kineticloop.safety_artifact_dependencies AS dependency
    WHERE dependency.artifact_id = ANY(p_artifact_ids)
      AND NOT dependency.dependency_artifact_id = ANY(p_artifact_ids)
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_DEPENDENCY_INCOMPLETE';
  END IF;
  IF EXISTS (
    SELECT 1 FROM kineticloop.safety_artifacts AS artifact
    WHERE artifact.id = ANY(p_artifact_ids)
      AND (artifact.valid_from IS NULL OR artifact.validity_kind IS NULL
        OR (artifact.validity_kind = 'BOUNDED' AND artifact.valid_until IS NULL))
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_VALIDITY_UNDEFINED';
  END IF;
  IF EXISTS (
    SELECT 1 FROM kineticloop.safety_artifacts AS artifact
    WHERE artifact.id = ANY(p_artifact_ids)
      AND (authoritative_now < artifact.valid_from
        OR (artifact.valid_until IS NOT NULL AND authoritative_now >= artifact.valid_until))
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_EXPIRED';
  END IF;
  IF EXISTS (
    SELECT 1 FROM kineticloop.artifact_revocation_events AS revocation
    WHERE revocation.ref_s49_id = ANY(p_artifact_ids)
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_REVOKED';
  END IF;
{command_eligibility_sql}
  RETURN current_revision;
EXCEPTION
  WHEN lock_not_available OR query_canceled THEN
    RAISE EXCEPTION 'KL_REGISTRY_TIMEOUT';
END
$routine$
"""


REVOKE_ROUTINE_SQL = """
CREATE FUNCTION kineticloop.registry_revoke_artifact(
  p_artifact_id uuid,
  p_artifact_content_hash text,
  p_effective_at timestamptz,
  p_reason_code text,
  p_revocation_payload_hash text,
  p_command_key text,
  p_request_hash text,
  p_causation_incident_id uuid,
  p_lock_timeout_ms integer
) RETURNS TABLE(
  revocation_id uuid,
  registry_revision bigint,
  artifact_id uuid,
  effective_at timestamptz,
  recorded_at timestamptz,
  operator_identity text,
  outbox_delivery_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $routine$
DECLARE
  current_revision bigint;
  stored_receipt record;
  artifact_hash text;
  new_revocation_id uuid;
  new_revision bigint;
  new_recorded_at timestamptz;
  new_delivery_id uuid;
  canonical_reason_code text;
BEGIN
  IF NOT pg_has_role(session_user, 'kl_trusted_admin', 'MEMBER') THEN
    RAISE EXCEPTION 'KL_REGISTRY_COMMAND_NOT_AUTHORIZED';
  END IF;
  canonical_reason_code := normalize(p_reason_code, NFC);
  IF p_lock_timeout_ms <= 0 OR p_effective_at IS NULL
     OR p_reason_code IS NULL OR btrim(p_reason_code) = ''
     OR p_command_key IS NULL OR btrim(p_command_key) = ''
     OR p_request_hash IS NULL OR p_request_hash !~ '^[0-9a-f]{64}$'
     OR p_revocation_payload_hash IS NULL
     OR p_revocation_payload_hash IS DISTINCT FROM encode(
       sha256(convert_to(
         '{"effective_at":"'
         || to_char(p_effective_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
         || '","reason_code":' || to_json(canonical_reason_code)::text || '}',
         'UTF8'
       )),
       'hex'
     ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_INVALID_ARGUMENT';
  END IF;
  PERFORM set_config('lock_timeout', p_lock_timeout_ms::text || 'ms', true);
  SELECT state.registry_revision INTO current_revision
  FROM kineticloop.safety_registry_state AS state
  WHERE state.id = 1
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'KL_REGISTRY_UNAVAILABLE';
  END IF;

  SELECT receipt.* INTO stored_receipt
  FROM kineticloop.registry_management_receipts AS receipt
  WHERE receipt.command_key = p_command_key;
  IF FOUND THEN
    IF stored_receipt.request_hash IS DISTINCT FROM p_request_hash THEN
      RAISE EXCEPTION 'KL_REGISTRY_IDEMPOTENCY_CONFLICT';
    END IF;
    RETURN QUERY SELECT stored_receipt.revocation_id, stored_receipt.registry_revision,
      stored_receipt.artifact_id, stored_receipt.effective_at, stored_receipt.recorded_at,
      stored_receipt.operator_identity, stored_receipt.outbox_delivery_id;
    RETURN;
  END IF;

  SELECT artifact.content_hash INTO artifact_hash
  FROM kineticloop.safety_artifacts AS artifact
  WHERE artifact.id = p_artifact_id;
  IF NOT FOUND OR artifact_hash IS DISTINCT FROM p_artifact_content_hash THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_UNKNOWN';
  END IF;
  IF EXISTS (
    SELECT 1 FROM kineticloop.artifact_revocation_events AS revocation
    WHERE revocation.ref_s49_id = p_artifact_id
  ) THEN
    RAISE EXCEPTION 'KL_REGISTRY_ARTIFACT_REVOKED';
  END IF;

  new_revocation_id := gen_random_uuid();
  new_revision := current_revision + 1;
  new_delivery_id := gen_random_uuid();
  new_recorded_at := clock_timestamp();
  INSERT INTO kineticloop.artifact_revocation_events (
    id, content_hash, reason_code, revocation_payload_hash, effective_at, recorded_at,
    management_command_identity, registry_revision, ref_s49_id, registry_state_id,
    operator_identity, command_key, request_hash, causation_incident_id,
    outbox_delivery_id
  ) VALUES (
    new_revocation_id, p_artifact_content_hash, canonical_reason_code,
    p_revocation_payload_hash, p_effective_at, new_recorded_at, p_command_key, new_revision,
    p_artifact_id, 1, session_user, p_command_key, p_request_hash,
    p_causation_incident_id, new_delivery_id
  );

  UPDATE kineticloop.safety_registry_state
  SET registry_revision = new_revision, last_revocation_id = new_revocation_id
  WHERE id = 1;
  INSERT INTO kineticloop.registry_management_receipts (
    command_key, request_hash, revocation_id, registry_revision, artifact_id,
    effective_at, recorded_at, operator_identity, causation_incident_id,
    outbox_delivery_id
  ) VALUES (
    p_command_key, p_request_hash, new_revocation_id, new_revision, p_artifact_id,
    p_effective_at, new_recorded_at, session_user, p_causation_incident_id,
    new_delivery_id
  );
  INSERT INTO kineticloop.registry_audit_events (
    event_id, revocation_id, operator_identity, causation_incident_id
  ) VALUES (gen_random_uuid(), new_revocation_id, session_user, p_causation_incident_id);
  INSERT INTO kineticloop.registry_outbox (delivery_id, revocation_id)
  VALUES (new_delivery_id, new_revocation_id);

  RETURN QUERY SELECT new_revocation_id, new_revision, p_artifact_id,
    p_effective_at, new_recorded_at, session_user::text, new_delivery_id;
EXCEPTION
  WHEN lock_not_available OR query_canceled THEN
    RAISE EXCEPTION 'KL_REGISTRY_TIMEOUT';
END
$routine$
"""


def upgrade() -> None:
    # This catalog-only block must remain the first successor action.
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("GRANT USAGE ON SCHEMA kineticloop TO kl_trusted_admin")
    op.execute("""
        ALTER TABLE kineticloop.artifact_revocation_events
          ADD COLUMN operator_identity text,
          ADD COLUMN command_key text,
          ADD COLUMN request_hash text,
          ADD COLUMN causation_incident_id uuid,
          ADD COLUMN outbox_delivery_id uuid
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_s50_command_key
        ON kineticloop.artifact_revocation_events(command_key)
        WHERE command_key IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_s50_outbox_delivery_id
        ON kineticloop.artifact_revocation_events(outbox_delivery_id)
        WHERE outbox_delivery_id IS NOT NULL
    """)
    op.execute("""
        CREATE TABLE kineticloop.registry_management_receipts (
          command_key text PRIMARY KEY,
          request_hash text NOT NULL,
          revocation_id uuid NOT NULL UNIQUE REFERENCES kineticloop.artifact_revocation_events(id),
          registry_revision bigint NOT NULL UNIQUE CHECK (registry_revision > 0),
          artifact_id uuid NOT NULL REFERENCES kineticloop.safety_artifacts(id),
          effective_at timestamptz NOT NULL,
          recorded_at timestamptz NOT NULL,
          operator_identity text NOT NULL,
          causation_incident_id uuid NOT NULL,
          outbox_delivery_id uuid NOT NULL UNIQUE
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.registry_audit_events (
          event_id uuid PRIMARY KEY,
          revocation_id uuid NOT NULL UNIQUE REFERENCES kineticloop.artifact_revocation_events(id),
          operator_identity text NOT NULL,
          causation_incident_id uuid NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.registry_outbox (
          delivery_id uuid PRIMARY KEY,
          revocation_id uuid NOT NULL UNIQUE REFERENCES kineticloop.artifact_revocation_events(id),
          recorded_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
          delivered_at timestamptz
        )
    """)
    op.execute("REVOKE ALL ON kineticloop.registry_management_receipts FROM PUBLIC")
    op.execute("REVOKE ALL ON kineticloop.registry_audit_events FROM PUBLIC")
    op.execute("REVOKE ALL ON kineticloop.registry_outbox FROM PUBLIC")
    op.execute(
        "GRANT SELECT, INSERT ON kineticloop.registry_management_receipts TO kl_writer_safety_registry"
    )
    op.execute(
        "GRANT SELECT, INSERT ON kineticloop.registry_audit_events TO kl_writer_safety_registry"
    )
    op.execute("GRANT SELECT, INSERT ON kineticloop.registry_outbox TO kl_writer_safety_registry")
    # PostgreSQL requires UPDATE privilege for SELECT ... FOR UPDATE. Runtime
    # logins cannot assume this NOLOGIN owner, and the fixed routines never write S01.
    op.execute(
        "GRANT SELECT, UPDATE ON kineticloop.user_decision_state "
        "TO kl_writer_safety_registry"
    )
    op.execute(
        "GRANT SELECT ON kineticloop.decision_manifests, "
        "kineticloop.authorization_issuances, kineticloop.authorization_events, "
        "kineticloop.authorization_artifact_closure TO kl_writer_safety_registry"
    )
    op.execute("GRANT SELECT ON kineticloop.registry_management_receipts TO kl_auditor")
    op.execute("GRANT SELECT ON kineticloop.registry_audit_events TO kl_auditor")
    op.execute("GRANT SELECT ON kineticloop.registry_outbox TO kl_auditor")
    op.execute(
        "CREATE TRIGGER registry_management_receipts_immutable BEFORE UPDATE OR DELETE ON kineticloop.registry_management_receipts FOR EACH ROW EXECUTE FUNCTION kineticloop.reject_immutable_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER registry_audit_events_immutable BEFORE UPDATE OR DELETE ON kineticloop.registry_audit_events FOR EACH ROW EXECUTE FUNCTION kineticloop.reject_immutable_history_mutation()"
    )
    op.execute(
        "CREATE TRIGGER registry_outbox_immutable BEFORE DELETE ON kineticloop.registry_outbox FOR EACH ROW EXECUTE FUNCTION kineticloop.reject_immutable_history_mutation()"
    )
    op.execute("GRANT CREATE ON SCHEMA kineticloop TO kl_writer_safety_registry")
    op.execute("SET LOCAL ROLE kl_writer_safety_registry")
    for name in SHARED_ROUTINES:
        op.execute(_shared_routine_sql(name))
    op.execute(REVOKE_ROUTINE_SQL)
    for name in SHARED_ROUTINES:
        signature = f"kineticloop.{name}(uuid,uuid[],bigint,integer)"
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO kl_application")
    revoke_signature = (
        "kineticloop.registry_revoke_artifact("
        "uuid,text,timestamptz,text,text,text,text,uuid,integer)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {revoke_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {revoke_signature} TO kl_trusted_admin")
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("REVOKE CREATE ON SCHEMA kineticloop FROM kl_writer_safety_registry")


def downgrade() -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_writer_safety_registry")
    op.execute(
        "DROP FUNCTION kineticloop.registry_revoke_artifact(uuid,text,timestamptz,text,text,text,text,uuid,integer)"
    )
    for name in reversed(SHARED_ROUTINES):
        op.execute(f"DROP FUNCTION kineticloop.{name}(uuid,uuid[],bigint,integer)")
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("REVOKE USAGE ON SCHEMA kineticloop FROM kl_trusted_admin")
    op.execute(
        "REVOKE SELECT, UPDATE ON kineticloop.user_decision_state "
        "FROM kl_writer_safety_registry"
    )
    op.execute(
        "REVOKE SELECT ON kineticloop.decision_manifests, "
        "kineticloop.authorization_issuances, kineticloop.authorization_events, "
        "kineticloop.authorization_artifact_closure FROM kl_writer_safety_registry"
    )
    op.execute("DROP TABLE kineticloop.registry_outbox")
    op.execute("DROP TABLE kineticloop.registry_audit_events")
    op.execute("DROP TABLE kineticloop.registry_management_receipts")
    op.execute("DROP INDEX kineticloop.uq_s50_outbox_delivery_id")
    op.execute("DROP INDEX kineticloop.uq_s50_command_key")
    op.execute("""
        ALTER TABLE kineticloop.artifact_revocation_events
          DROP COLUMN outbox_delivery_id,
          DROP COLUMN causation_incident_id,
          DROP COLUMN request_hash,
          DROP COLUMN command_key,
          DROP COLUMN operator_identity
    """)
