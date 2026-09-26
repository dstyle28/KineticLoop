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
  expected_role text;
  role_record record;
  unsafe_memberships bigint;
BEGIN
  FOR role_name IN
    SELECT rolname FROM pg_roles
    WHERE rolname = ANY(ARRAY[
      'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
      'kl_subject_test', 'kl_subject_evaluation', 'kl_writer_safety_registry'
    ]) OR rolname LIKE 'kl_writer_%'
  LOOP
    SELECT * INTO role_record FROM pg_roles WHERE rolname = role_name;
    IF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb
       OR role_record.rolcreaterole OR role_record.rolinherit
       OR role_record.rolreplication OR role_record.rolbypassrls THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_UNSAFE:%', role_name;
    END IF;
  END LOOP;

  FOREACH role_name IN ARRAY ARRAY[
    'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
    'kl_subject_test', 'kl_subject_evaluation', 'kl_writer_safety_registry'
  ]
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=role_name) THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_MISSING:%', role_name;
    END IF;
  END LOOP;

  SELECT count(*) INTO unsafe_memberships
  FROM pg_roles parent_role CROSS JOIN pg_roles member_role
  WHERE (parent_role.rolname = ANY(ARRAY[
           'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
           'kl_subject_test', 'kl_subject_evaluation'
         ]) OR parent_role.rolname LIKE 'kl_writer_%')
    AND (member_role.rolname = ANY(ARRAY[
           'kl_migration_owner', 'kl_application', 'kl_auditor', 'kl_trusted_admin',
           'kl_subject_test', 'kl_subject_evaluation'
         ]) OR member_role.rolname LIKE 'kl_writer_%')
    AND parent_role.oid <> member_role.oid
    AND pg_has_role(member_role.oid, parent_role.oid, 'MEMBER');
  IF unsafe_memberships <> 0 THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_PREFLIGHT_PROTECTED_MEMBERSHIP';
  END IF;

  FOREACH role_name IN ARRAY ARRAY[
    'kl_production_subject_1_login',
    'kl_test_subject_1_login', 'kl_test_subject_2_login',
    'kl_evaluation_subject_1_login', 'kl_evaluation_subject_2_login'
  ]
  LOOP
    SELECT * INTO role_record FROM pg_roles WHERE rolname=role_name;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_MISSING:%', role_name;
    END IF;
    IF NOT role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolcreatedb
       OR role_record.rolcreaterole OR NOT role_record.rolinherit
       OR role_record.rolreplication OR role_record.rolbypassrls THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_UNSAFE:%', role_name;
    END IF;
    expected_role := CASE
      WHEN role_name LIKE 'kl_production_%' THEN 'kl_application'
      WHEN role_name LIKE 'kl_test_%' THEN 'kl_subject_test'
      ELSE 'kl_subject_evaluation'
    END;
    IF (SELECT count(*) FROM pg_auth_members membership
        JOIN pg_roles member_role ON member_role.oid=membership.member
        WHERE member_role.rolname=role_name) <> 1
       OR NOT EXISTS (
         SELECT 1 FROM pg_auth_members membership
         JOIN pg_roles parent_role ON parent_role.oid=membership.roleid
         JOIN pg_roles member_role ON member_role.oid=membership.member
         WHERE member_role.rolname=role_name AND parent_role.rolname=expected_role
           AND NOT membership.admin_option AND membership.inherit_option
           AND NOT membership.set_option
       )
       OR EXISTS (
         SELECT 1 FROM pg_roles writer_role
         WHERE writer_role.rolname LIKE 'kl_writer_%'
           AND (pg_has_role(role_name,writer_role.rolname,'MEMBER')
                OR pg_has_role(role_name,writer_role.rolname,'SET'))
       )
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_MEMBERSHIP:%', role_name;
    END IF;
    IF EXISTS (
         SELECT 1 FROM pg_class protected
         JOIN pg_namespace schema ON schema.oid=protected.relnamespace
         WHERE schema.nspname='kineticloop'
           AND protected.relname=ANY(ARRAY[
             'daily_plan_heads','authorization_issuances','execution_bindings',
             'replay_runs','replay_artifacts'
           ])
           AND protected.relowner=role_record.oid
       )
       OR EXISTS (
         SELECT 1 FROM pg_class protected
         JOIN pg_namespace schema ON schema.oid=protected.relnamespace
         CROSS JOIN LATERAL aclexplode(protected.relacl) acl
         WHERE schema.nspname='kineticloop'
           AND protected.relname=ANY(ARRAY[
             'daily_plan_heads','authorization_issuances','execution_bindings',
             'replay_runs','replay_artifacts'
           ])
           AND acl.grantee=role_record.oid
       )
       OR EXISTS (
         SELECT 1 FROM pg_namespace schema
         WHERE schema.nspname='kineticloop'
           AND (schema.nspowner=role_record.oid
                OR has_schema_privilege(role_record.oid,schema.oid,'CREATE'))
       )
       OR EXISTS (
         SELECT 1 FROM pg_proc routine
         JOIN pg_namespace schema ON schema.oid=routine.pronamespace
         WHERE schema.nspname='kineticloop' AND routine.proowner=role_record.oid
       )
       OR EXISTS (
         SELECT 1 FROM pg_class protected
         JOIN pg_namespace schema ON schema.oid=protected.relnamespace
         WHERE schema.nspname='kineticloop'
           AND protected.relname=ANY(ARRAY[
             'daily_plan_heads','authorization_issuances','execution_bindings',
             'replay_runs','replay_artifacts'
           ])
           AND has_table_privilege(
             role_record.oid,protected.oid,
             'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
           )
       )
       OR expected_role <> 'kl_application' AND EXISTS (
         SELECT 1 FROM pg_class protected
         JOIN pg_namespace schema ON schema.oid=protected.relnamespace
         WHERE schema.nspname='kineticloop'
           AND protected.relname=ANY(ARRAY[
             'daily_plan_heads','authorization_issuances','execution_bindings',
             'replay_runs','replay_artifacts'
           ])
           AND has_table_privilege(role_record.oid,protected.oid,'SELECT')
       )
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_OBJECT_BYPASS:%', role_name;
    END IF;
  END LOOP;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_event_trigger event_guard
    JOIN pg_proc routine ON routine.oid=event_guard.evtfoid
    JOIN pg_namespace schema ON schema.oid=routine.pronamespace
    JOIN pg_language language ON language.oid=routine.prolang
    JOIN pg_roles function_owner ON function_owner.oid=routine.proowner
    JOIN pg_roles trigger_owner ON trigger_owner.oid=event_guard.evtowner
    WHERE event_guard.evtname='kl_subject_scope_ddl_guard'
      AND event_guard.evtevent='ddl_command_start'
      AND event_guard.evtenabled='O'
      AND schema.nspname='public'
      AND routine.proname='kl_subject_scope_ddl_guard'
      AND routine.pronargs=0
      AND routine.prorettype='event_trigger'::regtype
      AND routine.prokind='f'
      AND language.lanname='plpgsql'
      AND routine.provolatile='v'
      AND routine.proparallel='u'
      AND NOT routine.proleakproof
      AND routine.prosecdef
      AND routine.proconfig=ARRAY['search_path=pg_catalog, pg_temp']::text[]
      AND md5(routine.prosrc)='dfffd471dab1de3c77f6885072ea8f93'
      AND function_owner.rolsuper
      AND trigger_owner.rolsuper
      AND NOT EXISTS (
        SELECT 1
        FROM aclexplode(coalesce(routine.proacl,acldefault('f',routine.proowner))) acl
        WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'
      )
  ) THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_DDL_GUARD_MISSING';
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
  p_environment_id uuid,
  p_principal_name text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  existing_scope record;
  principal_role record;
  expected_role text;
