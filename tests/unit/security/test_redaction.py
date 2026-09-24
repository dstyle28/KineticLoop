from __future__ import annotations

import copy
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
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


class UnsafeReturnCode(int):
    def __format__(self, format_spec: str) -> str:
        del format_spec
        return "RETURN_CODE_SECRET"


class UnsafeDiagnosticStr(str):
    def __str__(self) -> str:
        return "attacker-controlled-str-rendering"


class UnsafeDiagnosticBytes(bytes):
    def __bytes__(self) -> bytes:
        return b"attacker-controlled-bytes-rendering"


class StatefulDiagnosticList(list[str | bytes]):
    def __init__(self, values: list[str | bytes]) -> None:
        super().__init__(values)
        self.iteration_count = 0

    def __iter__(self) -> Iterator[str | bytes]:
        self.iteration_count += 1
        if self.iteration_count == 1:
            return iter(("safe", "safe"))
        return list.__iter__(self)


class StatefulDiagnosticTuple(tuple[str | bytes, ...]):
    iteration_count: int

    def __new__(cls, values: tuple[str | bytes, ...]) -> StatefulDiagnosticTuple:
        instance = super().__new__(cls, values)
        instance.iteration_count = 0
        return instance

    def __iter__(self) -> Iterator[str | bytes]:
        self.iteration_count += 1
        if self.iteration_count == 1:
            return iter(("safe", "safe"))
        return tuple.__iter__(self)


class DeceptiveLengthList(list[str]):
    def __len__(self) -> int:
        return 0


class StatefulMappingTuple(tuple[str, ...]):
    iteration_count: int

    def __new__(cls, values: tuple[str, ...]) -> StatefulMappingTuple:
        instance = super().__new__(cls, values)
        instance.iteration_count = 0
        return instance

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        if self.iteration_count == 1:
            return tuple.__iter__(self)
        return iter(("safe",))


class StatefulMappingFrozenSet(frozenset[str]):
    iteration_count: int

    def __new__(cls, values: frozenset[str]) -> StatefulMappingFrozenSet:
        instance = super().__new__(cls, values)
        instance.iteration_count = 0
        return instance

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        if self.iteration_count == 1:
            return frozenset.__iter__(self)
        return iter(("safe",))


class HostileDiagnosticDict(dict[str, str]):
    items_calls: int = 0

    def items(self) -> Any:
        self.items_calls += 1
        self["mutated"] = "source-was-mutated"
        return (("safe", dict.__getitem__(self, "password")),)


class HostileDiagnosticSet(set[str]):
    iteration_count: int = 0

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        self.add("source-was-mutated")
        return set.__iter__(self)


class HostileDiagnosticFrozenSet(frozenset[str]):
    iteration_count: int = 0

    def __iter__(self) -> Iterator[str]:
        self.iteration_count += 1
        return iter(("attacker-substituted-value",))


