"""production, test, and evaluation subject namespace isolation"""

from alembic import op

revision = "d4c1a9e7b203"
down_revision = "b6e4d8a1c927"
branch_labels = None
depends_on = None

PREFLIGHT_SQL = """
DO $preflight$
DECLARE
  role_name text;
  role_record record;
  unsafe_memberships bigint;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
    'kl_subject_test', 'kl_subject_evaluation'
  ]
  LOOP
    SELECT * INTO role_record FROM pg_roles WHERE rolname = role_name;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_MISSING:%', role_name;
    END IF;
    IF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb
       OR role_record.rolcreaterole OR role_record.rolinherit
       OR role_record.rolreplication OR role_record.rolbypassrls THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_UNSAFE:%', role_name;
    END IF;
  END LOOP;

  SELECT count(*) INTO unsafe_memberships
  FROM pg_roles parent_role
  CROSS JOIN pg_roles member_role
  WHERE parent_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
          'kl_subject_test', 'kl_subject_evaluation'
        ])
    AND member_role.rolname = ANY(ARRAY[
          'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
          'kl_subject_test', 'kl_subject_evaluation'
        ])
    AND parent_role.oid <> member_role.oid
    AND pg_has_role(member_role.oid, parent_role.oid, 'MEMBER');
  IF unsafe_memberships <> 0 THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_PROTECTED_MEMBERSHIP';
  END IF;

  IF session_user <> 'kl_migration_deployer'
     OR (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname=session_user)
     OR (SELECT count(*)
         FROM pg_auth_members memberships
         JOIN pg_roles member_role ON member_role.oid=memberships.member
         WHERE member_role.rolname=session_user) <> 2
     OR EXISTS (
       SELECT 1 FROM pg_auth_members memberships
       JOIN pg_roles parent_role ON parent_role.oid=memberships.roleid
       JOIN pg_roles member_role ON member_role.oid=memberships.member
       WHERE member_role.rolname=session_user
         AND (parent_role.rolname NOT IN ('kl_migration_owner','kl_writer_safety_registry')
              OR NOT memberships.set_option OR memberships.inherit_option
              OR memberships.admin_option)
     )
     OR EXISTS (
       SELECT 1 FROM pg_roles reachable_role
       WHERE reachable_role.rolname <> session_user
         AND reachable_role.rolname NOT IN (
           'kl_migration_owner','kl_writer_safety_registry','pg_database_owner'
         )
         AND pg_has_role(session_user,reachable_role.rolname,'SET')
     )
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_DEPLOYER';
  END IF;
END
$preflight$
"""

REGISTER_SQL = r"""
CREATE FUNCTION kineticloop.subject_scope_register(
  p_subject_id uuid,
  p_namespace text,
  p_policy_id uuid,
  p_environment_id uuid
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  existing_scope record;
BEGIN
  IF NOT pg_has_role(session_user, 'kl_trusted_admin', 'MEMBER') THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_REGISTRATION_DENIED';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_subject_id::text, 17017));

  SELECT * INTO existing_scope FROM kineticloop.subject_scopes
  WHERE subject_id=p_subject_id FOR UPDATE;
  IF FOUND THEN
    IF existing_scope.namespace <> p_namespace
       OR existing_scope.policy_id IS DISTINCT FROM p_policy_id
       OR existing_scope.environment_id IS DISTINCT FROM p_environment_id
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_IMMUTABLE';
    END IF;
    RETURN;
  END IF;
  IF p_namespace NOT IN ('PRODUCTION','TEST','EVALUATION') THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_INVALID';
  END IF;
  IF p_namespace = 'PRODUCTION' AND (p_policy_id IS NOT NULL OR p_environment_id IS NOT NULL)
     OR p_namespace = 'TEST' AND (p_policy_id IS NULL OR p_environment_id IS NULL)
     OR p_namespace = 'EVALUATION' AND (p_policy_id IS NOT NULL OR p_environment_id IS NULL)
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_INVALID';
  END IF;
  IF p_namespace = 'TEST' AND NOT EXISTS (
    SELECT 1 FROM kineticloop.policy_bundles AS policy
    WHERE policy.subject_id=p_subject_id AND policy.id=p_policy_id
      AND lower(policy.policy_namespace) LIKE 'test:%'
  ) THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_TEST_POLICY_REQUIRED';
  END IF;
  IF p_namespace IN ('TEST','EVALUATION') AND (
    EXISTS (SELECT 1 FROM kineticloop.daily_plan_heads WHERE subject_id=p_subject_id)
    OR EXISTS (SELECT 1 FROM kineticloop.authorization_issuances WHERE subject_id=p_subject_id)
    OR EXISTS (SELECT 1 FROM kineticloop.execution_bindings WHERE subject_id=p_subject_id)
    OR EXISTS (SELECT 1 FROM kineticloop.replay_runs WHERE subject_id=p_subject_id)
    OR EXISTS (SELECT 1 FROM kineticloop.replay_artifacts WHERE subject_id=p_subject_id)
  ) THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_EXISTING_STATE';
  END IF;

  INSERT INTO kineticloop.subject_scopes(subject_id,namespace,policy_id,environment_id)
  VALUES (p_subject_id,p_namespace,p_policy_id,p_environment_id);
END
$routine$
"""

