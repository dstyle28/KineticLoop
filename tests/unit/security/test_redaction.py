from __future__ import annotations

import copy
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from kineticloop.primitives.canonical import canonical_json_bytes
from kineticloop.primitives.hashes import sha256_bytes
from kineticloop.security import REDACTED, RedactedDiagnostic, Redactor

SENTINEL = "SYNTHETIC p@ss/word? NOT A CREDENTIAL"


@dataclass(frozen=True)
class CompoundDiagnosticKey:
    value: str


class UnsafeDiagnosticInt(int):
    def __repr__(self) -> str:
        return "unsafe-scalar-secret"


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
        "double_encoded_registered": quote(quote(SENTINEL, safe=""), safe=""),
        f"registered-key-{SENTINEL}": "safe value",
        "canonical_evidence": evidence,
    }
    child = ValueError({"password": "opaque-exception-secret", "safe": "child context"})
    process_error = subprocess.CalledProcessError(
        1,
        [
            "provider-client",
            f"--token={SENTINEL}",
            "--password",
            "opaque-cmd-secret",
        ],
        output=f"url=https://user:{quote(SENTINEL, safe='')}@provider.invalid/data",
        stderr='{"password":"opaque-stderr-secret","safe":"retry context"}',
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
    source["malformed_url"] = (
        "https://alice:hunter2@example.invalid:notaport/path?token=query-secret"
    )
    source["malformed_ipv6"] = (
        "postgresql://alice:hunter2@[2001:db8::1]:notaport/db?token=query-secret"
    )
    source["interior_keys"] = {
        "provider_api_key_value": "opaque-interior-secret",
        "clientSecret": "opaque-camel-secret",
        "accessToken": "opaque-access-secret",
    }
    source["authorization_argv"] = [
        "provider-client",
        "--authorization",
        "Bearer",
        "opaque-auth-secret",
    ]
    source["formatted_log_args"] = ("Authorization=%s", "Bearer format-secret")
    source["compound_keys"] = {
        ("registered", SENTINEL): "safe tuple-key value",
        CompoundDiagnosticKey(SENTINEL): "safe object-key value",
    }
    compound_exception = ValueError(
        "diagnostic payload: "
        '{"password": ["json-secret-one", "json-secret-two"], '
        "'credentials': ('python-secret-one', 'python-secret-two'), "
        "'safe': 'retained context'}"
    )
    source["compound_exception"] = compound_exception
    source["hybrid_authorization_argv"] = [
        "provider-client",
        "--authorization=Bearer",
        "hybrid-auth-secret",
    ]
    source["punctuated_argv"] = [
        "provider-client",
        "--api-key=comma-secret,semicolon-secret;tail-secret",
    ]
    source["semicolon_query"] = (
        "https://provider.invalid/data?safe=retained;token=semicolon-query-secret;"
        "password=second-query-secret"
    )
    source["multi_format_args"] = (
        "credentials=%s:%s",
        "opaque-format-user",
        "opaque-format-password",
    )
    source["brace_format_args"] = (
        "clientSecret={}{}",
        "opaque-brace-one",
        "opaque-brace-two",
    )
    source["acronym_keys"] = {
        "providerDSNValue": "opaque-acronym-dsn",
        "refreshTOKENValue": "opaque-acronym-token",
    }
    source["composite_text"] = '{"password":["first","opaque-composite-tail"]}'
    source["escaped_text"] = '{"password":"first\\"opaque-escaped-tail"}'
    source["malformed_quote_url"] = 'https://alice:hun"opaque-double-quote@example.invalid/path'
    source["malformed_single_quote_url"] = (
        "https://alice:hun'opaque-single-quote@example.invalid/path"
    )
    source["malformed_space_url"] = "https://alice:hun opaque-space@example.invalid/path"
    source["terminal_ipv6"] = "https://alice:hunter2@[2001:db8::1]"
    source["spaced_key_text"] = "API Key: opaque-space-key-secret"
    source["authorization_header"] = "Authorization Bearer opaque-header-secret"
    source["nested_compound_text"] = '{"password":[["inner-secret"],"tail-secret"]}'
    source["mixed_format_args"] = (
        "safe=%s password=%s",
        "retained-format-context",
        "mixed-format-secret",
    )
    source["mixed_brace_args"] = (
        "safe={} client secret={}",
        "retained-brace-context",
        "mixed-brace-secret",
    )
    source["sensitive_compound_key"] = {("password", "slot"): "tuple-key-secret"}
    source["sensitive_bytes_key"] = {b"password": "bytes-key-secret"}
    source["sensitive_frozenset_key"] = {
        frozenset({"slot", "clientSecret"}): "frozenset-key-secret"
    }
    source["unsupported_value"] = CompoundDiagnosticKey("registered-object-secret")
    source["unsupported_path"] = Path(f"/tmp/{SENTINEL}")
    source["cookie_tail"] = "cookie=session-value; opaque-cookie-tail-secret"
    source["fully_encoded_userinfo"] = (
        "https://alice%3Aopaque-encoded-userinfo-secret%40provider.invalid/path"
    )
    source["recursively_encoded_userinfo"] = (
        "https://alice%253Aopaque-double-encoded-secret%2540provider.invalid/path"
    )
    source["recursively_encoded_query"] = (
        "https://provider.invalid/path?to%256ben=opaque-double-query-secret"
    )
    source["fully_encoded_query_assignment"] = (
        "https://provider.invalid/path?to%256ben%253Dopaque-fully-encoded-query-secret"
    )
    source["indexed_format_args"] = (
        "password={1} safe={0}",
        "retained-indexed-context",
        "indexed-format-secret",
    )
    source["dynamic_width_args"] = (
        "password=%*s",
        8,
        "dynamic-width-secret",
    )
    source["dynamic_precision_args"] = (
        "password=%.*s",
        4,
        "dynamic-precision-secret",
    )
    source["unsafe_scalar_value"] = UnsafeDiagnosticInt(7)
    source["unsafe_scalar_key"] = {UnsafeDiagnosticInt(8): "safe mapped value"}
    source["equals_authorization_text"] = (
        "provider-client --authorization=Bearer equals-authorization-secret"
    )
    source["quoted_password_text"] = (
        'provider-client --password="quoted-first-secret quoted-second-secret"'
    )
    source["plain_space_argv"] = [
        "provider-client",
        "--password=plain-first-secret plain-second-secret",
    ]
    source["escaped_quote_password_text"] = (
        'provider-client --password "escaped-first-secret\\" escaped-second-secret"'
    )
    format_exception = ValueError(
        "safe=%s password=%s",
        "retained-exception-context",
        "exception-format-secret",
    )
    source["format_exception"] = format_exception
    compound_exception_args = compound_exception.args
    format_exception_args = format_exception.args
    source_without_error = dict(source)
    source_without_error.pop("error")
    source_without_error.pop("compound_exception")
    source_without_error.pop("format_exception")
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
    assert "opaque-exception-secret" not in rendered
    assert "opaque-cmd-secret" not in rendered
    assert "opaque-stderr-secret" not in rendered
    assert "opaque-interior-secret" not in rendered
    assert "opaque-camel-secret" not in rendered
    assert "opaque-access-secret" not in rendered
    assert "opaque-auth-secret" not in rendered
    assert "format-secret" not in rendered
    assert "json-secret-one" not in rendered
    assert "json-secret-two" not in rendered
    assert "python-secret-one" not in rendered
    assert "python-secret-two" not in rendered
    assert "hybrid-auth-secret" not in rendered
    assert "comma-secret" not in rendered
    assert "semicolon-secret" not in rendered
    assert "tail-secret" not in rendered
    assert "semicolon-query-secret" not in rendered
    assert "second-query-secret" not in rendered
    assert "opaque-format-user" not in rendered
    assert "opaque-format-password" not in rendered
    assert "opaque-brace-one" not in rendered
    assert "opaque-brace-two" not in rendered
    assert "opaque-acronym-dsn" not in rendered
    assert "opaque-acronym-token" not in rendered
    assert "opaque-composite-tail" not in rendered
    assert "opaque-escaped-tail" not in rendered
    assert "opaque-double-quote" not in rendered
    assert "opaque-single-quote" not in rendered
    assert "opaque-space" not in rendered
    assert "opaque-space-key-secret" not in rendered
    assert "opaque-header-secret" not in rendered
    assert "inner-secret" not in rendered
    assert "tail-secret" not in rendered
    assert "mixed-format-secret" not in rendered
    assert "mixed-brace-secret" not in rendered
    assert "tuple-key-secret" not in rendered
    assert "bytes-key-secret" not in rendered
    assert "frozenset-key-secret" not in rendered
    assert "registered-object-secret" not in rendered
    assert "opaque-cookie-tail-secret" not in rendered
    assert "opaque-encoded-userinfo-secret" not in rendered
    assert "opaque-double-encoded-secret" not in rendered
    assert "opaque-double-query-secret" not in rendered
    assert "opaque-fully-encoded-query-secret" not in rendered
    assert "indexed-format-secret" not in rendered
    assert "dynamic-width-secret" not in rendered
    assert "dynamic-precision-secret" not in rendered
    assert "unsafe-scalar-secret" not in rendered
    assert "equals-authorization-secret" not in rendered
    assert "quoted-first-secret" not in rendered
    assert "quoted-second-secret" not in rendered
    assert "plain-first-secret" not in rendered
    assert "plain-second-secret" not in rendered
    assert "escaped-first-secret" not in rendered
    assert "escaped-second-secret" not in rendered
    assert "exception-format-secret" not in rendered
    assert "[2001:db8::1]" in rendered
    assert "provider timeout" in rendered
    assert "sslmode=require" in rendered
    assert "attempt': 3" in rendered
    assert "retained context" in rendered
    assert "retained-format-context" in rendered
    assert "retained-brace-context" in rendered
    assert "retained-exception-context" in rendered
    assert "retained-indexed-context" in rendered
    assert REDACTED in rendered
    assert isinstance(redacted["error"], RedactedDiagnostic)  # type: ignore[index]

    source_without_error = dict(source)
    source_without_error.pop("error")
    source_without_error.pop("compound_exception")
    source_without_error.pop("format_exception")
    assert source_without_error == untouched
    assert compound_exception.args == compound_exception_args
    assert format_exception.args == format_exception_args
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
