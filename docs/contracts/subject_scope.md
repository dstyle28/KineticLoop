# Subject scope persistence contract

Production is the compatibility default for subjects without an explicit row in
`kineticloop.subject_scopes`. Test and evaluation subjects require an immutable,
trusted-admin registration before they can use their isolated storage.

`TEST` registration binds one same-subject policy whose namespace begins with
`test:` and one isolated environment identifier. S42 writes for that subject must
use `TEST_ONLY` and that exact policy; S45 must also use `TEST_ONLY`. Evaluation
subjects may write S46/S47 replay storage and cannot write S38/S42/S45. Production
subjects cannot write `TEST_ONLY` authorization or execution rows and cannot write
evaluation storage.

Each runtime subject uses an externally provisioned LOGIN principal that inherits
exactly one NOLOGIN scope role. `kl_application` represents the production namespace,
while `kl_subject_test` and `kl_subject_evaluation` represent the two non-production
namespaces. Trusted-admin registration records the LOGIN principal, exact subject,
and namespace in `kineticloop.subject_principal_bindings`. A principal and a subject
can each occur in only one binding. Subject principals cannot inherit or assume any
`kl_writer_*` role, including `kl_writer_safety_registry`, and cannot hold a direct
protected-table or authority-metadata ACL, protected-table or authority-metadata
ownership, in-schema routine ownership, or schema creation authority. Upgrade
preflight rejects those bypasses before DDL when the objects exist. Registration,
lookup, RLS, and storage-write paths recheck direct and inherited authority over all
five protected data tables plus `subject_scopes` and
`subject_principal_bindings`.

Only the externally provisioned `kl_trusted_admin_login` with its one exact inherited
`kl_trusted_admin` membership may call registration. A canonical or already-bound
subject session fails registration even if an administrator later grants it the
trusted-admin role. Both authority tables enable and force row-level security. Their
policies use a catalog-only SECURITY DEFINER helper to revalidate the authenticated
session before permitting any row access. Bound subject sessions therefore see no
authority rows under direct ACLs, inherited bridge ACLs, `SET ROLE`, ownership, or
role-attribute drift. SECURITY INVOKER row and statement triggers provide a second
write boundary and permit registration INSERTs only while the trusted-admin caller
is executing inside the migration-owner SECURITY DEFINER routine. The database
superuser remains the explicit operator path for retiring metadata before downgrade.

Scope roles have no direct access to the five protected tables.
`subject_scope_lookup` accepts only an object kind and object identifier. It derives
the namespace and exact subject from `session_user`, rechecks the principal's sole
scope membership and absence of writer paths, and filters the protected relation by
the bound subject. It returns SQL NULL for missing objects and for objects belonging
to any other subject, including another subject in the same namespace. The
application converts every NULL or role mismatch into the same `SUBJECT_SCOPE_DENIED`
response and `BOUNDED_SCOPE_LOOKUP` timing class. Before releasing a successful
lookup, the application also verifies that the returned kind, object identifier,
subject identifier, and namespace exactly match its authenticated actor and request.

The storage trigger makes `subject_id` immutable on every UPDATE across S38, S42,
S45, S46, and S47. When a subject-specific session acquires any direct or transitive
MEMBER or SET path to a `kl_writer_*` role, the runtime boundary rejects direct DML
even after `SET ROLE`. Normal command-owner routines remain SECURITY DEFINER entry points and
continue to perform their guarded writes without granting their writer identity to
the subject session. The row trigger itself is SECURITY INVOKER and passes its
invoking `current_user` to the narrowly privileged RLS helper. This lets the trigger
independently reject INSERT, UPDATE, and DELETE by a bound or canonically named
subject session unless the row operation is executing under the table's exact
command owner for the exact bound subject and namespace. It rejects every such
session's TRUNCATE. The trigger still rejects these writes if an administrator later
grants the login `BYPASSRLS`.

All five protected tables enable and force row-level security. Every policy derives
the bound subject and namespace from `session_user` and revalidates live role
attributes, the sole scope membership, all reachable roles, protected-object ACLs
and ownership, schema creation, and in-schema routine ownership. Bound principals
can never use drifted table privileges directly: reads are restricted to the exact
bound subject, and writes additionally require `current_user` to be the table's
exact command-owner role. Unbound reads are limited to the migration owner, the
table's exact writer, auditors, and the SafetyRegistry writer's required S42 read.
A statement-level `BEFORE TRUNCATE` trigger rejects every bound subject session.

