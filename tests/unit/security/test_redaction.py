from __future__ import annotations

import copy
import subprocess
from urllib.parse import quote

from kineticloop.primitives.canonical import canonical_json_bytes
from kineticloop.primitives.hashes import sha256_bytes
from kineticloop.security import REDACTED, RedactedDiagnostic, Redactor

SENTINEL = "SYNTHETIC p@ss/word? NOT A CREDENTIAL"


def test_nested_redaction_is_non_mutating_and_authority_neutral() -> None:
    evidence = {
        "evidence_id": "evidence-synthetic-001",
        "observed": {"metric": "duration_minutes", "value": 42},
    }
    canonical_before = canonical_json_bytes(evidence)
    hash_before = sha256_bytes(canonical_before)
    source: dict[str, object] = {
        "safe": "provider timeout",
        "password": SENTINEL,
        "nested": [
            {"api_key": SENTINEL, "attempt": 3},
            (
                "https://db_user:SYNTHETIC%20p%40ss%2Fword%3F%20NOT%20A%20CREDENTIAL"
                "@db.invalid:5432/test?sslmode=require&token=also-secret",
            ),
        ],
        "log_args": ("retry %s", {"Authorization": f"Bearer {SENTINEL}"}),
        "registered": f"failure contained {quote(SENTINEL, safe='')}",
        f"registered-key-{SENTINEL}": "safe value",
        "canonical_evidence": evidence,
    }
    child = ValueError(f"password={SENTINEL}")
    process_error = subprocess.CalledProcessError(
        1,
        ["provider-client", f"--token={SENTINEL}"],
        output=f"url=https://user:{quote(SENTINEL, safe='')}@provider.invalid/data",
        stderr=f"Authorization: Bearer {SENTINEL}",
    )
    process_error.__cause__ = child
    source["error"] = process_error
    source["ipv6"] = "postgresql://alice:hunter2@[::1]:5432/db?token=abc"
    source["mixed_encoding"] = quote(SENTINEL, safe="").replace("%2F", "%2f")
    source["partial_encoding"] = SENTINEL.replace("/", "%2f").replace("?", "%3f")
    source["unregistered_sensitive_text"] = (
        'Authorization: Bearer opaque.jwt.value; password="opaque multi word"'
    )
    source["argv"] = ["provider-client", "--hevy-api-key", "opaque-argument"]
    source["string_command"] = 'provider-client --password "opaque command value"'
    source_without_error = dict(source)
    source_without_error.pop("error")
    untouched = copy.deepcopy(source_without_error)

    redacted = Redactor((SENTINEL,)).redact(source)
    rendered = repr(redacted)

    assert SENTINEL not in rendered
    assert quote(SENTINEL, safe="") not in rendered
    assert "also-secret" not in rendered
    assert "alice" not in rendered
    assert "hunter2" not in rendered
    assert "opaque.jwt.value" not in rendered
    assert "opaque multi word" not in rendered
    assert "opaque-argument" not in rendered
    assert "opaque command value" not in rendered
    assert "provider timeout" in rendered
    assert "sslmode=require" in rendered
    assert "attempt': 3" in rendered
    assert REDACTED in rendered
    assert isinstance(redacted["error"], RedactedDiagnostic)  # type: ignore[index]

    source_without_error = dict(source)
    source_without_error.pop("error")
    assert source_without_error == untouched
    assert canonical_json_bytes(evidence) == canonical_before
    assert sha256_bytes(canonical_json_bytes(evidence)) == hash_before

    diagnostic = redacted["error"]  # type: ignore[index]
    for authority_field in (
        "evidence_admission",
        "command",
        "role",
        "capability",
        "approval",
        "authorization",
    ):
        assert not hasattr(diagnostic, authority_field)
