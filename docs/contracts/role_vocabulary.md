# Role vocabulary and capability contract v1

## Scope

This contract defines four closed identity categories and coarse capabilities. It does not grant a
command, authenticate an identity, or replace command-specific authorization, policy, scope,
dependency, validity, control-state, or transaction guards. A trusted service must bind the role to
the identity before an authorization boundary uses it.

## Stable vocabulary

| Role wire value | Derived capability | Production actor category |
|---|---|---|
| `subject` | `act_as_production_subject` | yes |
| `test` | `run_test_simulation` | no |
| `admin` | `administer_production` | yes |
| `evaluation` | `run_isolated_evaluation` | no |

Capabilities are mutually exclusive in v1. Subject capability does not imply admin capability, and
admin capability does not imply subject capability. The generic production-actor predicate is only
classification. The enforcing production boundary requires one exact production capability, so it
cannot bypass the subject/admin distinction; callers must also apply every domain guard for a
command.

Test and evaluation identities are mechanically rejected by the production-actor boundary. Test
simulation cannot be treated as production authorization. Evaluation remains isolated and cannot
write live state, issue production authorization, or trigger execution. No output, summary,
repetition, or conversion can promote either role or its capability.

## Serialization

The wire schema is `kineticloop-role-identity-v1` and has exactly three fields:

```json
{"identity_id":"8c7d83ee-49db-4b2c-9df2-0b0f158c328f","role":"test","schema":"kineticloop-role-identity-v1"}
```

`identity_id` uses the repository's canonical UUID form. Unknown roles, schema versions, duplicate
keys, extra fields, and noncanonical identifiers are rejected. Capabilities are intentionally absent
from the payload and are derived from the immutable role matrix, so serialized input cannot assert
additional capability.

## Frozen-authority alignment

- `INV-02`: model-declared command text or authorization never creates capability.
- `INV-15`: summaries and transformations remain non-command and cannot raise authority.
- Protocol §7.4 and DB S46–S48: evaluation/replay stays isolated from production authorization and
  live mutation.
- DB §8.1: test-only authorization stays explicitly test-only and cannot be installed as a
  production release configuration.
