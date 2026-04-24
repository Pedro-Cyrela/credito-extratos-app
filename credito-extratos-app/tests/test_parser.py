import pandas as pd

from src.transaction_parser import (
    deduplicate_transactions,
    detect_foreign_statement,
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


def test_parse_transactions_from_nubank_text_blocks_and_page_continuation():
    text_pages = [
        (
            "Lucas Faria Malvao\n"
            "Movimentações\n"
            "01 DEZ 2025 Total de entradas + 2.602,33\n"
            "Resgate RDB 222,33\n"
            "Transferência recebida pelo Pix LUCAS FARIA MALVAO - •••.605.277-•• - 1.400,00\n"
            "CLOUDWALK IP LTDA (0542) Agência: 1 Conta:\n"
            "4074234-1\n"
            "Total de saídas - 3.302,33\n"
            "Compra no débito MARINA PORTO REAL 700,00\n"
            "Transferência enviada pelo Pix RODRIGO CUNHA DA SILVA - •••.065.387-•• - 80,00\n"
        ),
        (
            "Aplicação RDB 800,00\n"
            "Aplicação RDB 100,00\n"
            "02 DEZ 2025 Total de entradas + 95,00\n"
            "Resgate RDB 30,00\n"
            "Transferência recebida pelo Pix JAQUELYNE NUNES LIMOEIRO - •••.287.967-•• - 50,00\n"
            "Total de saídas - 95,00\n"
            "Compra no débito PIZZARIA E PASTELARIA 45,00\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "nubank.pdf")

    assert len(result) == 9
    marina = result[result["descricao"] == "Compra no débito MARINA PORTO REAL"]
    assert marina.iloc[0]["data"].strftime("%Y-%m-%d") == "2025-12-01"
    assert marina.iloc[0]["valor"] == -700.0
    assert (result["descricao"] == "Aplicação RDB").sum() == 2
    assert result[result["descricao"] == "Aplicação RDB"]["valor"].tolist() == [-800.0, -100.0]
    assert result[result["descricao"].str.contains("JAQUELYNE", regex=False)].iloc[0]["valor"] == 50.0


def test_parse_foreign_deposits_and_continued_sections():
    text_pages = [
        (
            "Bank of America\n"
            "Deposits and other additions\n"
            "Date Description Amount\n"
            "01/30/26 THEALCOVER709177 DES:PAYROLL ID:2451415 INDN:MARIA POSADA CO 553.63\n"
            "ID:1179097700 PPD\n"
            "02/02/26 PURCHASE REFUND AMAZON MKTPLACE 19.66\n"
            "continued on the next page\n"
            "Marketing line that must not become a transaction detail\n"
        ),
        (
            "Deposits and other additions - continued\n"
            "Date Description Amount\n"
            "02/06/26 THEALCOVER709177 DES:PAYROLL ID:2451415 INDN:MARIA POSADA CO 411.78\n"
            "Total deposits and other additions $985.07\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "foreign.pdf")

    assert len(result) == 3
    assert round(result["valor"].sum(), 2) == 985.07
    assert result.iloc[0]["data"].strftime("%Y-%m-%d") == "2026-01-30"
    assert "ID:1179097700 PPD" in result.iloc[0]["descricao"]
    assert not result["descricao"].str.contains("Marketing line", regex=False).any()


def test_detect_foreign_statement_does_not_identify_currency():
    text_pages = [
        (
            "Bank of America\n"
            "Deposits and other additions\n"
            "Date Description Amount\n"
            "01/30/26 PAYROLL 553.63\n"
        )
    ]

    assert detect_foreign_statement(text_pages) is True


def test_parse_bradesco_word_layout_uses_physical_credit_debit_columns():
    text_pages = [
        (
            "Bradesco Celular\n"
            "Data Historico Docto. Credito (R$) Debito (R$) Saldo (R$)\n"
            "TRANSFERENCIA PIX\n"
            "03/12/2025 1346403 300,00 164,57\n"
            "DES: Renata Cristina Fagun 03/12\n"
            "04/12/2025 INSS 0043204 5.031,99 4.732,23\n"
        )
    ]
    word_pages = [
        _word_rows(
            [
                [("Data", 45), ("Historico", 110), ("Docto.", 304), ("Credito", 385), ("Debito", 452), ("Saldo", 520)],
                [("TRANSFERENCIA", 110), ("PIX", 176)],
                [("03/12/2025", 45), ("1346403", 303), ("300,00", 462), ("164,57", 532)],
                [("DES:", 110), ("Renata", 130), ("Cristina", 160), ("Fagun", 195), ("03/12", 225)],
                [("04/12/2025", 45), ("INSS", 110), ("0043204", 303), ("5.031,99", 398), ("4.732,23", 522)],
            ]
        )
    ]

    result = parse_transactions_from_text(text_pages, "bradesco.pdf", word_pages)

    pix = result[result["descricao"].str.contains("Renata", regex=False)].iloc[0]
    inss = result[result["descricao"] == "INSS"].iloc[0]
    assert pix["valor"] == -300.0
    assert pix["tipo_inferido"] == "debito"
    assert inss["valor"] == 5031.99
    assert inss["tipo_inferido"] == "credito"


def _word_rows(rows):
    words = []
    for row_index, row in enumerate(rows):
        top = 100 + (row_index * 12)
        for text, x0 in row:
            words.append({"text": text, "x0": x0, "x1": x0 + max(len(text) * 4, 4), "top": top})
    return words