A database-wide `ddl_command_start` event trigger is an external cluster-bootstrap
prerequisite. Its superuser-owned SECURITY DEFINER function checks the authenticated
`session_user`, not `current_user`, and rejects all DDL from either a registered
principal or a canonical subject-login name. The name check keeps the boundary
closed if a subject reaches the migration owner and deletes or corrupts its binding
before attempting DDL. It prevents that session from disabling RLS, changing or
dropping policies and storage triggers, replacing guard functions, altering protected
relations, or constructing a foreign-key existence oracle after a `REFERENCES` grant.
The d4 migration verifies the enabled event, function signature, owner attributes,
fixed search path, revoked PUBLIC execution, and exact function-body fingerprint
before any object change.

Foreign keys into S38, S42, S45, S46, or S47 are a closed inventory. Upgrade
preflight uses `pg_constraint` and its `pg_depend` target dependencies to accept only
the eight canonical in-schema, subject-keyed constraints. It rejects a legacy or
external inbound foreign key before d4 changes any object, even if its creator's
`REFERENCES` privilege was later revoked. Registration repeats the inventory check,
and lookup and RLS fail closed if administrator drift adds a noncanonical inbound
constraint after registration. This prevents referential-integrity probes from
becoming a row-existence oracle outside the protected storage boundary.

The cluster bootstrap superuser must install the guard after the frozen baseline
ownership handoff and before upgrading past b6. The canonical installation is:

```sql
CREATE OR REPLACE FUNCTION public.kl_subject_scope_ddl_guard()
RETURNS event_trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,pg_temp AS $guard$
DECLARE
  bound_principal boolean;
BEGIN
  bound_principal := session_user ~
    '^kl_(production|test|evaluation)_subject_[a-z0-9_]+_login$';
  IF NOT bound_principal
     AND to_regclass('kineticloop.subject_principal_bindings') IS NOT NULL
  THEN
    EXECUTE 'SELECT EXISTS (SELECT 1 FROM '
      'kineticloop.subject_principal_bindings '
      'WHERE principal_name=session_user)'
      INTO bound_principal;
  END IF;
  IF bound_principal THEN
    RAISE EXCEPTION 'KL_SUBJECT_SCOPE_DDL_DENIED';
  END IF;
END
$guard$;
REVOKE ALL ON FUNCTION public.kl_subject_scope_ddl_guard() FROM PUBLIC;
CREATE EVENT TRIGGER kl_subject_scope_ddl_guard
ON ddl_command_start EXECUTE FUNCTION public.kl_subject_scope_ddl_guard();
```

The external event trigger remains installed across a d4 downgrade. When the binding
table is absent, the canonical subject-login check remains active and the metadata
lookup is skipped; unbound deployer and cluster-admin sessions can perform the next
upgrade. Event-trigger administration and ALTER ROLE remain superuser operations.
Provisioning must never grant a subject principal `SUPERUSER` or `BYPASSRLS`.
PostgreSQL intentionally bypasses SELECT policies for either attribute, so an
administrator that grants one can read protected rows as that principal despite the
row-write and DDL guards. Direct superuser data access is likewise outside this
database boundary and belongs to trusted cluster administration and continuous role
audit.

Registration and protected writes take the same transaction-scoped advisory lock
derived from the subject identifier. This serializes the first protected write with
namespace registration so an unregistered subject cannot be classified as production
while a concurrent trusted-admin transaction is assigning TEST or EVALUATION scope.

Downgrade fails before removing a trigger, function, table, or privilege whenever
any scope row, principal binding, or S38/S42/S45/S46/S47 row exists. Removing
classification metadata cannot make retained data downgrade-safe. Operators must
explicitly retire all classified state and protected data before restoring the
predecessor's shared production read surface.

The downgrade acquires transaction-held `ACCESS EXCLUSIVE` locks in the global order
S38, S42, S45, S46, S47, subject scopes, then principal bindings before checking
emptiness. Registration first takes `ACCESS SHARE` locks on the five protected
tables in the same order. A concurrent protected write or registration therefore
finishes before the downgrade scan, or waits until the complete downgrade commits;
it cannot enter between the scan and guard removal.

The triggers are storage guards, not new T6/T7 command owners. They neither acquire
S51/S01 nor issue authorization or execution bindings. Normal T6/T7 command routines
must still take the frozen S51-to-S01 order and enforce all current eligibility.
