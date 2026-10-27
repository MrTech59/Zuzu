"""Structured logging with secret redaction.

A logging.Filter scans formatted records for known secret values and masks them,
so provider keys or tokens never reach console or file logs, even if code
accidentally logs a full request object.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable

# Patterns whose values must be masked whenever they appear in a log line.
_REDACT_PATTERN_KEYS = (
    "api_key",
    "authorization",
    "token",
    "password",
    "secret",
    "credential",
    "session_id",
)

# Header-style occurrences such as "authorization: Bearer xyz" are masked fully.
_HEADER_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|token|password|secret|credential)\b(\s*[:=]\s*)([^\s,;\"']+)"
)
_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[^\s\"',]+")


class SecretRedactingFilter(logging.Filter):
    """Masks secret-like values in log records.

    Set `known_secrets` to concrete secret values (API keys, bearer tokens);
    any occurrence of them is replaced with "***REDACTED***".
    """

    def __init__(self, known_secrets: Iterable[str] | None = None) -> None:
        super().__init__()
        self._literals: list[str] = [s for s in (known_secrets or []) if s]
        self._literals.sort(key=len, reverse=True)  # longest first

    def add_secret(self, value: str) -> None:
        if value and value not in self._literals:
            self._literals.insert(0, value)
            self._literals.sort(key=len, reverse=True)

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - broken record formatting
            return True
        msg = redact_text(msg, self._literals)
        record.msg = msg
        record.args = ()
        return True


def redact_text(text: str, literals: Iterable[str]) -> str:
    out = text
    for lit in literals:
        if lit:
            out = out.replace(lit, "***REDACTED***")
    out = _BEARER_RE.sub(r"\1***REDACTED***", out)
    out = _HEADER_RE.sub(r"\1\2***REDACTED***", out)
    return out


def setup_logging(level: str = "INFO", known_secrets: Iterable[str] | None = None) -> None:
    """Configure root logging with the redacting filter on all handlers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s :: %(message)s"))
    redactor = SecretRedactingFilter(known_secrets)
    handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn loggers also flow through the redacting handler.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # Keep the redactor reachable for runtime secret registration.
    logging.getLogger("zuzu.secrets")._redactor = redactor  # type: ignore[attr-defined]


def register_secret(value: str) -> None:
    """Register a secret value at runtime so it is redacted from all logs."""
    if not value:
        return
    lg = logging.getLogger("zuzu.secrets")
    redactor: SecretRedactingFilter | None = getattr(lg, "_redactor", None)
    if redactor is not None:
        redactor.add_secret(value)