BEGIN
  IF NOT pg_has_role(session_user, 'kl_trusted_admin', 'MEMBER') THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_REGISTRATION_DENIED';
  END IF;
  IF p_namespace NOT IN ('PRODUCTION','TEST','EVALUATION') THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_INVALID';
  END IF;
  IF p_namespace='PRODUCTION'
       AND p_principal_name !~ '^kl_production_subject_[a-z0-9_]+_login$'
     OR p_namespace='TEST'
       AND p_principal_name !~ '^kl_test_subject_[a-z0-9_]+_login$'
     OR p_namespace='EVALUATION'
       AND p_principal_name !~ '^kl_evaluation_subject_[a-z0-9_]+_login$'
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_INVALID';
  END IF;
  SELECT * INTO principal_role FROM pg_roles WHERE rolname=p_principal_name;
  IF NOT FOUND OR NOT principal_role.rolcanlogin OR principal_role.rolsuper
     OR principal_role.rolcreatedb OR principal_role.rolcreaterole
     OR NOT principal_role.rolinherit OR principal_role.rolreplication
     OR principal_role.rolbypassrls THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_INVALID';
  END IF;
  expected_role := CASE p_namespace
    WHEN 'PRODUCTION' THEN 'kl_application'
    WHEN 'TEST' THEN 'kl_subject_test'
    ELSE 'kl_subject_evaluation'
  END;
  IF (SELECT count(*) FROM pg_auth_members membership
      WHERE membership.member=principal_role.oid) <> 1
     OR NOT EXISTS (
       SELECT 1 FROM pg_auth_members membership
       JOIN pg_roles parent_role ON parent_role.oid=membership.roleid
       WHERE membership.member=principal_role.oid
         AND parent_role.rolname=expected_role
         AND NOT membership.admin_option AND membership.inherit_option
         AND NOT membership.set_option
     )
     OR EXISTS (
       SELECT 1 FROM pg_roles writer_role
       WHERE writer_role.rolname LIKE 'kl_writer_%'
         AND (pg_has_role(principal_role.oid,writer_role.oid,'MEMBER')
              OR pg_has_role(principal_role.oid,writer_role.oid,'SET'))
     )
     OR EXISTS (
       SELECT 1 FROM pg_class protected
       JOIN pg_namespace schema ON schema.oid=protected.relnamespace
       WHERE schema.nspname='kineticloop'
         AND protected.relname=ANY(ARRAY[
           'daily_plan_heads','authorization_issuances','execution_bindings',
           'replay_runs','replay_artifacts'
         ])
         AND (protected.relowner=principal_role.oid
              OR has_table_privilege(
                principal_role.oid,protected.oid,
                'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
              ))
     )
     OR EXISTS (
       SELECT 1 FROM pg_namespace schema
       WHERE schema.nspname='kineticloop'
         AND (schema.nspowner=principal_role.oid
              OR has_schema_privilege(principal_role.oid,schema.oid,'CREATE'))
     )
     OR EXISTS (
       SELECT 1 FROM pg_proc routine
       JOIN pg_namespace schema ON schema.oid=routine.pronamespace
       WHERE schema.nspname='kineticloop' AND routine.proowner=principal_role.oid
     )
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_PRINCIPAL_INVALID';
  END IF;
  LOCK TABLE kineticloop.daily_plan_heads IN ACCESS SHARE MODE;
  LOCK TABLE kineticloop.authorization_issuances IN ACCESS SHARE MODE;
  LOCK TABLE kineticloop.execution_bindings IN ACCESS SHARE MODE;
  LOCK TABLE kineticloop.replay_runs IN ACCESS SHARE MODE;
  LOCK TABLE kineticloop.replay_artifacts IN ACCESS SHARE MODE;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_subject_id::text, 17017));

  SELECT * INTO existing_scope FROM kineticloop.subject_scopes
  WHERE subject_id=p_subject_id FOR UPDATE;
  IF FOUND THEN
    IF existing_scope.namespace <> p_namespace
       OR existing_scope.policy_id IS DISTINCT FROM p_policy_id
       OR existing_scope.environment_id IS DISTINCT FROM p_environment_id
       OR NOT EXISTS (
         SELECT 1 FROM kineticloop.subject_principal_bindings AS binding
         WHERE binding.principal_name=p_principal_name
           AND binding.subject_id=p_subject_id
           AND binding.namespace=p_namespace
       )
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_IMMUTABLE';
    END IF;
    RETURN;
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
  INSERT INTO kineticloop.subject_principal_bindings(
    principal_name,subject_id,namespace
  ) VALUES (p_principal_name,p_subject_id,p_namespace);
