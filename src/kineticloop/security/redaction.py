"""Recursive, non-mutating redaction for presentation-only diagnostics."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypeAlias
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

from kineticloop.config.secrets import SecretValue

REDACTED = "[REDACTED]"
_SECRET_MARKER = "__KINETICLOOP_REDACTED_SECRET__"

_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "database_url",
        "password",
        "refresh_token",
        "secret",
        "token",
    }
)
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"'{}\[\]]+")
_ASSIGNMENT = re.compile(
    r"(?i)(?P<key>access[_-]?token|api[_-]?key|authorization|client[_-]?secret|"
    r"credential|database[_-]?url|password|refresh[_-]?token|secret|token)"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\s,;]+)"
)
_COMMAND_OPTION = re.compile(
    r"(?i)(?P<prefix>--(?:access[_-]?token|api[_-]?key|client[_-]?secret|"
    r"password|refresh[_-]?token|secret|token)=)(?P<value>[^\s,;]+)"
)

DiagnosticScalar: TypeAlias = str | bytes | int | float | bool | None


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


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

    __slots__ = ("__variants",)

    def __init__(self, secrets: Sequence[str | SecretValue] = ()) -> None:
        variants: set[str] = set()
        for secret in secrets:
            raw = secret.reveal() if isinstance(secret, SecretValue) else secret
            if not isinstance(raw, str):
                raise TypeError("redaction secrets must be strings or SecretValue instances")
            if raw:
                variants.update({raw, quote(raw, safe=""), quote_plus(raw, safe="")})
        self.__variants = tuple(sorted(variants, key=lambda item: (-len(item), item)))

    def text(self, value: str) -> str:
        """Redact one diagnostic string without changing the source value."""

        result = value
        for variant in self.__variants:
            result = result.replace(variant, _SECRET_MARKER)
        result = _URL.sub(lambda match: self._url(match.group(0)), result)
        result = result.replace(_SECRET_MARKER, REDACTED)
        result = _COMMAND_OPTION.sub(lambda match: f"{match.group('prefix')}{REDACTED}", result)
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
                    REDACTED if _normalized_key(key) in _SENSITIVE_KEYS else value,
                )
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
            sanitized = urlunsplit(
                (parsed.scheme, host, parsed.path, urlencode(query, doseq=True), parsed.fragment)
            )
        except (TypeError, ValueError):
            sanitized = matched_url
        for variant in self.__variants:
            sanitized = sanitized.replace(variant, REDACTED)
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
                    REDACTED if _normalized_key(key) in _SENSITIVE_KEYS else self.redact(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, tuple):
            return tuple(self.redact(item) for item in value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, set):
            return {self.redact(item) for item in value}
        if isinstance(value, frozenset):
            return frozenset(self.redact(item) for item in value)
        return value

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
