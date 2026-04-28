import pandas as pd

from src.manual_overrides import (
    apply_manual_overrides,
    build_transaction_key,
    ensure_transaction_keys,
    keep_matching_overrides,
    reconcile_manual_overrides,
)


def test_build_transaction_key_is_stable_for_same_transaction():
    row = {
        "data": pd.Timestamp("2026-04-20"),
        "descricao": "TED RECEBIDA",
        "valor": 100000.0,
        "arquivo_origem": "extrato.pdf",
    }

    assert build_transaction_key(row) == build_transaction_key(pd.Series(row))


def test_manual_disregard_is_preserved_after_reprocessing():
    df = pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-04-20"),
                "descricao": "TED RECEBIDA",
                "valor": 100000.0,
                "arquivo_origem": "extrato.pdf",
                "status_final": "considerado",
                "motivo_final": "Credito aceito pela regra inicial.",
            }
        ]
    )

    keyed_df = ensure_transaction_keys(df)
    transaction_key = keyed_df.loc[0, "transaction_key"]
    overrides = {
        transaction_key: {
            "status_final": "desconsiderado",
            "motivo_final": "Ajuste manual do analista na interface.",
        }
    }

    result = apply_manual_overrides(df, overrides)

    assert result.loc[0, "status_final"] == "desconsiderado"


def test_manual_consideration_is_applied_in_current_session():
    df = pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-04-20"),
                "descricao": "RECEBIMENTO BOLETO",
                "valor": 3500.0,
                "arquivo_origem": "extrato.pdf",
                "status_final": "desconsiderado",
                "motivo_final": "Regra de exclusao acionada por termo: boleto.",
            }
        ]
    )

    keyed_df = ensure_transaction_keys(df)
    transaction_key = keyed_df.loc[0, "transaction_key"]
    overrides = {
        transaction_key: {
            "status_final": "considerado",
            "motivo_final": "Ajuste manual do analista na interface.",
        }
    }

    result = apply_manual_overrides(df, overrides)

    assert result.loc[0, "status_final"] == "considerado"


def test_new_automatic_exclusion_wins_over_old_manual_consideration():
    df = pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-04-20"),
                "descricao": "RECEBIMENTO BOLETO",
                "valor": 3500.0,
                "arquivo_origem": "extrato.pdf",
                "status_final": "desconsiderado",
                "motivo_final": "Regra de exclusao acionada por termo: boleto.",
            }
        ]
    )

    keyed_df = ensure_transaction_keys(df)
    transaction_key = keyed_df.loc[0, "transaction_key"]
    overrides = {
        transaction_key: {
            "status_final": "considerado",
            "motivo_final": "Ajuste manual do analista na interface.",
        }
    }

    result = reconcile_manual_overrides(overrides, df)

    assert result == {}


def test_keep_matching_overrides_discards_missing_transactions():
    old_df = pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-04-20"),
                "descricao": "TED RECEBIDA",
                "valor": 100000.0,
                "arquivo_origem": "extrato.pdf",
            }
        ]
    )
    new_df = pd.DataFrame(
        [
            {
                "data": pd.Timestamp("2026-04-21"),
                "descricao": "PIX RECEBIDO",
                "valor": 1200.0,
                "arquivo_origem": "extrato.pdf",
            }
        ]
    )

    old_key = ensure_transaction_keys(old_df).loc[0, "transaction_key"]
    overrides = {old_key: {"status_final": "desconsiderado"}}

    assert keep_matching_overrides(overrides, new_df) == {}