END
$routine$
"""

LOOKUP_SQL = r"""
CREATE FUNCTION kineticloop.subject_scope_lookup(
  p_object_kind text,
  p_object_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  bound_subject uuid;
  bound_namespace text;
  expected_role text;
  found_subject uuid;
BEGIN
  SELECT binding.subject_id,binding.namespace INTO bound_subject,bound_namespace
  FROM kineticloop.subject_principal_bindings AS binding
  JOIN kineticloop.subject_scopes AS scope
    ON scope.subject_id=binding.subject_id AND scope.namespace=binding.namespace
  WHERE binding.principal_name=session_user;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_DENIED';
  END IF;
  expected_role := CASE bound_namespace
    WHEN 'PRODUCTION' THEN 'kl_application'
    WHEN 'TEST' THEN 'kl_subject_test'
    WHEN 'EVALUATION' THEN 'kl_subject_evaluation'
    ELSE NULL
  END;
  IF expected_role IS NULL
     OR (SELECT count(*) FROM pg_auth_members membership
         JOIN pg_roles member_role ON member_role.oid=membership.member
         WHERE member_role.rolname=session_user) <> 1
     OR NOT EXISTS (
       SELECT 1 FROM pg_auth_members membership
       JOIN pg_roles parent_role ON parent_role.oid=membership.roleid
       JOIN pg_roles member_role ON member_role.oid=membership.member
       WHERE member_role.rolname=session_user AND parent_role.rolname=expected_role
         AND NOT membership.admin_option AND membership.inherit_option
         AND NOT membership.set_option
     )
     OR EXISTS (
       SELECT 1 FROM pg_roles writer_role
       WHERE writer_role.rolname LIKE 'kl_writer_%'
         AND (pg_has_role(session_user,writer_role.rolname,'MEMBER')
              OR pg_has_role(session_user,writer_role.rolname,'SET'))
     )
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_ROLE_DENIED';
  END IF;
  IF bound_namespace='EVALUATION' AND p_object_kind NOT IN ('S46','S47')
     OR bound_namespace IN ('PRODUCTION','TEST') AND p_object_kind NOT IN ('S38','S42','S45')
  THEN
    RETURN NULL;
  END IF;

  CASE p_object_kind
    WHEN 'S38' THEN SELECT subject_id INTO found_subject FROM kineticloop.daily_plan_heads WHERE subject_id=bound_subject AND id=p_object_id;
    WHEN 'S42' THEN SELECT subject_id INTO found_subject FROM kineticloop.authorization_issuances WHERE subject_id=bound_subject AND id=p_object_id;
    WHEN 'S45' THEN SELECT subject_id INTO found_subject FROM kineticloop.execution_bindings WHERE subject_id=bound_subject AND id=p_object_id;
    WHEN 'S46' THEN SELECT subject_id INTO found_subject FROM kineticloop.replay_runs WHERE subject_id=bound_subject AND id=p_object_id;
    WHEN 'S47' THEN SELECT subject_id INTO found_subject FROM kineticloop.replay_artifacts WHERE subject_id=bound_subject AND id=p_object_id;
    ELSE RETURN NULL;
  END CASE;
  IF found_subject IS NULL THEN
    RETURN NULL;
  END IF;
  RETURN jsonb_build_object(
    'kind',p_object_kind,
    'object_id',p_object_id::text,
    'subject_id',found_subject::text,
    'namespace',bound_namespace
  );
END
$routine$
"""

GUARD_SQL = r"""
CREATE FUNCTION kineticloop.enforce_subject_storage_scope() RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $guard$
DECLARE
  subject_namespace text;
  isolated_policy uuid;
  row_subject uuid;
  trusted_cluster_admin boolean;
BEGIN
  SELECT rolsuper INTO trusted_cluster_admin
  FROM pg_roles WHERE rolname=session_user;
  IF TG_OP='TRUNCATE' THEN
    IF NOT coalesce(trusted_cluster_admin,false)
       AND NOT kineticloop.subject_scope_rls_allows(
         NULL,TG_TABLE_NAME,'DELETE',current_user::text
       )
    THEN
      RAISE EXCEPTION 'KL_SUBJECT_SCOPE_DIRECT_DML_DENIED';
    END IF;
    RETURN NULL;
  END IF;
  IF TG_OP='UPDATE' AND OLD.subject_id IS DISTINCT FROM NEW.subject_id THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_SUBJECT_IMMUTABLE';
  END IF;
  row_subject := CASE WHEN TG_OP='DELETE' THEN OLD.subject_id ELSE NEW.subject_id END;
  IF NOT coalesce(trusted_cluster_admin,false)
     AND NOT kineticloop.subject_scope_rls_allows(
       row_subject,TG_TABLE_NAME,TG_OP,current_user::text
     )
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_DIRECT_DML_DENIED';
  END IF;
  IF TG_OP='DELETE' THEN
    RETURN OLD;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(row_subject::text, 17017));
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

