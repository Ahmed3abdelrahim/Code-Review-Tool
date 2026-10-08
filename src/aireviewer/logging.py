"""Structured JSON logging with secret redaction.

Records from structlog and from stdlib loggers (httpx, uvicorn, ...) go through one
ProcessorFormatter on the root handler. Redaction is the last step before rendering and runs
after exceptions are formatted, so traceback text is redacted too. Tracebacks are plain text
and never include frame locals.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
from collections.abc import Iterable, Mapping
from types import TracebackType
from typing import Any, Final, TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

MASK: Final = "***"
MIN_KNOWN_SECRET_LENGTH: Final = 12  # shorter values (e.g. a dev DB password) are too common
MAX_REPR_CHARS: Final = 10_000
MAX_DEPTH: Final = 10

_SENSITIVE_KEYS: Final = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "x_api_key",
        "private_key",
        "client_secret",
    }
)
_SENSITIVE_SUFFIXES: Final = ("_token", "_secret", "_password", "_api_key", "_private_key")

_SENSITIVE_NAME = r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key)"
_TEXT_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    # PEM blocks: complete, or truncated (BEGIN ... PRIVATE KEY up to the end of the text).
    (re.compile(r"-----BEGIN ([A-Z0-9 ]+)-----.*?-----END \1-----", re.S), MASK),
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*", re.S), MASK),
    # Credentials in URLs: scheme://user:password@host
    (re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^/\s:@]*:)[^/\s@]+@"), rf"\1{MASK}@"),
    # Authorization header values, whatever the scheme.
    (
        re.compile(r"(?i)(\b(?:proxy-)?authorization[\"']?\s*[:=]\s*[\"']?)[^\"'\r\n,;}]+"),
        rf"\1{MASK}",
    ),
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9\-._~+/]+=*"), rf"\1{MASK}"),
    # key=value, key: value, 'key': 'value' for sensitive names (object reprs, DSNs).
    (
        re.compile(
            rf"(?i)((?<![A-Za-z0-9])(?:[a-z0-9]+[_-])*{_SENSITIVE_NAME}[\"']?\s*[:=]\s*[\"']?)"
            r"(?!\*\*\*)[^\s\"',;}&)]+"
        ),
        rf"\1{MASK}",
    ),
    # JWTs (the GitHub App JWT) and GitHub tokens.
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), MASK),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]+|github_pat_\w+)"), MASK),
)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def _capped_repr(value: object) -> str:
    try:
        text = repr(value)
    except Exception:
        return f"<unrepresentable {type(value).__name__}>"
    if len(text) > MAX_REPR_CHARS:
        return text[:MAX_REPR_CHARS] + "...[truncated]"
    return text


class Redactor:
    """structlog processor that masks secrets in every field of an event."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        known = sorted(
            {s for s in secrets if len(s) >= MIN_KNOWN_SECRET_LENGTH}, key=len, reverse=True
        )
        self._known = re.compile("|".join(map(re.escape, known))) if known else None

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        return self._redact_mapping(event_dict, 0)

    def redact_text(self, text: str) -> str:
        if self._known is not None:
            text = self._known.sub(MASK, text)
        for pattern, replacement in _TEXT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def _redact_mapping(self, mapping: Mapping[Any, Any], depth: int) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in mapping.items():
            name = key if isinstance(key, str) else _capped_repr(key)
            if value is not None and _is_sensitive_key(name):
                redacted[self.redact_text(name)] = MASK
            else:
                redacted[self.redact_text(name)] = self._redact_value(value, depth)
        return redacted

    def _redact_value(self, value: object, depth: int) -> object:
        if isinstance(value, str):
            return self.redact_text(value)
        if value is None or isinstance(value, bool | int | float):
            return value
        if depth < MAX_DEPTH:
            if isinstance(value, Mapping):
                return self._redact_mapping(value, depth + 1)
            if isinstance(value, list | tuple | set | frozenset):
                return [self._redact_value(item, depth + 1) for item in value]
        # Anything else would be repr()'d by the renderer after redaction; do it here instead.
        return self.redact_text(_capped_repr(value))


def configure_logging(
    level: str = "INFO", *, secrets: Iterable[str] = (), stream: TextIO | None = None
) -> None:
    """Route structlog and stdlib logging to one redacting JSON handler on the root logger.

    Call at process startup, passing `settings.secret_values()` once settings are loaded.
    """
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,  # plain text, no frame locals
            Redactor(secrets),
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    _install_excepthooks()


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.stdlib.get_logger(name)
    return logger


def _install_excepthooks() -> None:
    """Send uncaught exceptions through the redacting logger instead of raw stderr."""
    log = get_logger("aireviewer.uncaught")

    def excepthook(
        exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("uncaught_exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args: threading.ExceptHookArgs) -> None:
        log.critical(
            "uncaught_thread_exception",
            thread=args.thread.name if args.thread is not None else None,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
