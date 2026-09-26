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
of identities already present in S49. The closure must be unique, acyclic, no more than 128
nodes, and no more than 16 edges deep. Closure construction and external work remain outside
the transaction; SQL independently verifies the submitted closure before admission.

Successful first admission atomically appends S49, normalized dependency edges, a management
receipt, an audit event, and an outbox row. Exact replay returns the original registration;
reuse of an artifact identity with different identity, version, content, dependency, binding,
or validity is rejected. Existing immutable-history triggers reject S49/dependency mutation.
Runtime application, audit, user, and agent sessions receive no direct S49/S51 DML, cannot
assume the owner role, and cannot execute RegisterArtifact.

T3, T6, and T7 continue to require exact artifact references and use the shared S51 routines.
Unknown, expired, or revoked identities remain fail-closed. Registration adds no production
auto-activation and makes no product-requirement PASS claim.
