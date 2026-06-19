"""FX/BRL conversion utilities for foreign-currency statements.

Pure-data functions extracted from app.py so the conversion logic is
testable and reusable without Streamlit.
"""

from __future__ import annotations

import logging

import pandas as pd

from .fx_ptax import FxQuote
from .monthly_summary import build_monthly_summary

logger = logging.getLogger(__name__)


def apply_fx_to_transactions(
    transactions_df: pd.DataFrame,
    display_currency: str,
    fx_quote: FxQuote | None,
) -> pd.DataFrame:
    """Add ``moeda_extrato``, ``cotacao_ptax_venda``, ``data_cotacao_ptax``
    and ``valor_brl`` columns to a transactions DataFrame when a quote is
    available. Returns a copy; the input is not mutated.
    """
    if transactions_df.empty:
        return transactions_df.copy()

    df = transactions_df.copy()
    df["moeda_extrato"] = display_currency

    if fx_quote is None:
        return df

    rate = float(fx_quote.rate_brl_per_unit)
    df["cotacao_ptax_venda"] = rate
    df["data_cotacao_ptax"] = fx_quote.requested_date.strftime("%d/%m/%Y")

    valor_numeric = pd.to_numeric(df["valor"], errors="coerce")
    df["valor_brl"] = (valor_numeric * rate).round(2)

    return df


def build_monthly_summary_with_brl(
    transactions_df: pd.DataFrame,
    fx_quote: FxQuote | None,
) -> pd.DataFrame:
    """Build the base monthly summary; when ``valor_brl`` is available,
    merge BRL totals into ``total_considerado_brl`` / ``total_desconsiderado_brl``.
    """
    summary = build_monthly_summary(transactions_df)

    if (
        fx_quote is None
        or transactions_df.empty
        or "valor_brl" not in transactions_df.columns
    ):
        return summary

    brl_base = transactions_df.copy()
    brl_base["valor"] = pd.to_numeric(brl_base["valor_brl"], errors="coerce").fillna(0)
    brl_summary = build_monthly_summary(brl_base)
    brl_summary = brl_summary.rename(
        columns={
            "total_considerado": "total_considerado_brl",
            "total_desconsiderado": "total_desconsiderado_brl",
        }
    )
    brl_summary = brl_summary.drop(
        columns=[c for c in ("qtd_creditos_considerados", "qtd_revisao") if c in brl_summary.columns],
        errors="ignore",
    )
    return summary.merge(brl_summary, on="mes_ref", how="left")


def stamp_fx_on_headers(
    headers_df: pd.DataFrame,
    display_currency: str,
    fx_quote: FxQuote | None,
    selected_currency_label: str | None,
) -> pd.DataFrame:
    """Add FX columns to the headers DataFrame used in the export."""
    df = headers_df.copy()
    df["moeda_selecionada"] = selected_currency_label or display_currency
    if fx_quote is not None:
        df["cotacao_ptax_venda"] = float(fx_quote.rate_brl_per_unit)
        df["data_cotacao_ptax"] = fx_quote.requested_date.strftime("%d/%m/%Y")
    return df
