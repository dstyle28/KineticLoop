"""bind the T3 registry gate to the candidate artifact closure"""

from alembic import op

from migrations.versions.b6e4d8a1c927_artifact_registry import (
    PREFLIGHT_SQL,
    _publish_guard_sql,
)

revision = "e7a2c4f91d60"
down_revision = "d4c1a9e7b203"
branch_labels = None
depends_on = None


PUBLISH_CANDIDATE_GUARD_SQL = r"""
CREATE OR REPLACE FUNCTION kineticloop.registry_guard_publish_manifest(
  p_subject_id uuid,
  p_artifact_ids uuid[],
  p_minimum_registry_revision bigint,
  p_lock_timeout_ms integer
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, kineticloop, pg_temp
AS $routine$
DECLARE
  current_revision bigint;
  authoritative_now timestamptz;
BEGIN
  IF p_lock_timeout_ms IS NULL OR p_lock_timeout_ms <= 0 THEN
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

  PERFORM 1
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
    SELECT 1
    FROM kineticloop.safety_artifacts AS artifact
    WHERE artifact.id = ANY(p_artifact_ids)
      AND artifact.validity_kind = 'TIMELESS'
      AND (
        artifact.timeless_approval_policy IS NULL
        OR artifact.timeless_approval_policy !~
          '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        OR CASE
          WHEN artifact.timeless_approval_policy ~
            '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
          THEN NOT EXISTS (
            SELECT 1
            FROM kineticloop.safety_artifacts AS policy
            JOIN kineticloop.safety_artifact_dependencies AS edge
              ON edge.artifact_id = artifact.id
             AND edge.dependency_artifact_id = policy.id
            WHERE policy.id = artifact.timeless_approval_policy::uuid
              AND policy.artifact_kind IN ('POLICY', 'POLICY_BUNDLE')
              AND policy.id = ANY(p_artifact_ids)
          )
          ELSE true
        END
      )
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
  RETURN current_revision;
EXCEPTION
  WHEN lock_not_available OR query_canceled THEN
    RAISE EXCEPTION 'KL_REGISTRY_TIMEOUT';
END
$routine$
"""


def _replace_publish_guard(sql: str) -> None:
    op.execute(PREFLIGHT_SQL)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("GRANT CREATE ON SCHEMA kineticloop TO kl_writer_safety_registry")
    op.execute("SET LOCAL ROLE kl_writer_safety_registry")
    op.execute(sql)
    op.execute("SET LOCAL ROLE kl_migration_owner")
    op.execute("REVOKE CREATE ON SCHEMA kineticloop FROM kl_writer_safety_registry")


def upgrade() -> None:
    _replace_publish_guard(PUBLISH_CANDIDATE_GUARD_SQL)


def downgrade() -> None:
    _replace_publish_guard(_publish_guard_sql(hardened=True))
