import pandas as pd

from src.transaction_parser import (
    deduplicate_transactions,
    parse_transaction_tables,
    parse_transactions_from_text,
)


def test_deduplicate_transactions():
    df = pd.DataFrame(
        [
            {"data": "2026-01-01", "descricao": "PIX RECEBIDO", "valor": 100.0, "arquivo_origem": "a.pdf"},
            {"data": "2026-01-01", "descricao": "PIX RECEBIDO", "valor": 100.0, "arquivo_origem": "a.pdf"},
        ]
    )
    result = deduplicate_transactions(df)
    assert len(result) == 1


def test_parse_transaction_tables_handles_cd_suffix_in_generic_amount_column():
    df = pd.DataFrame(
        [
            {"Data": "01/01/2026", "Historico": "SALARIO EMPRESA X", "Valor": "1.000,00 C"},
            {"Data": "02/01/2026", "Historico": "COMPRA CARTAO", "Valor": "250,00 D"},
        ]
    )

    result = parse_transaction_tables([df], "extrato.pdf")

    assert result.loc[0, "tipo_inferido"] == "credito"
    assert result.loc[0, "valor"] == 1000.0
    assert result.loc[1, "tipo_inferido"] == "debito"
    assert result.loc[1, "valor"] == -250.0


def test_parse_transactions_from_text_uses_amount_before_balance():
    page_text = (
        "01/01/2026 PIX RECEBIDO DE MARIA 1.000,00 2.000,00\n"
        "02/01/2026 PAGAMENTO BOLETO -500,00 1.500,00"
    )

    result = parse_transactions_from_text([page_text], "extrato.pdf")

    assert result.loc[0, "descricao"] == "PIX RECEBIDO DE MARIA"
    assert result.loc[0, "valor"] == 1000.0
    assert result.loc[1, "descricao"] == "PAGAMENTO BOLETO"
    assert result.loc[1, "valor"] == -500.0


def test_parse_transactions_from_text_merges_multiline_description():
    page_text = (
        "03/01/2026 PIX RECEBIDO DE CLIENTE\n"
        "REFERENTE NF 1234 1.250,00 3.750,00"
    )

    result = parse_transactions_from_text([page_text], "extrato.pdf")

    assert len(result) == 1
    assert result.loc[0, "descricao"] == "PIX RECEBIDO DE CLIENTE REFERENTE NF 1234"
    assert result.loc[0, "valor"] == 1250.0
