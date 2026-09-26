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
protected-table ACL, protected-table or in-schema routine ownership, or schema
creation authority. Upgrade preflight rejects those bypasses before DDL. Registration
rechecks them before persisting a binding.

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
the subject session.

All five protected tables enable and force row-level security. Every policy derives
the bound subject and namespace from `session_user` and revalidates live role
attributes, the sole scope membership, all reachable roles, protected-object ACLs
and ownership, schema creation, and in-schema routine ownership. Bound principals
can never use drifted table privileges directly: reads are restricted to the exact
bound subject, and writes additionally require `current_user` to be the table's
exact command-owner role. Unbound reads are limited to the migration owner, the
table's exact writer, auditors, and the SafetyRegistry writer's required S42 read.
A statement-level `BEFORE TRUNCATE` trigger rejects every bound subject session.

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
