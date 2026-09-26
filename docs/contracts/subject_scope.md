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

Runtime credentials inherit exactly one scope role. `kl_application` represents the
production namespace, while `kl_subject_test` and `kl_subject_evaluation` represent
the two non-production namespaces. These roles have no direct access to the five
protected tables. `subject_scope_lookup` derives namespace from `session_user`, uses
a fixed search path, and returns SQL NULL for both missing objects and objects outside
that namespace. The application converts every NULL or role mismatch into the same
`SUBJECT_SCOPE_DENIED` response and `BOUNDED_SCOPE_LOOKUP` timing class.

Registration and protected writes take the same transaction-scoped advisory lock
derived from the subject identifier. This serializes the first protected write with
namespace registration so an unregistered subject cannot be classified as production
while a concurrent trusted-admin transaction is assigning TEST or EVALUATION scope.

The triggers are storage guards, not new T6/T7 command owners. They neither acquire
S51/S01 nor issue authorization or execution bindings. Normal T6/T7 command routines
must still take the frozen S51-to-S01 order and enforce all current eligibility.
