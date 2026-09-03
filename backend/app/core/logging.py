"""Structured JSON logging with request correlation IDs and secret sanitization.

Usage::

    from app.core.logging import get_logger, set_request_id

    logger = get_logger(__name__)
    set_request_id("req-123")        # once per request / celery task
    logger.info("job fetched", extra={
        "source": "hh_kz",
        "operation": "fetch_jobs",
        "jobs_received": 42,
    })
"""

import contextvars
import json
import logging
import re
import sys

from app.core.config import settings

# Correlation / request id shared across the current execution context.
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def set_request_id(request_id: str | None) -> None:
    """Set the request id for the current request/task context."""
    request_id_var.set(request_id)


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "password",
    "secret",
    "authorization",
    "api-key",
    "x-api-key",
    "x-api-app-id",
    "bearer",
}

# Attributes logging attaches to every record; any other attribute is treated
# as structured extra data and must be sanitized.
_STD_RECORD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime", "correlation_id",
})

# Well-known secret token shapes: OpenAI sk-..., GitHub ghp_.../github_pat_...,
# Telegram bot tokens (123456789:AAAA...).
_TOKEN_PATTERNS = (
    re.compile(r"\b[a-z_-]*(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"),
)


def _mask_secrets(value: str) -> str:
    """Mask well-known secret token shapes inside a string."""
    for pattern in _TOKEN_PATTERNS:
        value = pattern.sub("***", value)
    return value


def _sanitize_value(value: object) -> object:
    """Recursively mask values stored under sensitive keys."""
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            str_key = str(key)
            if str_key.lower().replace(" ", "-") in SENSITIVE_KEYS:
                sanitized[str_key] = "***"
            else:
                sanitized[str_key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _mask_secrets(value)
    return value


class SanitizingFormatter(logging.Formatter):
    """JSON formatter that masks secrets and adds the correlation id."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _mask_secrets(record.getMessage()),
        }

        request_id = request_id_var.get()
        if request_id:
            entry["correlation_id"] = request_id

        extras = {
            key: value
            for key, value in getattr(record, "__dict__", {}).items()
            if key not in _STD_RECORD_ATTRS and not key.startswith("_")
        }
        if extras:
            entry.update(_sanitize_value(extras))  # type: ignore[arg-type]

        if record.exc_info:
            entry["exc_info"] = _mask_secrets(self.formatException(record.exc_info))

        return json.dumps(entry, ensure_ascii=False, default=str, sort_keys=True)


def setup_logging() -> None:
    """Configure the root logger with the JSON structured formatter."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Reuse an existing stdout handler (e.g. installed by uvicorn) or add one.
    handler = next(
        (h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        root_logger.addHandler(handler)
    else:
        handler.setLevel(log_level)

    handler.setFormatter(
        SanitizingFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
    )

    # Silence noisy HTTP client loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for structured output."""
    return logging.getLogger(name)
