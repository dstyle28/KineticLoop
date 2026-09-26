# Artifact registry registration contract

`RegisterArtifact` is a distinct global management command. It does not change the frozen
T2-GLOBAL revocation linearization rule or make provider/model output authoritative.

The externally provisioned `kl_trusted_admin` execution role alone receives `EXECUTE` on the
single non-overloaded `kineticloop.registry_register_artifact(uuid,text,text,uuid[],text,text,text,integer)`
routine. The routine is `SECURITY DEFINER`, is owned by NOLOGIN
`kl_writer_safety_registry`, fixes `search_path` to `pg_catalog, kineticloop, pg_temp`, checks
`pg_has_role(session_user, 'kl_trusted_admin', 'MEMBER')`, and persists `session_user` as the
operator identity. Caller actor/capability fields are neither SQL authorization inputs nor
persisted operator identity.

Registration takes the singleton S51 row `FOR UPDATE` and holds that exclusive gate through
commit. It never reads or locks S01. Under the gate it admits only immutable MODEL, PROMPT,
TOOL, RUNTIME, or POLICY identity/version/content tuples with an exact S05, S19, or S48 root,
defined BOUNDED or explicitly approved TIMELESS validity, and an explicitly complete closure
of identities already present in S49. A TIMELESS approval names a canonical UUID for a
pre-registered `POLICY` or `POLICY_BUNDLE` artifact; that identity must be an explicit member
of the declared closure, so its later T2-GLOBAL revocation denies T3, T6, and T7. Omitted,
JSON-null, blank, one-sided, or non-increasing validity fields fail with
`VALIDITY_UNDEFINED`; the successor also makes the S49 validity check NULL-total. Before it
installs that constraint, upgrade performs a deterministic preflight over legacy TIMELESS
rows and aborts if any approval policy is not a canonical registered `POLICY` or
`POLICY_BUNDLE` connected by an explicit dependency edge. A malformed legacy row therefore
cannot become eligible merely because the successor was installed.

The closure must be unique, acyclic, no more than 128 nodes, and no more than 16 edges deep.
SQL verifies it with bounded duplicate-suppressing traversal, so dense DAGs do not cause path
enumeration. A closure whose validity cannot be established within either bound fails with
the frozen `VALIDITY_UNDEFINED` denial and no registration mutation. Closure construction and
external work remain outside the transaction; SQL independently verifies the submitted
closure before admission.

Successful first admission atomically appends S49, normalized dependency edges, a management
receipt, an audit event, and an outbox row. Exact replay returns the original registration;
reuse of an artifact identity with different identity, version, content, dependency, binding,
or validity is rejected. Both an existing artifact-id conflict and the S49 natural-identity
unique conflict surface as stable `IMMUTABLE_ARTIFACT` domain denials. Lock timeout and any
failure after the first S49 write roll back S49, dependency edges, receipt, audit event, and
outbox together. Existing immutable-history triggers reject S49/dependency mutation.
Runtime application, audit, user, and agent sessions receive no direct S49/S51 DML, cannot
assume the owner role, and cannot execute RegisterArtifact.

T3, T6, and T7 continue to require exact artifact references and use the shared S51 routines.
For T3, the registry guard loads the subject's current S24 manifest root and closure digest,
requires that root in the caller-supplied complete closure, and compares S24's digest with the
deterministic digest of those exact supplied identities before evaluating every member. The
caller therefore cannot substitute an unrelated healthy closure, and SQL does not construct
the closure inside the coordination transaction. At use time, every TIMELESS member is
checked again for its canonical registered policy dependency inside that exact closure;
revoking only that policy denies T3, T6, and T7 before mutation. Unknown, expired, or revoked
identities remain fail-closed. Registration adds no production auto-activation and makes no
product-requirement PASS claim.