RLS_GUARD_SQL = r"""
CREATE FUNCTION kineticloop.subject_scope_rls_allows(
  p_subject_id uuid,
  p_table_name text,
  p_operation text,
  p_effective_role text
) RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $policy$
DECLARE
  binding record;
  principal_role record;
  expected_scope_role text;
  expected_writer text;
BEGIN
  expected_writer := CASE p_table_name
    WHEN 'daily_plan_heads' THEN 'kl_writer_prescription_commit_service'
    WHEN 'authorization_issuances' THEN 'kl_writer_authorization_service'
    WHEN 'execution_bindings' THEN 'kl_writer_execution_service'
    WHEN 'replay_runs' THEN 'kl_writer_replay_service'
    WHEN 'replay_artifacts' THEN 'kl_writer_replay_service'
    ELSE NULL
  END;
  IF expected_writer IS NULL
     OR p_operation NOT IN ('SELECT','INSERT','UPDATE','DELETE')
  THEN
    RETURN false;
  END IF;

  SELECT principal.subject_id,principal.namespace
    INTO binding
  FROM kineticloop.subject_principal_bindings AS principal
  JOIN kineticloop.subject_scopes AS scope
    ON scope.subject_id=principal.subject_id
   AND scope.namespace=principal.namespace
  WHERE principal.principal_name=session_user;
  IF NOT FOUND THEN
    IF session_user ~ '^kl_(production|test|evaluation)_subject_[a-z0-9_]+_login$'
    THEN
      RETURN false;
    END IF;
    IF p_operation='SELECT' THEN
      RETURN p_effective_role IN ('kl_migration_owner',expected_writer)
        OR pg_has_role(p_effective_role,'kl_auditor','MEMBER')
        OR p_table_name='authorization_issuances'
           AND p_effective_role='kl_writer_safety_registry';
    END IF;
    RETURN p_effective_role=expected_writer;
  END IF;

  SELECT * INTO principal_role FROM pg_roles WHERE rolname=session_user;
  expected_scope_role := CASE binding.namespace
    WHEN 'PRODUCTION' THEN 'kl_application'
    WHEN 'TEST' THEN 'kl_subject_test'
    WHEN 'EVALUATION' THEN 'kl_subject_evaluation'
    ELSE NULL
  END;
  IF expected_scope_role IS NULL
     OR NOT FOUND
     OR NOT principal_role.rolcanlogin OR principal_role.rolsuper
     OR principal_role.rolcreatedb OR principal_role.rolcreaterole
     OR NOT principal_role.rolinherit OR principal_role.rolreplication
     OR principal_role.rolbypassrls
     OR (SELECT count(*) FROM pg_auth_members membership
         WHERE membership.member=principal_role.oid) <> 1
     OR NOT EXISTS (
       SELECT 1 FROM pg_auth_members membership
       JOIN pg_roles parent_role ON parent_role.oid=membership.roleid
       WHERE membership.member=principal_role.oid
         AND parent_role.rolname=expected_scope_role
         AND NOT membership.admin_option AND membership.inherit_option
         AND NOT membership.set_option
     )
     OR EXISTS (
       SELECT 1 FROM pg_roles reachable_role
       WHERE reachable_role.oid<>principal_role.oid
         AND reachable_role.rolname<>expected_scope_role
         AND (pg_has_role(principal_role.oid,reachable_role.oid,'MEMBER')
              OR pg_has_role(principal_role.oid,reachable_role.oid,'SET'))
     )
     OR EXISTS (
       SELECT 1 FROM pg_class protected
       JOIN pg_namespace schema ON schema.oid=protected.relnamespace
       WHERE schema.nspname='kineticloop'
         AND protected.relname=ANY(ARRAY[
           'daily_plan_heads','authorization_issuances','execution_bindings',
           'replay_runs','replay_artifacts'
         ])
         AND (protected.relowner=principal_role.oid
              OR has_table_privilege(
                principal_role.oid,protected.oid,
                'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'
              ))
     )
     OR EXISTS (
       SELECT 1 FROM pg_namespace schema
       WHERE schema.nspname='kineticloop'
         AND (schema.nspowner=principal_role.oid
              OR has_schema_privilege(principal_role.oid,schema.oid,'CREATE'))
     )
     OR EXISTS (
       SELECT 1 FROM pg_proc routine
       JOIN pg_namespace schema ON schema.oid=routine.pronamespace
       WHERE schema.nspname='kineticloop' AND routine.proowner=principal_role.oid
     )
  THEN
    RETURN false;
  END IF;

  IF binding.subject_id IS DISTINCT FROM p_subject_id
     OR binding.namespace='EVALUATION'
        AND p_table_name NOT IN ('replay_runs','replay_artifacts')
     OR binding.namespace IN ('PRODUCTION','TEST')
        AND p_table_name NOT IN (
          'daily_plan_heads','authorization_issuances','execution_bindings'
        )
  THEN
    RETURN false;
  END IF;
  RETURN p_operation='SELECT' OR p_effective_role=expected_writer;
END
$policy$
"""

