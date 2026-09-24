"""Recursive, non-mutating redaction for presentation-only diagnostics."""

from __future__ import annotations

import re
import string
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
_SCHEMELESS_USERINFO = re.compile(
    r"(?P<userinfo>[^\s/@:]+(?::[^\s/@]*)?@)(?P<host>\[[^\]]+\]|[A-Za-z0-9.-]+)"
)
_PERCENT_PLACEHOLDER = re.compile(
    r"(?<!%)%(?!%)(?:\([^)]+\))?[-+#0 ]*(?:\*|\d*)(?:\.(?:\*|\d+))?[A-Za-z]"
)
_SENSITIVE_KEY_EXPRESSION = (
    r"access[\s_.-]?token|api[\s_.-]?key|authorization|client[\s_.-]?secret|cookie|"
    r"credential(?:s)?|database[\s_.-]?url|dsn|passwd|password|refresh[\s_.-]?token|"
    r"secret|token"
)
_SENSITIVE_ASSIGNMENT = re.compile(
    rf"(?i)(?P<quote>[\"']?)(?P<key>[a-z0-9_. -]*(?:{_SENSITIVE_KEY_EXPRESSION})"
    r"[a-z0-9_. -]*)(?P=quote)(?P<separator>\s*[:=;]\s*)"
)
_COMMAND_OPTION = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*[=:;])"
    r"(?P<value>[\s\S]+)"
)
_COMMAND_SEPARATE = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*\s+)"
    r"(?P<value>[\s\S]+)"
)
_AUTH_HEADER = re.compile(
    r"(?i)(?P<prefix>\bauthorization(?:\s+|\s*[=:;]\s*))"
    r"(?P<value>[\s\S]+)"
)
DiagnosticScalar: TypeAlias = str | bytes | int | float | bool | None
_ALL_FOLLOWING_ARGUMENTS = -1


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
    percent_index = 0
    for placeholder in _PERCENT_PLACEHOLDER.finditer(value):
        segment = value[previous_end : placeholder.start()]
        assignments = list(re.finditer(r"(?i)([a-z0-9_. -]+)\s*[:=]\s*$", segment))
        if assignments:
            active_sensitive = _is_sensitive_key(assignments[-1].group(1))
        token = placeholder.group(0)
        star_count = token.count("*")
        argument_index = percent_index + star_count
        percent_index += star_count + 1
        if active_sensitive:
            positions.add(argument_index)
        previous_end = placeholder.end()

    automatic_index = 0
    formatter = string.Formatter()

    def inspect_braces(format_string: str, *, classify_fields: bool) -> None:
        nonlocal automatic_index
        active_brace_sensitive = False
        for literal, field_name, format_spec, _conversion in formatter.parse(format_string):
            assignments = list(
                re.finditer(r"(?i)([a-z0-9_. -]+)\s*[:=]\s*$", literal)
            )
            if assignments:
                active_brace_sensitive = _is_sensitive_key(assignments[-1].group(1))
            if field_name is None:
                continue
            root_name = re.split(r"[.[]", field_name, maxsplit=1)[0]
            if root_name.isdigit():
                argument_index = int(root_name)
            elif not root_name:
                argument_index = automatic_index
                automatic_index += 1
            else:
                argument_index = _ALL_FOLLOWING_ARGUMENTS
            if classify_fields and active_brace_sensitive:
                positions.add(argument_index)
            if format_spec:
                inspect_braces(format_spec, classify_fields=False)

    try:
        inspect_braces(value, classify_fields=True)
    except ValueError:
        prefix = value.partition("{")[0]
        key, found, _member = prefix.rpartition("=")
        if found and _is_sensitive_key(key):
            positions.add(0)
    return positions


def _has_malformed_sensitive_format(value: str) -> bool:
    if _SENSITIVE_ASSIGNMENT.search(value) is None:
        return False
    index = 0
    has_percent_placeholder = False
    while index < len(value):
        if value[index] != "%":
            index += 1
            continue
        if value.startswith("%%", index):
            index += 2
            continue
        placeholder = _PERCENT_PLACEHOLDER.match(value, index)
        if placeholder is None:
            return True
        has_percent_placeholder = True
        index = placeholder.end()
    saw_automatic = False
    saw_manual = False
    saw_brace_field = False

    def inspect_numbering(format_string: str) -> None:
        nonlocal saw_automatic, saw_brace_field, saw_manual
        for _literal, field_name, format_spec, _conversion in string.Formatter().parse(
            format_string
        ):
            if field_name is None:
                continue
            saw_brace_field = True
            root_name = re.split(r"[.[]", field_name, maxsplit=1)[0]
            if not root_name:
                saw_automatic = True
            elif root_name.isdigit():
                saw_manual = True
            if saw_automatic and saw_manual:
                raise ValueError("mixed automatic and manual field numbering")
            if format_spec:
                inspect_numbering(format_spec)

    try:
        inspect_numbering(value)
    except ValueError:
        return True
    return has_percent_placeholder and saw_brace_field


