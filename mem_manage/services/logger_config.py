"""Central logging configuration for mem_manage.

Trimmed from the RAG-work sibling project's version: this keeps only
request-id-tagged console + debug-file logging. Dropped entirely: the
LangSmith/Phoenix span-mirroring handler, the Langfuse handler, the
timing_tracker cross-import, and the chunk-run markdown writer - all
RAG-ingestion-pipeline observability with no equivalent here.
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from ..config import DEFAULT_LOG_DIR

_CONFIGURED_ATTR = "_mem_manage_logging_configured"

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        return True


class _DynamicStdoutHandler(logging.StreamHandler):
    """Follow sys.stdout so batch-run tee streams still capture console logs."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def setup_logging(
    log_dir: str | Path = DEFAULT_LOG_DIR,
    app_name: str | None = None,
    console_level: int = logging.INFO,
) -> None:
    """Configure application logging once for the current process."""
    root_logger = logging.getLogger()
    if getattr(root_logger, _CONFIGURED_ATTR, False):
        return

    resolved_log_dir = Path(log_dir)
    resolved_log_dir.mkdir(parents=True, exist_ok=True)
    resolved_app_name = app_name or Path(sys.argv[0]).stem or "mem_manage"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    request_id_filter = _RequestIdFilter()

    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | [%(request_id)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = _DynamicStdoutHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(request_id_filter)

    debug_file = resolved_log_dir / f"{resolved_app_name}_{timestamp}.debug.log"
    debug_handler = logging.FileHandler(debug_file, encoding="utf-8")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(file_formatter)
    debug_handler.addFilter(request_id_filter)

    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(debug_handler)

    setattr(root_logger, _CONFIGURED_ATTR, True)
