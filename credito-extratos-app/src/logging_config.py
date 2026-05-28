"""Centralized logging configuration.

LGPD rules for this app:
- NEVER log transaction descriptions, amounts, account holder names,
  account numbers, agency numbers or any PII extracted from PDFs.
- File names uploaded by the analyst MAY be logged (the analyst chose
  the name) but consider truncating in shared environments.
- Acceptable to log: parser name, row counts, statuses, error types,
  durations.

Call :func:`configure_logging` once at process startup (in app.py).
"""

from __future__ import annotations

import logging
import os
import sys

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_CONFIGURED = False


def configure_logging(level: str | int | None = None) -> None:
    """Configure the root logger idempotently.

    Reads CREDITO_EXTRATOS_LOG_LEVEL from env if level is not provided.
    Defaults to INFO. Logs go to stderr; rotate via the host (e.g. journald,
    NSSM on Windows) when running as a service.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = level or os.environ.get("CREDITO_EXTRATOS_LOG_LEVEL", "INFO")
    if isinstance(resolved_level, str):
        resolved_level = resolved_level.upper()

    root = logging.getLogger()
    root.setLevel(resolved_level)

    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    # Avoid duplicate handlers when Streamlit re-runs the script
    for existing in list(root.handlers):
        if isinstance(existing, logging.StreamHandler):
            root.removeHandler(existing)
    root.addHandler(handler)

    # pdfplumber/pdfminer are extremely noisy on DEBUG; cap at WARNING.
    for noisy in ("pdfminer", "pdfminer.pdfinterp", "pdfminer.pdfdocument", "pdfplumber"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