def _sequence_sensitive_positions(value: str) -> set[int]:
    if _has_malformed_sensitive_format(value):
        return {_ALL_FOLLOWING_ARGUMENTS}
    if re.search(r"(?i)\bauthorization\b", value) and (
        _PERCENT_PLACEHOLDER.search(value) is not None or "{" in value
    ):
        return {_ALL_FOLLOWING_ARGUMENTS}
    format_positions = _format_sensitive_positions(value)
    if format_positions:
        return format_positions
    stripped = value.lstrip("-").strip()
    if re.match(r"(?i)^authorization(?:\b|[=:;])", stripped):
        return {_ALL_FOLLOWING_ARGUMENTS}
    for separator in ("=", ":", ";"):
        key, found, member = stripped.partition(separator)
        if found and _is_sensitive_key(key):
            if _normalized_key(key) == "authorization":
                return {_ALL_FOLLOWING_ARGUMENTS}
            if not member or member.casefold() in {"bearer", "basic", "digest", "token"}:
                return {0}
            return set()
    return {0} if _is_sensitive_key(stripped) else set()


def _sequence_item_text(value: object) -> str | None:
    if type(value) is str:
        return value
    if type(value) is bytes:
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return str.__str__(value)
    if isinstance(value, bytes):
        return bytes.__bytes__(value).decode("utf-8", errors="replace")
    return None


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
    return len(value)


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


def _percent_byte_pattern(value: int, *, depth: int = 1) -> str:
    encoded = f"{value:02X}"
    return (
        "%"
        + ("25" * (depth - 1))
        + "".join(
            f"[{nibble.lower()}{nibble.upper()}]" if nibble.isalpha() else nibble
            for nibble in encoded
        )
    )


