"""Backward-compatible facade.

The implementation lives in :mod:`src.parsers`. This module re-exports the
public surface so that existing callers (``analysis_engine``, tests, the
Streamlit app) keep working unchanged.
"""

from __future__ import annotations

import pandas as pd

from .parsers import (
    TRANSACTION_COLUMNS,
    detect_foreign_statement,
    parse_transaction_tables,
    parse_transactions_from_text,
)


def deduplicate_transactions(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    return df.drop_duplicates(
        subset=["data", "descricao", "valor", "arquivo_origem"],
        keep="first",
    ).reset_index(drop=True)


__all__ = [
    "TRANSACTION_COLUMNS",
    "deduplicate_transactions",
    "detect_foreign_statement",
    "parse_transaction_tables",
    "parse_transactions_from_text",
]