def test_nested_redaction_is_non_mutating_and_authority_neutral() -> None:
    secret_named_value_type = type(SENTINEL, (), {})
    secret_named_error_type = type(SENTINEL, (ValueError,), {})
    deeply_encoded_sentinel = SENTINEL
    for _ in range(9):
        deeply_encoded_sentinel = quote(deeply_encoded_sentinel, safe="")
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
        "over_depth_encoded_registered": deeply_encoded_sentinel,
        f"registered-key-{SENTINEL}": "safe value",
        "canonical_evidence": evidence,
    }
    child = secret_named_error_type(
        {"password": "opaque-exception-secret", "safe": "child context"}
    )
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
    source["secret_named_value"] = secret_named_value_type()
    source["secret_named_key"] = {secret_named_value_type(): "safe type-key value"}
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
    source["encoded_compound_query"] = (
        "https://provider.invalid/path?safe%3Dok%26token%3Dopaque-compound-query-secret"
    )
    source["encoded_nested_query"] = (
        "https://provider.invalid/path?safe=ok%26token%3Dopaque-nested-query-secret"
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
    source["bytes_argv"] = [b"provider-client", b"--password", b"opaque-byte-secret"]
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
    source_without_error.pop("secret_named_value")
    source_without_error.pop("secret_named_key")
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
    assert "opaque-compound-query-secret" not in rendered
    assert "opaque-nested-query-secret" not in rendered
    assert "indexed-format-secret" not in rendered
    assert "dynamic-width-secret" not in rendered
    assert "dynamic-precision-secret" not in rendered
    assert "unsafe-scalar-secret" not in rendered
    assert "equals-authorization-secret" not in rendered
    assert "quoted-first-secret" not in rendered
    assert "quoted-second-secret" not in rendered
    assert "plain-first-secret" not in rendered
    assert "plain-second-secret" not in rendered
    assert "opaque-byte-secret" not in rendered
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
    source_without_error.pop("secret_named_value")
    source_without_error.pop("secret_named_key")
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


def test_nested_query_credentials_are_redacted_recursively() -> None:
    nested_url_secret = "NESTED_URL_SECRET"
    nested_db_secret = "NESTED_DB_SECRET"
    nested_query_secret = "NESTED_QUERY_SECRET"
    nested_assignment_secret = "NESTED_ASSIGN_SECRET"
    nested_url = f"https://alice:{nested_url_secret}@inner.invalid/path"
    nested_database_url = (
        f"postgresql://dbuser:{nested_db_secret}@db.invalid/data"
        f"?token={nested_query_secret}"
    )
    recursively_encoded = quote(quote(nested_url, safe=""), safe="")
    values = (
        f"https://outer.invalid/?redirect={quote(nested_url, safe='')}",
        f"https://outer.invalid/?next={quote(nested_database_url, safe='')}",
        "https://outer.invalid/?payload="
        + quote(f"password={nested_assignment_secret}", safe=""),
        f"https://outer.invalid/?redirect={recursively_encoded}",
    )

    rendered = repr(Redactor().redact(values))

    for secret in (
        nested_url_secret,
        nested_db_secret,
        nested_query_secret,
        nested_assignment_secret,
    ):
        assert secret not in rendered
        assert quote(secret, safe="") not in rendered


def test_nested_brace_format_fields_redact_outer_credential_arguments() -> None:
    nested_width_secret = "NESTED_BRACE_WIDTH_SECRET"
    nested_precision_secret = "NESTED_BRACE_PRECISION_SECRET"
    width_values = (
        "password={0:{1}}",
        nested_width_secret,
        ">20",
    )
    precision_values = (
        "safe={0} token={1:.{2}}",
        "retained-context",
        nested_precision_secret,
        "8",
    )
    error = ValueError("password={0:{1}}", nested_width_secret, ">20")
    chained = RuntimeError("safe outer")
    chained.__cause__ = error

    rendered_values = repr(
        (Redactor().redact(width_values), Redactor().redact(precision_values))
    )
    rendered_error = str(Redactor().exception_diagnostic(chained))

    assert nested_width_secret not in rendered_values
    assert nested_precision_secret not in rendered_values
    assert nested_width_secret not in rendered_error
    assert "retained-context" in rendered_values


def test_subprocess_return_codes_cannot_bypass_redaction() -> None:
    direct = subprocess.CalledProcessError(
        UnsafeReturnCode(9),
        ["provider-client", "status"],
    )
    chained = RuntimeError("outer failure")
    chained.__cause__ = subprocess.CalledProcessError(
        "STRING_RETURN_CODE_SECRET",  # type: ignore[arg-type]
        ["provider-client", "status"],
    )
    redactor = Redactor(("RETURN_CODE_SECRET", "STRING_RETURN_CODE_SECRET"))

    direct_rendered = str(redactor.exception_diagnostic(direct))
    chained_rendered = str(redactor.exception_diagnostic(chained))

    assert "RETURN_CODE_SECRET" not in direct_rendered
    assert "STRING_RETURN_CODE_SECRET" not in chained_rendered
    assert "<diagnostic-value>" in direct_rendered
    assert REDACTED in chained_rendered


def test_string_subclass_sequence_relationships_fail_closed() -> None:
    option_secret = "UNREGISTERED_OPTION_VALUE"
    format_secret = "UNREGISTERED_FORMAT_VALUE"
    bytes_secret = b"UNREGISTERED_BYTES_VALUE"
    authorization_secret = "UNREGISTERED_AUTHORIZATION_VALUE"
    exception_secret = "UNREGISTERED_EXCEPTION_VALUE"
    values = (
        [UnsafeDiagnosticStr("--password"), option_secret],
        (UnsafeDiagnosticStr("password=%s"), format_secret),
        [UnsafeDiagnosticBytes(b"--password"), bytes_secret],
        [
            UnsafeDiagnosticStr("--authorization"),
            UnsafeDiagnosticStr("Bearer"),
            authorization_secret,
        ],
    )
    error = ValueError(UnsafeDiagnosticStr("password=%s"), exception_secret)

    rendered_values = repr(Redactor().redact(values))
    rendered_error = str(Redactor().exception_diagnostic(error))

    assert option_secret not in rendered_values
    assert format_secret not in rendered_values
    assert bytes_secret.decode() not in rendered_values
    assert authorization_secret not in rendered_values
    assert exception_secret not in rendered_error


def test_over_depth_mapping_keys_suppress_associated_values() -> None:
    encoded_key = "".join(f"%{ord(character):02X}" for character in "password")
    for _ in range(8):
        encoded_key = quote(encoded_key, safe="")
    values = (
        {encoded_key: "OVERDEPTH_STRING_KEY_VALUE"},
        {encoded_key.encode(): "OVERDEPTH_BYTES_KEY_VALUE"},
        {("safe", encoded_key): "OVERDEPTH_TUPLE_KEY_VALUE"},
        {frozenset({"safe", encoded_key}): "OVERDEPTH_FROZENSET_KEY_VALUE"},
    )

    rendered = repr(Redactor().redact(values))

    assert "OVERDEPTH_STRING_KEY_VALUE" not in rendered
    assert "OVERDEPTH_BYTES_KEY_VALUE" not in rendered
    assert "OVERDEPTH_TUPLE_KEY_VALUE" not in rendered
    assert "OVERDEPTH_FROZENSET_KEY_VALUE" not in rendered
    assert REDACTED in rendered


def test_hostile_sequence_containers_are_snapshotted_once() -> None:
    list_secret = "STATEFUL_LIST_VALUE"
    tuple_secret = "STATEFUL_TUPLE_VALUE"
    length_secret = "DECEPTIVE_LENGTH_AUTH_VALUE"
    exception_secret = "STATEFUL_EXCEPTION_VALUE"
    subprocess_secret = "STATEFUL_SUBPROCESS_VALUE"
    stateful_list = StatefulDiagnosticList(["--password", list_secret])
    stateful_tuple = StatefulDiagnosticTuple(("password=%s", tuple_secret))
    deceptive_length = DeceptiveLengthList(
        ["--authorization", "Negotiate", length_secret]
    )
    error = ValueError()
    error.args = StatefulDiagnosticTuple(("password=%s", exception_secret))
    process_error = subprocess.CalledProcessError(
        1,
        StatefulDiagnosticList(["--password", subprocess_secret]),
    )

    rendered = repr(
        Redactor().redact(
            (stateful_list, stateful_tuple, deceptive_length, error, process_error)
        )
    )

    for secret in (
        list_secret,
        tuple_secret,
        length_secret,
        exception_secret,
        subprocess_secret,
    ):
        assert secret not in rendered
    assert stateful_list.iteration_count == 0
    assert stateful_tuple.iteration_count == 0


def test_extensible_authorization_schemes_fail_closed() -> None:
    negotiate_secret = "NEGOTIATE_AUTH_VALUE"
    aws_secret = "AWS4_AUTH_VALUE"
    subclass_secret = "SUBCLASS_AUTH_VALUE"
    values = (
        ["--authorization", "Negotiate", negotiate_secret],
        [b"--authorization", b"AWS4-HMAC-SHA256", aws_secret.encode()],
        [
            UnsafeDiagnosticStr("--authorization"),
            UnsafeDiagnosticStr("Custom-Scheme"),
            subclass_secret,
        ],
    )

    rendered = repr(Redactor().redact(values))

    assert negotiate_secret not in rendered
    assert aws_secret not in rendered
    assert subclass_secret not in rendered


def test_malformed_sensitive_formats_suppress_unresolved_arguments() -> None:
    percent_secret = "MALFORMED_PERCENT_VALUE"
    mixed_percent_secret = "MALFORMED_MIXED_PERCENT_VALUE"
    brace_secret = "MALFORMED_BRACE_VALUE"
    mixed_numbering_secret = "MIXED_NUMBERING_VALUE"
    values = (
        ("password=%", percent_secret),
        ("safe=%s password=%", "retained-percent-context", mixed_percent_secret),
        ("safe={} password={", "retained-brace-context", brace_secret),
        ("safe={0} password={}", "retained-numbering-context", mixed_numbering_secret),
    )
    direct_error = ValueError("password=%", percent_secret)
    chained_error = RuntimeError("outer")
    chained_error.__cause__ = ValueError(
        "safe={0} password={}", "retained-numbering-context", mixed_numbering_secret
    )

    rendered = repr(Redactor().redact(values))
    rendered_direct = str(Redactor().exception_diagnostic(direct_error))
    rendered_chained = str(Redactor().exception_diagnostic(chained_error))

    assert percent_secret not in rendered
    assert mixed_percent_secret not in rendered
    assert brace_secret not in rendered
    assert mixed_numbering_secret not in rendered
    assert percent_secret not in rendered_direct
    assert mixed_numbering_secret not in rendered_chained


def test_extensible_text_authorization_and_dotted_assignments_are_redacted() -> None:
    negotiate_secret = "TEXT_NEGOTIATE_VALUE"
    custom_secret = "TEXT_CUSTOM_SCHEME_VALUE"
    dotted_api_secret = "DOTTED_API_KEY_VALUE"
    dotted_database_secret = "DOTTED_DATABASE_URL_VALUE"
    encoded_authorization = quote(
        f"Authorization AWS4-HMAC-SHA256 {custom_secret}", safe=""
    )
    values = (
        f"Authorization Negotiate {negotiate_secret}",
        encoded_authorization,
        f"api.key={dotted_api_secret}",
        f"database.url={dotted_database_secret}",
    )
    process_error = subprocess.CalledProcessError(
        1,
        ["provider-client", "status"],
        stderr=f"Authorization Custom-Scheme {custom_secret}",
    )

    rendered = repr(Redactor().redact((*values, process_error)))

    for secret in (
        negotiate_secret,
        custom_secret,
        dotted_api_secret,
        dotted_database_secret,
    ):
        assert secret not in rendered
        assert quote(secret, safe="") not in rendered


def test_over_depth_sequence_token_suppresses_all_unresolved_arguments() -> None:
    encoded_authorization = "".join(
        f"%{ord(character):02X}" for character in "--authorization"
    )
    for _ in range(8):
        encoded_authorization = quote(encoded_authorization, safe="")
    secret = "OVERDEPTH_AUTHORIZATION_VALUE"

    rendered = repr(
        Redactor().redact([encoded_authorization, "AWS4-HMAC-SHA256", secret])
    )

    assert secret not in rendered
    assert "AWS4-HMAC-SHA256" not in rendered


def test_composite_mapping_keys_are_snapshotted_once() -> None:
    tuple_key = StatefulMappingTuple(("password",))
    frozenset_key = StatefulMappingFrozenSet(frozenset({"clientSecret"}))
    tuple_secret = "STATEFUL_TUPLE_KEY_VALUE"
    frozenset_secret = "STATEFUL_FROZENSET_KEY_VALUE"

    rendered = repr(
        Redactor().redact(
            ({tuple_key: tuple_secret}, {frozenset_key: frozenset_secret})
        )
    )

    assert tuple_secret not in rendered
    assert frozenset_secret not in rendered
    assert tuple_key.iteration_count == 0
    assert frozenset_key.iteration_count == 0


def test_empty_delimiter_authorization_suppresses_scheme_and_credential() -> None:
    raw_secret = "EMPTY_AUTHORIZATION_VALUE"
    encoded_secret = "ENCODED_EMPTY_AUTHORIZATION_VALUE"
    colon_secret = "COLON_EMPTY_AUTHORIZATION_VALUE"
    values = (
        ["--authorization=", "Negotiate", raw_secret],
        ["--authorization%3D", "Custom-Scheme", encoded_secret],
        ["--authorization%3A", "AWS4-HMAC-SHA256", colon_secret],
    )
    error = ValueError("--authorization=", "Negotiate", raw_secret)

    rendered = repr(Redactor().redact(values))
    rendered_error = str(Redactor().exception_diagnostic(error))

    assert raw_secret not in rendered
    assert encoded_secret not in rendered
    assert colon_secret not in rendered
    assert raw_secret not in rendered_error


def test_mixed_format_dialects_suppress_unresolved_arguments() -> None:
    brace_secret = "MIXED_BRACE_DIALECT_VALUE"
    percent_secret = "MIXED_PERCENT_DIALECT_VALUE"
    values = (
        ("safe=%s password={}", "retained-percent-context", brace_secret),
        ("safe={} password=%s", "retained-brace-context", percent_secret),
    )
    direct_error = ValueError(
        "safe=%s password={}", "retained-percent-context", brace_secret
    )
    chained_error = RuntimeError("outer")
    chained_error.__cause__ = ValueError(
        "safe={} password=%s", "retained-brace-context", percent_secret
    )

    rendered = repr(Redactor().redact(values))
    rendered_direct = str(Redactor().exception_diagnostic(direct_error))
    rendered_chained = str(Redactor().exception_diagnostic(chained_error))

    assert brace_secret not in rendered
    assert percent_secret not in rendered
    assert brace_secret not in rendered_direct
    assert percent_secret not in rendered_chained


def test_unresolved_sensitive_fields_and_authorization_formats_fail_closed() -> None:
    out_of_range_secret = "OUT_OF_RANGE_FIELD_VALUE"
    named_secret = "NAMED_FIELD_VALUE"
    authorization_secret = "AUTHORIZATION_FORMAT_VALUE"
    values = (
        ("password={99}", out_of_range_secret),
        ("password={credential}", named_secret),
        ("Authorization %s %s", "Negotiate", authorization_secret),
    )
    direct_error = ValueError("password={99}", out_of_range_secret)
    chained_error = RuntimeError("outer")
    chained_error.__cause__ = ValueError("password={credential}", named_secret)
    process_error = subprocess.CalledProcessError(
        1,
        ["provider-client", "status"],
        stderr=(  # type: ignore[arg-type]
            "Authorization %s %s",
            "Custom-Scheme",
            authorization_secret,
        ),
    )

    rendered = repr(Redactor().redact((*values, process_error)))
    rendered_direct = str(Redactor().exception_diagnostic(direct_error))
    rendered_chained = str(Redactor().exception_diagnostic(chained_error))

    assert out_of_range_secret not in rendered
    assert named_secret not in rendered
    assert authorization_secret not in rendered
    assert out_of_range_secret not in rendered_direct
    assert named_secret not in rendered_chained


def test_hostile_dict_subclasses_use_trusted_snapshot_without_mutation() -> None:
    secret = "HOSTILE_MAPPING_VALUE"
    source = HostileDiagnosticDict(password=secret)
    before = tuple(dict.items(source))

    rendered = repr(Redactor().redact(source))

    assert secret not in rendered
    assert tuple(dict.items(source)) == before
    assert source.items_calls == 0


def test_split_authorization_suppresses_all_trailing_components() -> None:
    signature_secret = "MULTIPART_SIGNATURE_VALUE"
    command = [
        "--authorization",
        "AWS4-HMAC-SHA256",
        "Credential=FIRST",
        "SignedHeaders=host",
        f"Signature={signature_secret}",
    ]
    direct_error = ValueError(*command)
    process_error = subprocess.CalledProcessError(
        1,
        command,
        stderr=tuple(command),  # type: ignore[arg-type]
    )

    rendered = repr(Redactor().redact((command, direct_error, process_error)))

    assert signature_secret not in rendered
    assert "Credential=FIRST" not in rendered
    assert "SignedHeaders=host" not in rendered


def test_encoded_delimiters_cannot_escape_credential_redaction() -> None:
    password_tail = "ENCODED_NEWLINE_PASSWORD_TAIL"
    authorization_tail = "ENCODED_NEWLINE_AUTHORIZATION_TAIL"
    semicolon_tail = "SEMICOLON_AUTHORIZATION_TAIL"
    values = (
        f"unrecognized arguments: --password=FIRST%0A{password_tail}",
        f"Authorization Custom FIRST%0A{authorization_tail}",
        f"Authorization Custom FIRST;{semicolon_tail}",
    )
    direct_error = ValueError(values[0])
    process_error = subprocess.CalledProcessError(
        1,
        ["provider-client", "status"],
        stderr=values[1],
    )

    rendered = repr(Redactor().redact((*values, direct_error, process_error)))

    assert password_tail not in rendered
    assert authorization_tail not in rendered
    assert semicolon_tail not in rendered


def test_single_and_combined_authorization_values_fail_closed() -> None:
    single_secret = "SINGLE_TOKEN_AUTHORIZATION_VALUE"
    encoded_secret = "ENCODED_SINGLE_AUTHORIZATION_VALUE"
    multipart_secret = "COMBINED_MULTIPART_SIGNATURE_VALUE"
    encoded_text = quote(f"Authorization {encoded_secret}", safe="")
    combined = [
        "Authorization AWS4-HMAC-SHA256",
        "Credential=FIRST",
        "SignedHeaders=host",
        f"Signature={multipart_secret}",
    ]
    direct_error = ValueError(f"Authorization {single_secret}")
    process_error = subprocess.CalledProcessError(
        1,
        combined,
        stderr=tuple(combined),  # type: ignore[arg-type]
    )

    rendered = repr(
        Redactor().redact(
            (
                f"Authorization {single_secret}",
                encoded_text,
                combined,
                direct_error,
                process_error,
            )
        )
    )

    assert single_secret not in rendered
    assert encoded_secret not in rendered
    assert multipart_secret not in rendered
    assert "Credential=FIRST" not in rendered
    assert "SignedHeaders=host" not in rendered


def test_colon_delimited_sensitive_query_values_are_redacted() -> None:
    raw_secret = "COLON_QUERY_VALUE"
    encoded_secret = "ENCODED_COLON_QUERY_VALUE"
    mixed_secret = "MIXED_COLON_QUERY_VALUE"
    values = (
        f"https://x.invalid/?token:{raw_secret}",
        f"https://x.invalid/?password%3A{encoded_secret}",
        f"https://x.invalid/?safe=retained&authorization:{mixed_secret}",
    )

    rendered = repr(tuple(Redactor().text(value) for value in values))

    assert raw_secret not in rendered
    assert encoded_secret not in rendered
    assert mixed_secret not in rendered
    assert "retained" in rendered


def test_set_subclasses_use_trusted_snapshots_without_mutation() -> None:
    mutable = HostileDiagnosticSet({"safe-set-value"})
    immutable = HostileDiagnosticFrozenSet({"safe-frozenset-value"})
    mutable_before = set(set.__iter__(mutable))
    immutable_before = frozenset(frozenset.__iter__(immutable))

    rendered = repr(Redactor().redact((mutable, immutable)))

    assert "safe-set-value" in rendered
    assert "safe-frozenset-value" in rendered
    assert set(set.__iter__(mutable)) == mutable_before
    assert frozenset(frozenset.__iter__(immutable)) == immutable_before
    assert mutable.iteration_count == 0
    assert immutable.iteration_count == 0