LOOKUP_SQL = r"""
CREATE FUNCTION kineticloop.subject_scope_lookup(
  p_expected_namespace text,
  p_subject_id uuid,
  p_object_kind text,
  p_object_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  role_namespace text;
  target_namespace text;
  found_subject uuid;
BEGIN
  role_namespace := CASE
    WHEN pg_has_role(session_user, 'kl_subject_test', 'MEMBER') THEN 'TEST'
    WHEN pg_has_role(session_user, 'kl_subject_evaluation', 'MEMBER') THEN 'EVALUATION'
    WHEN pg_has_role(session_user, 'kl_application', 'MEMBER') THEN 'PRODUCTION'
    ELSE NULL
  END;
  IF role_namespace IS NULL OR role_namespace <> p_expected_namespace THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_DENIED';
  END IF;
  SELECT namespace INTO target_namespace FROM kineticloop.subject_scopes
  WHERE subject_id=p_subject_id;
  target_namespace := coalesce(target_namespace, 'PRODUCTION');
  IF target_namespace <> role_namespace THEN
    RETURN NULL;
  END IF;
  IF role_namespace='EVALUATION' AND p_object_kind NOT IN ('S46','S47')
     OR role_namespace IN ('PRODUCTION','TEST') AND p_object_kind NOT IN ('S38','S42','S45')
  THEN
    RETURN NULL;
  END IF;

  CASE p_object_kind
    WHEN 'S38' THEN SELECT subject_id INTO found_subject FROM kineticloop.daily_plan_heads WHERE subject_id=p_subject_id AND id=p_object_id;
    WHEN 'S42' THEN SELECT subject_id INTO found_subject FROM kineticloop.authorization_issuances WHERE subject_id=p_subject_id AND id=p_object_id;
    WHEN 'S45' THEN SELECT subject_id INTO found_subject FROM kineticloop.execution_bindings WHERE subject_id=p_subject_id AND id=p_object_id;
    WHEN 'S46' THEN SELECT subject_id INTO found_subject FROM kineticloop.replay_runs WHERE subject_id=p_subject_id AND id=p_object_id;
    WHEN 'S47' THEN SELECT subject_id INTO found_subject FROM kineticloop.replay_artifacts WHERE subject_id=p_subject_id AND id=p_object_id;
    ELSE RETURN NULL;
  END CASE;
  IF found_subject IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN jsonb_build_object('kind',p_object_kind,'object_id',p_object_id::text,'subject_id',found_subject::text);
END
$routine$
"""

GUARD_SQL = r"""
CREATE FUNCTION kineticloop.enforce_subject_storage_scope() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $guard$
DECLARE
  subject_namespace text;
  isolated_policy uuid;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.subject_id::text, 17017));
  SELECT namespace,policy_id INTO subject_namespace,isolated_policy
  FROM kineticloop.subject_scopes WHERE subject_id=NEW.subject_id;
  subject_namespace := coalesce(subject_namespace,'PRODUCTION');

  IF TG_TABLE_NAME IN ('replay_runs','replay_artifacts') THEN
    IF subject_namespace <> 'EVALUATION' THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_EVALUATION_STORAGE_DENIED';
    END IF;
    RETURN NEW;
  END IF;
  IF subject_namespace = 'EVALUATION' THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_LIVE_STORAGE_DENIED';
  END IF;
  IF TG_TABLE_NAME = 'authorization_issuances' THEN
    IF subject_namespace='TEST' AND (NEW.scope IS DISTINCT FROM 'TEST_ONLY' OR NEW.ref_s05_id IS DISTINCT FROM isolated_policy) THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_TEST_AUTHORIZATION_DENIED';
    ELSIF subject_namespace='PRODUCTION' AND NEW.scope='TEST_ONLY' THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_TEST_AUTHORIZATION_DENIED';
    END IF;
  ELSIF TG_TABLE_NAME = 'execution_bindings' THEN
    IF subject_namespace='TEST' AND NEW.execution_scope IS DISTINCT FROM 'TEST_ONLY'
       OR subject_namespace='PRODUCTION' AND NEW.execution_scope='TEST_ONLY'
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_EXECUTION_DENIED';
    END IF;
  END IF;
  RETURN NEW;
END
$guard$
"""