DOWNGRADE_DATA_PREFLIGHT_SQL = """
DO $downgrade_preflight$
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended('KL-017-downgrade-preflight',17017));
  IF EXISTS (SELECT 1 FROM kineticloop.subject_scopes)
     OR EXISTS (SELECT 1 FROM kineticloop.subject_principal_bindings)
     OR EXISTS (SELECT 1 FROM kineticloop.daily_plan_heads)
     OR EXISTS (SELECT 1 FROM kineticloop.authorization_issuances)
     OR EXISTS (SELECT 1 FROM kineticloop.execution_bindings)
     OR EXISTS (SELECT 1 FROM kineticloop.replay_runs)
     OR EXISTS (SELECT 1 FROM kineticloop.replay_artifacts)
  THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_DOWNGRADE_SCOPED_STATE';
  END IF;
END
$downgrade_preflight$
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
          CONSTRAINT uq_subject_scope_namespace UNIQUE(subject_id,namespace),
          CONSTRAINT ck_subject_scope_binding CHECK (
            namespace='PRODUCTION' AND policy_id IS NULL AND environment_id IS NULL
            OR namespace='TEST' AND policy_id IS NOT NULL AND environment_id IS NOT NULL
            OR namespace='EVALUATION' AND policy_id IS NULL AND environment_id IS NOT NULL
          )
        )
    """)
    op.execute("""
        CREATE TABLE kineticloop.subject_principal_bindings (
          principal_name text PRIMARY KEY,
          subject_id uuid NOT NULL UNIQUE,
          namespace text NOT NULL CHECK (namespace IN ('PRODUCTION','TEST','EVALUATION')),
          registered_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
          CONSTRAINT fk_subject_principal_scope FOREIGN KEY(subject_id,namespace)
            REFERENCES kineticloop.subject_scopes(subject_id,namespace)
        )
    """)
    op.execute("REVOKE ALL ON kineticloop.subject_scopes FROM PUBLIC")
    op.execute("REVOKE ALL ON kineticloop.subject_principal_bindings FROM PUBLIC")
    op.execute(
        "GRANT SELECT ON kineticloop.subject_scopes, "
        "kineticloop.subject_principal_bindings TO kl_auditor"
    )
    op.execute("REVOKE SELECT ON kineticloop.daily_plan_heads, kineticloop.authorization_issuances, kineticloop.execution_bindings, kineticloop.replay_runs, kineticloop.replay_artifacts FROM kl_application")
    op.execute(REGISTER_SQL)
    op.execute(LOOKUP_SQL)
    op.execute(GUARD_SQL)
    op.execute(RLS_GUARD_SQL)
    op.execute(
        "REVOKE ALL ON FUNCTION kineticloop.enforce_subject_storage_scope() FROM PUBLIC"
    )
    rls_signature = "kineticloop.subject_scope_rls_allows(uuid,text,text,text)"
    op.execute(f"REVOKE ALL ON FUNCTION {rls_signature} FROM PUBLIC")
    for role in (
        "kl_migration_owner", "kl_application", "kl_auditor", "kl_trusted_admin",
        "kl_subject_test", "kl_subject_evaluation",
        "kl_writer_prescription_commit_service", "kl_writer_authorization_service",
        "kl_writer_execution_service", "kl_writer_replay_service",
        "kl_writer_safety_registry",
    ):
        op.execute(f"GRANT EXECUTE ON FUNCTION {rls_signature} TO {role}")
    op.execute(
        "GRANT SELECT ON kineticloop.subject_scopes TO "
        "kl_writer_prescription_commit_service, kl_writer_authorization_service, "
        "kl_writer_execution_service, kl_writer_replay_service"
    )
    protected_tables = (
        "daily_plan_heads", "authorization_issuances", "execution_bindings",
        "replay_runs", "replay_artifacts",
    )
    for table in protected_tables:
        op.execute(f"ALTER TABLE kineticloop.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE kineticloop.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY subject_scope_select ON kineticloop.{table} "
            "FOR SELECT USING (kineticloop.subject_scope_rls_allows("
            f"subject_id,'{table}','SELECT',current_user::text))"
        )
        op.execute(
            f"CREATE POLICY subject_scope_insert ON kineticloop.{table} "
            "FOR INSERT WITH CHECK (kineticloop.subject_scope_rls_allows("
            f"subject_id,'{table}','INSERT',current_user::text))"
        )
        op.execute(
            f"CREATE POLICY subject_scope_update ON kineticloop.{table} "
            "FOR UPDATE USING (kineticloop.subject_scope_rls_allows("
            f"subject_id,'{table}','UPDATE',current_user::text)) "
            "WITH CHECK (kineticloop.subject_scope_rls_allows("
            f"subject_id,'{table}','UPDATE',current_user::text))"
        )
        op.execute(
            f"CREATE POLICY subject_scope_delete ON kineticloop.{table} "
            "FOR DELETE USING (kineticloop.subject_scope_rls_allows("
            f"subject_id,'{table}','DELETE',current_user::text))"
        )
        op.execute(f"CREATE TRIGGER subject_storage_scope BEFORE INSERT OR UPDATE OR DELETE ON kineticloop.{table} FOR EACH ROW EXECUTE FUNCTION kineticloop.enforce_subject_storage_scope()")
        op.execute(f"CREATE TRIGGER subject_storage_truncate BEFORE TRUNCATE ON kineticloop.{table} FOR EACH STATEMENT EXECUTE FUNCTION kineticloop.enforce_subject_storage_scope()")
    register_signature = "kineticloop.subject_scope_register(uuid,text,uuid,uuid,text)"
    lookup_signature = "kineticloop.subject_scope_lookup(text,uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {register_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {register_signature} TO kl_trusted_admin")
    op.execute(f"REVOKE ALL ON FUNCTION {lookup_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {lookup_signature} TO kl_application, kl_subject_test, kl_subject_evaluation")
    op.execute("GRANT USAGE ON SCHEMA kineticloop TO kl_subject_test, kl_subject_evaluation")