def _secret_pattern(value: str) -> re.Pattern[str]:
    """Match raw and arbitrarily percent-encoded spellings of an exact secret."""

    pieces: list[str] = []
    for character in value:
        choices = [re.escape(character)]
        for depth in range(1, 9):
            choices.append(
                "".join(_percent_byte_pattern(byte, depth=depth) for byte in character.encode())
            )
        if character == " ":
            choices.append(r"\+")
            choices.extend(_percent_byte_pattern(ord("+"), depth=depth) for depth in range(1, 9))
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

        return self._text(value, nested_depth=0)

    def _text(self, value: str, *, nested_depth: int) -> str:
        if nested_depth >= 8:
            return REDACTED

        decoded = _stable_unquote(value)
        if decoded is None:
            return REDACTED
        result = decoded
        for pattern in self.__patterns:
            result = pattern.sub(_SECRET_MARKER, result)
        result = _CREDENTIAL_URL.sub(
            lambda match: self._url(match.group(0), nested_depth=nested_depth), result
        )
        result = _URL.sub(
            lambda match: self._url(match.group(0), nested_depth=nested_depth), result
        )
        result = result.replace(_SECRET_MARKER, REDACTED)
        result = result.replace(_USERINFO_MARKER, REDACTED)
        result = _SCHEMELESS_USERINFO.sub(
            lambda match: f"{REDACTED}@{match.group('host')}", result
        )
        result = _COMMAND_OPTION.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        result = _COMMAND_SEPARATE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        result = _AUTH_HEADER.sub(
            lambda match: f"{match.group('prefix')}{REDACTED}",
            result,
        )
        return _redact_sensitive_assignments(result)

    def _url(self, matched_url: str, *, nested_depth: int) -> str:
        if nested_depth >= 8:
            return REDACTED
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
            decoded_query = _stable_unquote(parsed.query, plus=True)
            if decoded_query is None:
                return REDACTED + trailing
            query_parts = re.split(r"([&;])", decoded_query)
            for index in range(0, len(query_parts), 2):
                part = query_parts[index]
                key, found, query_value = part.partition("=")
                if not found:
                    colon_key, colon_found, colon_value = part.partition(":")
                    if colon_found:
                        sanitized_colon_value = (
                            REDACTED
                            if _is_sensitive_key(colon_key)
                            else self._text(
                                colon_value, nested_depth=nested_depth + 1
                            )
                        )
                        query_parts[index] = (
                            f"{quote_plus(colon_key)}%3A{quote_plus(sanitized_colon_value)}"
                        )
                    else:
                        query_parts[index] = quote_plus(
                            self._text(part, nested_depth=nested_depth + 1)
                        )
                    continue
                sanitized_value = (
                    REDACTED
                    if _is_sensitive_key(key)
                    else self._text(query_value, nested_depth=nested_depth + 1)
                )
                query_parts[index] = (
                    f"{quote_plus(key)}={quote_plus(sanitized_value)}"
                )
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
        if isinstance(value, dict):
            result: dict[object, object] = {}
            for key, item in tuple(dict.items(value)):
                snapshot_key = self._snapshot_mapping_key(key)
                redacted_key = self._redact_mapping_key(snapshot_key)
                result[redacted_key] = (
                    REDACTED
                    if self._mapping_key_is_sensitive(snapshot_key)
                    else self.redact(item)
                )
            return result
        if isinstance(value, Mapping):
            return "<diagnostic-mapping>"
        if isinstance(value, tuple):
            return tuple(self._redact_sequence(value))
        if isinstance(value, list):
            return self._redact_sequence(value)
        if isinstance(value, set):
            items = tuple(set.__iter__(value))
            return {self.redact(item) for item in items}
        if isinstance(value, frozenset):
            items = tuple(frozenset.__iter__(value))
            return frozenset(self.redact(item) for item in items)
        if value is None or type(value) in (int, float, bool):
            return value
        return "<diagnostic-value>"

    def _snapshot_mapping_key(self, key: object) -> object:
        if isinstance(key, tuple):
            return tuple(
                self._snapshot_mapping_key(item) for item in tuple.__iter__(key)
            )
        if isinstance(key, frozenset):
            return frozenset(
                self._snapshot_mapping_key(item) for item in frozenset.__iter__(key)
            )
        return key

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
        return "<diagnostic-key>"

    def _mapping_key_is_sensitive(self, key: object) -> bool:
        if type(key) is str:
            decoded = _stable_unquote(key)
            if decoded is None:
                return True
            return _is_sensitive_key(decoded) or any(
                pattern.search(decoded) for pattern in self.__patterns
            )
        if type(key) is bytes:
            decoded = _stable_unquote(key.decode("utf-8", errors="replace"))
            if decoded is None:
                return True
            return _is_sensitive_key(decoded) or any(
                pattern.search(decoded) for pattern in self.__patterns
            )
        if isinstance(key, (tuple, frozenset)):
            return any(self._mapping_key_is_sensitive(item) for item in key)
        if key is None or type(key) in (int, float, bool):
            return False
        return True

    def _redact_sequence(self, value: Sequence[object]) -> list[object]:
        if isinstance(value, list):
            items = tuple(list.__iter__(value))
        elif isinstance(value, tuple):
            items = tuple(tuple.__iter__(value))
        else:
            raise TypeError("diagnostic sequence must be a list or tuple")
        sensitive_indices: set[int] = set()
        for index, item in enumerate(items):
            item_text = _sequence_item_text(item)
            if item_text is None:
                continue
            decoded_item = _stable_unquote(item_text)
            positions = (
                {_ALL_FOLLOWING_ARGUMENTS}
                if decoded_item is None
                else _sequence_sensitive_positions(decoded_item)
            )
            if _ALL_FOLLOWING_ARGUMENTS in positions:
                sensitive_indices.update(range(index + 1, len(items)))
                continue
            remaining_count = len(items) - index - 1
            if any(position >= remaining_count for position in positions):
                sensitive_indices.update(range(index + 1, len(items)))
                continue
            if positions == {0} and index + 1 < len(items):
                next_text = _sequence_item_text(items[index + 1])
                if next_text is not None:
                    decoded_next = _stable_unquote(next_text)
                    if decoded_next is None or decoded_next.casefold() in {
                        "bearer",
                        "basic",
                        "digest",
                        "token",
                    }:
                        positions = {0, 1}
            sensitive_indices.update(index + 1 + position for position in positions)
        return [
            REDACTED if index in sensitive_indices else self.redact(item)
            for index, item in enumerate(items)
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
            return RedactedDiagnostic(self.text(type(error).__name__), "exception cycle omitted")
        details: list[str] = []
        if isinstance(error, subprocess.CalledProcessError):
            redacted_returncode = self.redact(error.returncode)
            details.append(f"returncode={redacted_returncode!r}")
            details.append(f"command={self.redact(error.cmd)!r}")
            if error.stdout is not None:
                details.append(f"stdout={self.redact(error.stdout)!r}")
            if error.stderr is not None:
                details.append(f"stderr={self.redact(error.stderr)!r}")
        cause = error.__cause__ or error.__context__
        if isinstance(error, subprocess.CalledProcessError):
            message = f"subprocess failed with return code {redacted_returncode!r}"
        else:
            redacted_args = self.redact(error.args)
            assert isinstance(redacted_args, tuple)
            if len(redacted_args) == 1:
                message = str(redacted_args[0])
            else:
                message = repr(redacted_args)
        return RedactedDiagnostic(
            exception_type=self.text(type(error).__name__),
            message=message,
            details=tuple(details),
            cause=(
                self._exception_diagnostic(cause, seen | {id(error)}) if cause is not None else None
            ),
        )
