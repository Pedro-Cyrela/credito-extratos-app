import pandas as pd

from src import analysis_engine
from src.analysis_engine import (
    _build_holder_first_name_rules,
    _ensure_transaction_schema,
    analyze_uploaded_files,
)
from src.parsers.base import build_record


def test_ensure_transaction_schema_preserves_extra_columns_on_empty_dataframe():
    df = pd.DataFrame(columns=["status_final", "motivo_final", "termo_regra"])

    result = _ensure_transaction_schema(df)

    assert "status_final" in result.columns
    assert "motivo_final" in result.columns
    assert "termo_regra" in result.columns


def test_build_holder_first_name_rules_uses_text_before_first_space():
    result = _build_holder_first_name_rules(
        ["Maria Clara de Souza", "  João Pedro Silva  ", "MARIA Oliveira", ""]
    )

    assert result == ["word:Maria", "word:João"]


def test_analyze_uploaded_files_applies_holder_first_name_only_when_enabled(monkeypatch):
    transaction = build_record(
        dt=pd.Timestamp("2026-06-18"),
        desc="PIX RECEBIDO DE MARIA CLIENTE",
        amount=1000.0,
        raw_amount_text="+ 1.000,00",
        detected_as_credit=True,
        detected_as_debit=False,
        source_file="extrato.pdf",
    )

    def fake_process_single_file(file, errors, status_callback=None):
        return {"arquivo": "extrato.pdf", "banco": "Nubank"}, pd.DataFrame([transaction]), "Maria Souza"

    monkeypatch.setattr(analysis_engine, "_process_single_file", fake_process_single_file)

    disabled = analyze_uploaded_files(
        uploaded_files=[object()],
        custom_terms_raw="",
        custom_names_raw="",
        include_holder_first_name=False,
    )
    enabled = analyze_uploaded_files(
        uploaded_files=[object()],
        custom_terms_raw="",
        custom_names_raw="",
        include_holder_first_name=True,
    )

    assert disabled["transactions"].loc[0, "status_final"] == "considerado"
    assert enabled["transactions"].loc[0, "status_final"] == "desconsiderado"
    assert enabled["transactions"].loc[0, "termo_regra"] == "maria"
