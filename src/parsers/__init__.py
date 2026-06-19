"""Registry of bank-specific parsers.

Each parser is autocontained (owns its detection + extraction). The registry
is tried in order — the first parser whose ``matches(text_pages)`` returns
True and whose ``parse(...)`` produces a non-empty DataFrame wins.

Order matters: more specific layouts come first, generic fallbacks last.
"""

from __future__ import annotations

import logging

import pandas as pd

from .banco_brasil import BancoBrasilParser
from .bank_of_america import BankOfAmericaParser, looks_like_foreign_deposit
from .base import (
    PT_MONTHS,
    TRANSACTION_COLUMNS,
    BankParser,
    build_record,
    empty_transactions_df,
    finalize_records,
)
from .bradesco import BradescoParser
from .c6 import C6Parser
from .eagle import EagleBrokerParser
from .generic_table import parse_transaction_tables
from .generic_text import parse_generic_text
from .inter import InterParser
from .nubank import NubankParser
from .santander import SantanderParser
from .wise import WiseParser, looks_like_wise

logger = logging.getLogger(__name__)


BANK_PARSERS: tuple[BankParser, ...] = (
    WiseParser(),
    BradescoParser(),
    BancoBrasilParser(),
    EagleBrokerParser(),
    InterParser(),
    NubankParser(),
    C6Parser(),
    BankOfAmericaParser(),
    SantanderParser(),
)


def _detect_matching_parsers(text_pages: list[str]) -> list[str]:
    """Return the names of all bank parsers whose detector matches.

    Used to surface conflicts where a PDF could be interpreted by more than
    one layout (e.g. a combined Bradesco/Nubank statement). Each detector
    runs in its own try/except so a buggy ``matches`` doesn't block others.
    """
    matched: list[str] = []
    for parser in BANK_PARSERS:
        try:
            if parser.matches(text_pages):
                matched.append(parser.name)
        except Exception:
            logger.exception("Falha em matches() do parser %s", parser.name)
    return matched


def parse_transactions_from_text(
    text_pages: list[str],
    source_file: str,
    word_pages: list[list[dict]] | None = None,
) -> pd.DataFrame:
    """Try each bank-specific parser in order; fall back to the generic text parser.

    When more than one parser claims to match the same PDF, a warning is
    logged with the full list of names — the first one in registry order
    still wins. This makes ambiguous layouts visible in the logs without
    silently changing behavior.
    """
    matching_parsers = _detect_matching_parsers(text_pages)
    if len(matching_parsers) > 1:
        logger.warning(
            "PDF %s casou com %d parsers: %s | usando o primeiro: %s",
            source_file,
            len(matching_parsers),
            ", ".join(matching_parsers),
            matching_parsers[0],
        )

    for parser in BANK_PARSERS:
        if parser.name not in matching_parsers:
            continue
        try:
            result = parser.parse(text_pages, source_file, word_pages=word_pages)
        except Exception:
            logger.exception("Parser %s falhou em %s", parser.name, source_file)
            continue

        if not result.empty:
            logger.info(
                "PDF %s extraido pelo parser %s | linhas=%d",
                source_file,
                parser.name,
                len(result),
            )
            return result

    generic = parse_generic_text(text_pages, source_file)
    if not generic.empty:
        logger.info(
            "PDF %s extraido pelo parser generico | linhas=%d", source_file, len(generic)
        )
        return generic

    logger.warning("PDF %s nao casou com nenhum parser conhecido", source_file)
    return empty_transactions_df()


def detect_foreign_statement(text_pages: list[str]) -> bool:
    """Returns True if any *foreign-currency* layout is detected.

    Used by the UI to pre-select the "extrato estrangeiro" toggle.
    """
    return looks_like_foreign_deposit(text_pages) or looks_like_wise(text_pages)


__all__ = [
    "BANK_PARSERS",
    "PT_MONTHS",
    "TRANSACTION_COLUMNS",
    "BankParser",
    "build_record",
    "detect_foreign_statement",
    "empty_transactions_df",
    "finalize_records",
    "parse_generic_text",
    "parse_transaction_tables",
    "parse_transactions_from_text",
]
