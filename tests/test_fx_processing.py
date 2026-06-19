from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from src.fx_processing import (
    apply_fx_to_transactions,
    build_monthly_summary_with_brl,
    stamp_fx_on_headers,
)
from src.fx_ptax import FxQuote


def _make_quote(rate: float = 5.0) -> FxQuote:
    return FxQuote(
        currency="USD",
        rate_brl_per_unit=Decimal(str(rate)),
        quote_datetime=datetime(2026, 1, 15, 13, 0),
        requested_date=date(2026, 1, 15),
    )


def _make_transactions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-01-10"),
                "mes_ref": "01/2026",
                "descricao": "DEPOSIT FROM CLIENT A",
                "valor": 100.0,
                "status_final": "considerado",
                "arquivo_origem": "boa.pdf",
            },
            {
                "data": pd.Timestamp("2026-01-20"),
                "mes_ref": "01/2026",
                "descricao": "WIRE TRANSFER B",
                "valor": 200.0,
                "status_final": "considerado",
                "arquivo_origem": "boa.pdf",
            },
        ]
    )


def test_apply_fx_to_transactions_adds_brl_columns_when_quote_present():
    df = _make_transactions()
    result = apply_fx_to_transactions(df, "USD", _make_quote(rate=5.0))

    assert "moeda_extrato" in result.columns and (result["moeda_extrato"] == "USD").all()
    assert "valor_brl" in result.columns
    assert result.loc[0, "valor_brl"] == 500.0
    assert result.loc[1, "valor_brl"] == 1000.0
    assert result.loc[0, "cotacao_ptax_venda"] == 5.0
    assert result.loc[0, "data_cotacao_ptax"] == "15/01/2026"


def test_apply_fx_to_transactions_without_quote_keeps_only_currency():
    df = _make_transactions()
    result = apply_fx_to_transactions(df, "USD", None)

    assert (result["moeda_extrato"] == "USD").all()
    assert "valor_brl" not in result.columns
    assert "cotacao_ptax_venda" not in result.columns


def test_apply_fx_does_not_mutate_input():
    df = _make_transactions()
    before_cols = list(df.columns)
    apply_fx_to_transactions(df, "USD", _make_quote())
    assert list(df.columns) == before_cols


def test_build_monthly_summary_with_brl_merges_totals():
    df = _make_transactions()
    with_fx = apply_fx_to_transactions(df, "USD", _make_quote(rate=5.0))

    summary = build_monthly_summary_with_brl(with_fx, _make_quote(rate=5.0))

    assert "total_considerado" in summary.columns
    assert "total_considerado_brl" in summary.columns
    row = summary.iloc[0]
    assert row["total_considerado"] == 300.0
    assert row["total_considerado_brl"] == 1500.0


def test_build_monthly_summary_without_quote_skips_brl_merge():
    df = _make_transactions()
    summary = build_monthly_summary_with_brl(df, None)

    assert "total_considerado" in summary.columns
    assert "total_considerado_brl" not in summary.columns


def test_stamp_fx_on_headers_adds_quote_columns():
    headers = pd.DataFrame([{"arquivo": "boa.pdf", "banco": "Bank of America"}])
    result = stamp_fx_on_headers(headers, "USD", _make_quote(rate=4.95), "USD - Dolar americano")

    assert result.loc[0, "moeda_selecionada"] == "USD - Dolar americano"
    assert result.loc[0, "cotacao_ptax_venda"] == 4.95
    assert result.loc[0, "data_cotacao_ptax"] == "15/01/2026"


def test_stamp_fx_on_headers_without_quote_only_records_currency_label():
    headers = pd.DataFrame([{"arquivo": "boa.pdf"}])
    result = stamp_fx_on_headers(headers, "USD", None, "USD")
    assert result.loc[0, "moeda_selecionada"] == "USD"
    assert "cotacao_ptax_venda" not in result.columns
