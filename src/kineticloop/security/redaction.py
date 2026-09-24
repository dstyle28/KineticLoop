"""Recursive, non-mutating redaction for presentation-only diagnostics."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from kineticloop.config.secrets import SecretValue

REDACTED = "[REDACTED]"
_SECRET_MARKER = "__KINETICLOOP_REDACTED_SECRET__"

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
_SENSITIVE_KEY_EXPRESSION = (
    r"access[_-]?token|api[_-]?key|authorization|client[_-]?secret|cookie|credential(?:s)?|"
    r"database[_-]?url|dsn|passwd|password|refresh[_-]?token|secret|token"
)
_ASSIGNMENT = re.compile(
    rf"(?i)(?P<key>[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^,;\r\n]+)"
)
_COMMAND_OPTION = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*=)"
    r"(?P<value>[^,;\r\n]+)"
)
_COMMAND_SEPARATE = re.compile(
    rf"(?i)(?P<prefix>--[a-z0-9_.-]*(?:{_SENSITIVE_KEY_EXPRESSION})[a-z0-9_.-]*\s+)"
    r"(?P<value>\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;\r\n]+)"
)

DiagnosticScalar: TypeAlias = str | bytes | int | float | bool | None


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _is_sensitive_key(value: object) -> bool:
    normalized = _normalized_key(value)
    return any(
        normalized == part or normalized.startswith(f"{part}_") or normalized.endswith(f"_{part}")
        for part in _SENSITIVE_KEY_PARTS
    )


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
            raw = secret.reveal() if isinstance(secret, SecretValue) else secret
            if not isinstance(raw, str):
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
        result = _URL.sub(lambda match: self._url(match.group(0)), result)
        result = result.replace(_SECRET_MARKER, REDACTED)
        result = _COMMAND_OPTION.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        result = _COMMAND_SEPARATE.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
        return _ASSIGNMENT.sub(
            lambda match: f"{match.group('key')}{match.group('separator')}{REDACTED}",
            result,
        )

    def _url(self, matched_url: str) -> str:
        trailing = ""
        while matched_url and matched_url[-1] in ".,;)]":
            trailing = matched_url[-1] + trailing
            matched_url = matched_url[:-1]
        try:
            parsed = urlsplit(matched_url)
            hostname = parsed.hostname
            if not parsed.scheme or hostname is None:
                return matched_url + trailing
            host = f"[{hostname}]" if ":" in hostname else hostname
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
            if parsed.username is not None or parsed.password is not None:
                host = f"{REDACTED}@{host}"
            query = [
                (
                    key,
                    REDACTED if _is_sensitive_key(key) else value,
                )
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
            sanitized = urlunsplit(
                (parsed.scheme, host, parsed.path, urlencode(query, doseq=True), parsed.fragment)
            )
        except (TypeError, ValueError):
            sanitized = matched_url
        return sanitized + trailing

    def redact(self, value: object) -> object:
        """Return a recursively redacted diagnostic copy of a supported value."""

        if isinstance(value, SecretValue):
            return REDACTED
        if isinstance(value, BaseException):
            return self.exception_diagnostic(value)
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, bytes):
            return self.text(value.decode("utf-8", errors="replace")).encode("utf-8")
        if isinstance(value, Mapping):
            return {
                (self.text(key) if isinstance(key, str) else key): (
                    REDACTED if _is_sensitive_key(key) else self.redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, tuple):
            return tuple(self._redact_sequence(value))
        if isinstance(value, list):
            return self._redact_sequence(value)
        if isinstance(value, set):
            return {self.redact(item) for item in value}
        if isinstance(value, frozenset):
            return frozenset(self.redact(item) for item in value)
        return value

    def _redact_sequence(self, value: Sequence[object]) -> list[object]:
        result: list[object] = []
        redact_next = False
        for item in value:
            if redact_next:
                result.append(REDACTED)
                redact_next = False
                continue
            result.append(self.redact(item))
            if isinstance(item, str):
                option = item.lstrip("-")
                redact_next = "=" not in option and _is_sensitive_key(option)
        return result

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
        return RedactedDiagnostic(
            exception_type=type(error).__name__,
            message=self.text(str(error)),
            details=tuple(details),
            cause=(
                self._exception_diagnostic(cause, seen | {id(error)}) if cause is not None else None
            ),
        )