def upgrade() -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("""
        CREATE TABLE kineticloop.subject_scopes (
          subject_id uuid PRIMARY KEY,
          namespace text NOT NULL CHECK (namespace IN ('PRODUCTION','TEST','EVALUATION')),
          policy_id uuid,
          environment_id uuid,
          registered_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
          CONSTRAINT fk_subject_scope_test_policy FOREIGN KEY(subject_id,policy_id)
            REFERENCES kineticloop.policy_bundles(subject_id,id),
          CONSTRAINT ck_subject_scope_binding CHECK (
            namespace='PRODUCTION' AND policy_id IS NULL AND environment_id IS NULL
            OR namespace='TEST' AND policy_id IS NOT NULL AND environment_id IS NOT NULL
            OR namespace='EVALUATION' AND policy_id IS NULL AND environment_id IS NOT NULL
          )
        )
    """)
    op.execute("REVOKE ALL ON kineticloop.subject_scopes FROM PUBLIC")
    op.execute("GRANT SELECT ON kineticloop.subject_scopes TO kl_auditor")
    op.execute("REVOKE SELECT ON kineticloop.daily_plan_heads, kineticloop.authorization_issuances, kineticloop.execution_bindings, kineticloop.replay_runs, kineticloop.replay_artifacts FROM kl_application")
    op.execute(REGISTER_SQL)
    op.execute(LOOKUP_SQL)
    op.execute(GUARD_SQL)
    op.execute(
        "REVOKE ALL ON FUNCTION kineticloop.enforce_subject_storage_scope() FROM PUBLIC"
    )
    for table in ("daily_plan_heads", "authorization_issuances", "execution_bindings", "replay_runs", "replay_artifacts"):
        op.execute(f"CREATE TRIGGER subject_storage_scope BEFORE INSERT OR UPDATE ON kineticloop.{table} FOR EACH ROW EXECUTE FUNCTION kineticloop.enforce_subject_storage_scope()")
    register_signature = "kineticloop.subject_scope_register(uuid,text,uuid,uuid)"
    lookup_signature = "kineticloop.subject_scope_lookup(text,uuid,text,uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {register_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {register_signature} TO kl_trusted_admin")
    op.execute(f"REVOKE ALL ON FUNCTION {lookup_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {lookup_signature} TO kl_application, kl_subject_test, kl_subject_evaluation")
    op.execute("GRANT USAGE ON SCHEMA kineticloop TO kl_subject_test, kl_subject_evaluation")


def downgrade() -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    for table in ("daily_plan_heads", "authorization_issuances", "execution_bindings", "replay_runs", "replay_artifacts"):
        op.execute(f"DROP TRIGGER subject_storage_scope ON kineticloop.{table}")
    op.execute("DROP FUNCTION kineticloop.enforce_subject_storage_scope()")
    op.execute("DROP FUNCTION kineticloop.subject_scope_lookup(text,uuid,text,uuid)")
    op.execute("DROP FUNCTION kineticloop.subject_scope_register(uuid,text,uuid,uuid)")
    op.execute("GRANT SELECT ON kineticloop.daily_plan_heads, kineticloop.authorization_issuances, kineticloop.execution_bindings, kineticloop.replay_runs, kineticloop.replay_artifacts TO kl_application")
    op.execute(
        "REVOKE USAGE ON SCHEMA kineticloop FROM kl_subject_test, kl_subject_evaluation"
    )
    op.execute("DROP TABLE kineticloop.subject_scopes")