def downgrade() -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    protected_tables = (
        "daily_plan_heads", "authorization_issuances", "execution_bindings",
        "replay_runs", "replay_artifacts",
    )
    for table in (*protected_tables, "subject_scopes", "subject_principal_bindings"):
        op.execute(f"LOCK TABLE kineticloop.{table} IN ACCESS EXCLUSIVE MODE")
    op.execute(DOWNGRADE_DATA_PREFLIGHT_SQL)
    for table in protected_tables:
        op.execute(f"DROP TRIGGER subject_storage_truncate ON kineticloop.{table}")
        op.execute(f"DROP TRIGGER subject_storage_scope ON kineticloop.{table}")
        for operation in ("select", "insert", "update", "delete"):
            op.execute(f"DROP POLICY subject_scope_{operation} ON kineticloop.{table}")
        op.execute(f"ALTER TABLE kineticloop.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE kineticloop.{table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION kineticloop.enforce_subject_storage_scope()")
    op.execute("DROP FUNCTION kineticloop.subject_scope_rls_allows(uuid,text,text,text)")
    op.execute("DROP FUNCTION kineticloop.subject_scope_lookup(text,uuid)")
    op.execute("DROP FUNCTION kineticloop.subject_scope_register(uuid,text,uuid,uuid,text)")
    op.execute("GRANT SELECT ON kineticloop.daily_plan_heads, kineticloop.authorization_issuances, kineticloop.execution_bindings, kineticloop.replay_runs, kineticloop.replay_artifacts TO kl_application")
    op.execute(
        "REVOKE USAGE ON SCHEMA kineticloop FROM kl_subject_test, kl_subject_evaluation"
    )
    op.execute("DROP TABLE kineticloop.subject_principal_bindings")
    op.execute("DROP TABLE kineticloop.subject_scopes")
