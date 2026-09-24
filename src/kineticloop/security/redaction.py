"""Recursive, non-mutating redaction for presentation-only diagnostics."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias
from urllib.parse import quote_plus, unquote, unquote_plus, urlsplit, urlunsplit

from kineticloop.config.secrets import SecretValue

REDACTED = "[REDACTED]"
_SECRET_MARKER = "__KINETICLOOP_REDACTED_SECRET__"
_USERINFO_MARKER = "__KINETICLOOP_REDACTED_USERINFO__"

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "cookie",
        "credential",
        "credentials",
        "database_url",
        "dsn",
        "passwd",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")
_CREDENTIAL_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\r\n]*?@[^\s,;]+")
_PERCENT_PLACEHOLDER = re.compile(
    r"(?<!%)%(?!%)(?:\([^)]+\))?[-+#0 ]*(?:\*|\d*)(?:\.(?:\*|\d+))?[A-Za-z]"
)
_BRACE_PLACEHOLDER = re.compile(r"(?<!\{)\{[^{}]*\}(?!\})")
_SENSITIVE_KEY_EXPRESSION = (
    r"access[\s_-]?token|api[\s_-]?key|authorization|client[\s_-]?secret|cookie|"
    r"credential(?:s)?|database[\s_-]?url|dsn|passwd|password|refresh[\s_-]?token|"
    r"secret|token"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    rf"(?i)(?P<quote>[\"']?)(?P<key>[a-z0-9_. -]*(?:{_SENSITIVE_KEY_EXPRESSION})"
    r"[a-z0-9_. -]*)(?P=quote)(?P<separator>\s*[:=]\s*)"
)
_COMMAND_OPTION = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*=)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|"
    r"(?:bearer|basic|digest|token)\s+[^\r\n]+|[^\r\n]+)"
)
_COMMAND_SEPARATE = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*\s+)"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|"
    r"(?:bearer|basic|digest|token)\s+[^\r\n]+|[^\r\n]+)"
)
_AUTH_HEADER = re.compile(
    r"(?i)(?P<prefix>\bauthorization\s+(?:bearer|basic|digest|token)\s+)"
    r"(?P<value>[^;\r\n]+)"
)
_FORMAT_PLACEHOLDER = re.compile(
    rf"(?:{_PERCENT_PLACEHOLDER.pattern})|(?:{_BRACE_PLACEHOLDER.pattern})"
)

DiagnosticScalar: TypeAlias = str | bytes | int | float | bool | None


def _normalized_key(value: object) -> str:
    camel_split = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", str(value).strip())
    camel_split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", camel_split)
    return re.sub(r"[^a-z0-9]+", "_", camel_split.lower()).strip("_")


def _is_sensitive_key(value: object) -> bool:
    normalized = _normalized_key(value)
    padded = f"_{normalized}_"
    return any(f"_{part}_" in padded for part in _SENSITIVE_KEY_PARTS)


def _format_sensitive_positions(value: str) -> set[int]:
    positions: set[int] = set()
    active_sensitive = False
    previous_end = 0
    automatic_index = 0
    percent_index = 0
    for placeholder in _FORMAT_PLACEHOLDER.finditer(value):
        segment = value[previous_end : placeholder.start()]
        assignments = list(re.finditer(r"(?i)([a-z0-9_. -]+)\s*[:=]\s*$", segment))
        if assignments:
            active_sensitive = _is_sensitive_key(assignments[-1].group(1))
        token = placeholder.group(0)
        if token.startswith("%"):
            star_count = token.count("*")
            argument_index = percent_index + star_count
            percent_index += star_count + 1
        else:
            field_name = token[1:-1].split("!", maxsplit=1)[0].split(":", maxsplit=1)[0]
            root_name = re.split(r"[.[]", field_name, maxsplit=1)[0]
            if root_name.isdigit():
                argument_index = int(root_name)
            elif not root_name:
                argument_index = automatic_index
                automatic_index += 1
            else:
                argument_index = 0
        if active_sensitive:
            positions.add(argument_index)
        previous_end = placeholder.end()
    return positions


def _sequence_sensitive_positions(value: str) -> set[int]:
    format_positions = _format_sensitive_positions(value)
    if format_positions:
        return format_positions
    stripped = value.lstrip("-").strip()
    for separator in ("=", ":"):
        key, found, member = stripped.partition(separator)
        if found and _is_sensitive_key(key):
            if not member or member.casefold() in {"bearer", "basic", "digest", "token"}:
                return {0}
            return set()
    return {0} if _is_sensitive_key(stripped) else set()


def _sensitive_value_end(value: str, start: int) -> int:
    if start >= len(value):
        return start
    opening = value[start]
    pairs = {"[": "]", "(": ")", "{": "}"}
    if opening in pairs:
        stack = [pairs[opening]]
        quote: str | None = None
        escaped = False
        index = start + 1
        while index < len(value) and stack:
            character = value[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character in pairs:
                stack.append(pairs[character])
            elif character == stack[-1]:
                stack.pop()
            index += 1
        return index
    if opening in {'"', "'"}:
        index = start + 1
        escaped = False
        while index < len(value):
            character = value[index]
            index += 1
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == opening:
                break
        return index
    end = value.find("\n", start)
    return len(value) if end < 0 else end


def _redact_sensitive_assignments(value: str) -> str:
    result: list[str] = []
    cursor = 0
    while match := _SENSITIVE_ASSIGNMENT.search(value, cursor):
        value_start = match.end()
        value_end = _sensitive_value_end(value, value_start)
        result.append(value[cursor:value_start])
        result.append(REDACTED)
        cursor = value_end
    result.append(value[cursor:])
    return "".join(result)


def _stable_unquote(value: str, *, plus: bool = False) -> str | None:
    decoder = unquote_plus if plus else unquote
    decoded = value
    for _ in range(8):
        next_value = decoder(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return None


def _percent_byte_pattern(value: int) -> str:
    encoded = f"{value:02X}"
    return "%" + "".join(
        f"[{nibble.lower()}{nibble.upper()}]" if nibble.isalpha() else nibble for nibble in encoded
    )


def _secret_pattern(value: str) -> re.Pattern[str]:
    """Match raw and arbitrarily percent-encoded spellings of an exact secret."""

    pieces: list[str] = []
    for character in value:
        choices = [re.escape(character)]
        percent_encoded = "".join(_percent_byte_pattern(byte) for byte in character.encode())
        choices.append(percent_encoded)
        if character == " ":
            choices.append(r"\+")
        pieces.append(f"(?:{'|'.join(dict.fromkeys(choices))})")
    return re.compile("".join(pieces))


@dataclass(frozen=True, slots=True)
class RedactedDiagnostic:
    """Display-only exception details with no admission or authority behavior."""

    exception_type: str
    message: str
    details: tuple[str, ...] = ()
    cause: RedactedDiagnostic | None = None

    def __str__(self) -> str:
        rendered = f"{self.exception_type}: {self.message}"
        if self.details:
            rendered += " (" + "; ".join(self.details) + ")"
        if self.cause is not None:
            rendered += f"; caused by {self.cause}"
        return rendered

    def __repr__(self) -> str:
        return f"RedactedDiagnostic({str(self)!r})"


class Redactor:
    """Copy diagnostic values while removing registered and key-shaped secrets."""

    __slots__ = ("__patterns",)

    def __init__(self, secrets: Sequence[str | SecretValue] = ()) -> None:
        raw_values: set[str] = set()
        for secret in secrets:
            raw = secret.reveal() if type(secret) is SecretValue else secret
            if type(raw) is not str:
                raise TypeError("redaction secrets must be strings or SecretValue instances")
            if raw:
                raw_values.add(raw)
        self.__patterns = tuple(
            _secret_pattern(value)
            for value in sorted(raw_values, key=lambda item: (-len(item), item))
        )

    def text(self, value: str) -> str:
        """Redact one diagnostic string without changing the source value."""

        result = value
        for pattern in self.__patterns:
            result = pattern.sub(_SECRET_MARKER, result)
        result = _CREDENTIAL_URL.sub(lambda match: self._url(match.group(0)), result)
        result = _URL.sub(lambda match: self._url(match.group(0)), result)
        result = result.replace(_SECRET_MARKER, REDACTED)
        result = result.replace(_USERINFO_MARKER, REDACTED)
        result = _COMMAND_OPTION.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        result = _COMMAND_SEPARATE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        result = _AUTH_HEADER.sub(
            lambda match: f"{match.group('prefix')}{REDACTED}",
            result,
        )
        return _redact_sensitive_assignments(result)

    def _url(self, matched_url: str) -> str:
        trailing = ""
        while matched_url and matched_url[-1] in ".,;)":
            trailing = matched_url[-1] + trailing
            matched_url = matched_url[:-1]
        try:
            parsed = urlsplit(matched_url)
            authority = parsed
            has_userinfo = parsed.username is not None or parsed.password is not None
            decoded_netloc = _stable_unquote(parsed.netloc)
            if decoded_netloc is None:
                return REDACTED + trailing
            if not has_userinfo and "@" in decoded_netloc:
                authority = urlsplit(f"//{decoded_netloc.rsplit('@', maxsplit=1)[1]}")
                has_userinfo = True
            hostname = authority.hostname
            if not parsed.scheme or hostname is None:
                return REDACTED + trailing
            host = f"[{hostname}]" if ":" in hostname else hostname
            if authority.port is not None:
                host = f"{host}:{authority.port}"
            if has_userinfo:
                host = f"{_USERINFO_MARKER}@{host}"
            query_parts = re.split(r"([&;])", parsed.query)
            for index in range(0, len(query_parts), 2):
                key, found, value = query_parts[index].partition("=")
                decoded_key = _stable_unquote(key, plus=True)
                if decoded_key is None:
                    return REDACTED + trailing
                if found and _is_sensitive_key(decoded_key):
                    query_parts[index] = f"{key}={quote_plus(REDACTED)}"
            sanitized = urlunsplit(
                (parsed.scheme, host, parsed.path, "".join(query_parts), parsed.fragment)
            )
        except (TypeError, ValueError):
            sanitized = REDACTED
        return sanitized + trailing

    def redact(self, value: object) -> object:
        """Return a recursively redacted diagnostic copy of a supported value."""

        if type(value) is SecretValue:
            return REDACTED
        if isinstance(value, BaseException):
            return self.exception_diagnostic(value)
        if type(value) is str:
            return self.text(value)
        if type(value) is bytes:
            return self.text(value.decode("utf-8", errors="replace")).encode("utf-8")
        if isinstance(value, Mapping):
            result: dict[object, object] = {}
            for key, item in value.items():
                redacted_key = self._redact_mapping_key(key)
                result[redacted_key] = (
                    REDACTED if self._mapping_key_is_sensitive(key) else self.redact(item)
                )
            return result
        if isinstance(value, tuple):
            return tuple(self._redact_sequence(value))
        if isinstance(value, list):
            return self._redact_sequence(value)
        if isinstance(value, set):
            return {self.redact(item) for item in value}
        if isinstance(value, frozenset):
            return frozenset(self.redact(item) for item in value)
        if value is None or type(value) in (int, float, bool):
            return value
        return f"<diagnostic-value:{type(value).__name__}>"

    def _redact_mapping_key(self, key: object) -> object:
        if type(key) is str:
            return self.text(key)
        if type(key) is bytes:
            return self.redact(key)
        if isinstance(key, tuple):
            return tuple(self._redact_mapping_key(item) for item in key)
        if isinstance(key, frozenset):
            return frozenset(self._redact_mapping_key(item) for item in key)
        if key is None or type(key) in (int, float, bool):
            return key
        return f"<diagnostic-key:{type(key).__name__}>"

    def _mapping_key_is_sensitive(self, key: object) -> bool:
        if type(key) is str:
            return _is_sensitive_key(self.text(key))
        if type(key) is bytes:
            decoded = key.decode("utf-8", errors="replace")
            return _is_sensitive_key(self.text(decoded))
        if isinstance(key, (tuple, frozenset)):
            return any(self._mapping_key_is_sensitive(item) for item in key)
        if key is None or type(key) in (int, float, bool):
            return False
        return True

    def _redact_sequence(self, value: Sequence[object]) -> list[object]:
        sensitive_indices: set[int] = set()
        for index, item in enumerate(value):
            if not isinstance(item, str):
                continue
            positions = _sequence_sensitive_positions(item)
            if positions == {0} and index + 1 < len(value):
                next_item = value[index + 1]
                if isinstance(next_item, str) and next_item.casefold() in {
                    "bearer",
                    "basic",
                    "digest",
                    "token",
                }:
                    positions = {0, 1}
            sensitive_indices.update(index + 1 + position for position in positions)
        return [
            REDACTED if index in sensitive_indices else self.redact(item)
            for index, item in enumerate(value)
        ]

    def exception_diagnostic(self, error: BaseException) -> RedactedDiagnostic:
        """Redact an exception, subprocess output, and its chained exceptions."""

        return self._exception_diagnostic(error, frozenset())

    def _exception_diagnostic(
        self,
        error: BaseException,
        seen: frozenset[int],
    ) -> RedactedDiagnostic:
        if id(error) in seen:
            return RedactedDiagnostic(type(error).__name__, "exception cycle omitted")
        details: list[str] = []
        if isinstance(error, subprocess.CalledProcessError):
            details.append(f"returncode={error.returncode}")
            details.append(f"command={self.redact(error.cmd)!r}")
            if error.stdout is not None:
                details.append(f"stdout={self.redact(error.stdout)!r}")
            if error.stderr is not None:
                details.append(f"stderr={self.redact(error.stderr)!r}")
        cause = error.__cause__ or error.__context__
        if isinstance(error, subprocess.CalledProcessError):
            message = f"subprocess failed with return code {error.returncode}"
        else:
            redacted_args = self.redact(error.args)
            assert isinstance(redacted_args, tuple)
            if len(redacted_args) == 1:
                message = str(redacted_args[0])
            else:
                message = repr(redacted_args)
        return RedactedDiagnostic(
            exception_type=type(error).__name__,
            message=message,
            details=tuple(details),
            cause=(
                self._exception_diagnostic(cause, seen | {id(error)}) if cause is not None else None
            ),
        )
