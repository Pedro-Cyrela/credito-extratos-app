import pandas as pd

from src.table_extractor import tables_to_dataframes
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


def test_tables_to_dataframes_makes_duplicate_headers_unique():
    raw_tables = [
        [
            ["02/01", "02/01", "", "", "R$ 721,48"],
            ["", "02/01", "Entrada PIX", "Pix recebido de FULANO", ""],
            ["02/01", "02/01", "Pagamento", "PGTO FAT CARTAO C6", "-R$ 3.621,17"],
        ]
    ]

    [df] = tables_to_dataframes(raw_tables)

    assert list(df.columns) == ["02/01", "02/01_1", "col_2", "col_3", "R$ 721,48"]


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


def test_parse_transactions_from_nubank_handles_split_day_header_across_pages():
    text_pages = [
        (
            "Lucas Faria Malvao\n"
            "MovimentaÃ§Ãµes\n"
            "03 OUT 2025 Total de entradas + 10,00\n"
            "TransferÃªncia recebida pelo Pix FULANO - 10,00\n"
            "Total de saÃ­das - 1,00\n"
            "Compra no dÃ©bito PADARIA 1,00\n"
            "04 OUT 2025\n"
        ),
        (
            "Total de entradas + 1.128,30\n"
            "TransferÃªncia Recebida Ricardo Luiz GonÃ§alves de Albuquerque - â€¢â€¢â€¢. 800,00\n"
            "Total de saÃ­das - 500,00\n"
            "Pagamento de fatura 500,00\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "nubank.pdf")

    match = result[result["descricao"].str.contains("Ricardo", regex=False)]
    assert len(match) == 1
    assert match.iloc[0]["data"].strftime("%Y-%m-%d") == "2025-10-04"
    assert match.iloc[0]["valor"] == 800.0


def test_parse_transactions_from_nubank_normalizes_pix_no_credit_variants():
    text_pages = [
        (
            "Joao Pedro de Sousa Soares Leitao\n"
            "Movimentações\n"
            "26 JAN 2026 Total de entradas + 1.207,31\n"
            "Valor adicionado na conta por Valor adicionado para Pix no Crédito 4,31\n"
            "cartão de crédito\n"
            "Transferência recebida pelo Pix FULANO - 1.203,00\n"
            "Total de saídas - 4,31\n"
        ),
        (
            "08 MAR 2026 Total de entradas + 607,00\n"
            "Valor adicionado na conta por cartão Valor adicionado para Pix no Crédito 7,00\n"
            "de crédito\n"
            "Total de saídas - 7,00\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "nubank.pdf")

    matched = result[result["descricao"] == "Valor adicionado na conta por cartão Valor adicionado para Pix no Crédito"]
    assert len(matched) == 2
    assert sorted(matched["valor"].tolist()) == [4.31, 7.0]


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


def test_parse_transactions_from_wise_usd_statement_layout():
    text_pages = [
        (
            "Wise Payments Ltd.\n"
            "Extrato em USD\n"
            "DescriÃ§Ã£o Entrada SaÃ­da Valor\n"
            "Recebeu dinheiro de KNWN LOCAL LLC com a referÃªncia 1.100,00 1.100,00\n"
            "\"091311220026380\"\n"
            "6 de abril de 2026 TransaÃ§Ã£o: TRANSFER-2062411891 ReferÃªncia: 091311220026380\n"
            "20,00 USD movimentados para Visto USA -20,00 1.080,00\n"
            "6 de abril de 2026 TransaÃ§Ã£o: BALANCE-5073804866\n"
            "TransaÃ§Ã£o por cartÃ£o de 5,00 USD emitida por Anthropic ANTHROPIC.COM -5,00 169,32\n"
            "13 de maio de 2026 CartÃ£o terminado em 2307 Pedro Lucas da Silva Leite TransaÃ§Ã£o: CARD-3787345278\n"
        )
    ]

    result = parse_transactions_from_text(text_pages, "wise.pdf")

    assert len(result) == 3
    assert detect_foreign_statement(text_pages) is True

    deposit = result[result["descricao"].str.contains("KNWN LOCAL LLC", regex=False)].iloc[0]
    assert deposit["data"].strftime("%Y-%m-%d") == "2026-04-06"
    assert deposit["valor"] == 1100.0
    assert deposit["tipo_inferido"] == "credito"
    assert "091311220026380" in deposit["descricao"]

    transfer = result[result["descricao"].str.contains("Visto USA", regex=False)].iloc[0]
    assert transfer["valor"] == -20.0
    assert transfer["tipo_inferido"] == "debito"

    card = result[result["descricao"].str.contains("Anthropic", regex=False)].iloc[0]
    assert card["valor"] == -5.0


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


def test_parse_transactions_from_c6_monthly_statement():
    text_pages = [
        (
            "Extrato exportado no dia 2 de maio de 2026 às 15:27\n"
            "RAPHAELA GOMES DE CARVALHO BENTO • 203.723.007-90\n"
            "Agência: 1 • Conta: 167306170\n"
            "Extrato Período • 3 de novembro de 2025 até 2 de maio de 2026\n"
            "Novembro 2025 ( 03/11/2025 - 30/11/2025 ) Entradas: R$ 0,00 • Saídas: R$ 354,00\n"
            "Data Data\n"
            "Tipo Descrição Valor\n"
            "lançamento contábil\n"
            "06/11 05/11 Saída PIX Pix enviado para GOOGLE BRASIL INTERNET LTDA. -R$ 100,00\n"
            "08/11 10/11 Pagamento CLUBE DE PERMUTA -R$ 39,00\n"
            "Saldo do dia 12/11/25 R$ 398,87\n"
            "30/11 01/12 Saída PIX Pix enviado para GOOGLE BRASIL INTERNET LTDA. -R$ 100,00\n"
            "Janeiro 2026 ( 01/01/2026 - 31/01/2026 ) Entradas: R$ 3.620,96 • Saídas: R$ 3.736,17\n"
            "Data Data\n"
            "Tipo Descrição Valor\n"
            "lançamento contábil\n"
            "02/01 02/01 Entrada PIX Pix recebido de PRJ CONSULTORIA E MARKETING LTDA R$ 721,48\n"
            "02/01 02/01 Pagamento PGTO FAT CARTAO C6 -R$ 3.621,17\n"
        ),
        (
            "Data Data\n"
            "Tipo Descrição Valor\n"
            "lançamento contábil\n"
            "22/01 22/01 Entradas CASHBACK ATOMOS R$ 152,48\n"
            "Saldo do dia 22/01/26 R$ 60,76\n"
            "Abril 2026 ( 01/04/2026 - 30/04/2026 ) Entradas: R$ 0,00 • Saídas: R$ 0,00\n"
            "Sem lançamentos no mês\n"
            "No app do C6 Bank\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "c6.pdf")

    assert len(result) == 6
    assert result.iloc[0]["data"].strftime("%Y-%m-%d") == "2025-11-06"
    assert result.iloc[0]["descricao"] == "Saída PIX Pix enviado para GOOGLE BRASIL INTERNET LTDA."
    assert result.iloc[0]["valor"] == -100.0

    pix_credit = result[result["descricao"].str.contains("PRJ CONSULTORIA", regex=False)].iloc[0]
    assert pix_credit["data"].strftime("%Y-%m-%d") == "2026-01-02"
    assert pix_credit["valor"] == 721.48
    assert pix_credit["tipo_inferido"] == "credito"

    cashback = result[result["descricao"] == "Entradas CASHBACK ATOMOS"].iloc[0]
    assert cashback["valor"] == 152.48


def _word_rows(rows):
    words = []
    for row_index, row in enumerate(rows):
        top = 100 + (row_index * 12)
        for text, x0 in row:
            words.append({"text": text, "x0": x0, "x1": x0 + max(len(text) * 4, 4), "top": top})
    return words


def test_parse_transactions_from_nubank_skips_total_out_headers_and_daily_balances():
    text_pages = [
        (
            "THAINA SILVA ALVES DA COSTA\n"
            "MovimentaÃ§Ãµes\n"
            "21 DEZ 2025 Total de entradas + 300,00\n"
            "TransferÃªncia recebida pelo Pix CLIENTE EXEMPLO 300,00\n"
            "Saldo do dia 324,27\n"
            "22 DEZ 2025 Total de saÃ­das - 81,90\n"
            "Pagamento de boleto efetuado DAS-SIMPLES NACIONAL 81,90\n"
            "Saldo do dia 242,37\n"
        )
    ]

    result = parse_transactions_from_text(text_pages, "nubank.pdf")

    assert not result["descricao"].str.contains("Total de sa", case=False, regex=False).any()
    assert not result["descricao"].str.contains("Saldo do dia", case=False, regex=False).any()

    boleto = result[result["descricao"].str.contains("DAS-SIMPLES", regex=False)].iloc[0]
    assert boleto["data"].strftime("%Y-%m-%d") == "2025-12-22"
    assert boleto["valor"] == -81.9
    assert boleto["tipo_inferido"] == "debito"


def test_parse_transactions_from_inter_daily_statement():
    text_pages = [
        (
            "Solicitado em: 02/05/2026 - 15h01\n"
            "LETICIA JOANNI MATTEDI 14553370727\n"
            "CPF/CNPJ: 36.573.294/0001-98, Instituição: Banco Inter, Agência: 0001-9, Conta: 18866265-0\n"
            "Período: 02/05/2025 a 02/05/2026\n"
            "Saldo total Saldo disponível: Saldo bloqueado:\n"
            "R$ 0,00 R$ 0,00 R$ 0,00\n"
            "2 de Maio de 2025 Saldo do dia: R$ 0,06 Valor Saldo por transação\n"
            "Pix enviado: \"Cp :16501555-RMS BAR E RESTAURANTE LTDA\" -R$ 15,00 -R$ 1,94\n"
            "Pix recebido: \"Cp :18236120-Gabriel Pacheco de Almeida Santos\" R$ 2,00 R$ 0,06\n"
            "Fale com a gente\n"
            "SAC: 0800 940 9999\n"
        ),
        (
            "Pix enviado: \"Cp :90400888-William Rafael Monteiro da Costa\" -R$ 60,85 -R$ 49,05\n"
            "Resgate: \"CDB DI LIQ BANCO INTER SA\" R$ 60,00 R$ 10,95\n"
            "10 de Maio de 2025 Saldo do dia: R$ 2,70\n"
            "Pix enviado: \"Cp :18236120-Nelio Xavier Pinheiro Junior\" -R$ 958,00 -R$ 955,30\n"
            "Resgate: \"CDB DI LIQ BANCO INTER SA\" R$ 958,00 R$ 2,70\n"
        ),
    ]

    result = parse_transactions_from_text(text_pages, "inter.pdf")

    assert len(result) == 6
    received = result[result["descricao"].str.startswith('Pix recebido:')].iloc[0]
    assert received["data"].strftime("%Y-%m-%d") == "2025-05-02"
    assert received["valor"] == 2.0

    debit = result[result["descricao"].str.contains("RMS BAR", regex=False)].iloc[0]
    assert debit["valor"] == -15.0
    assert debit["tipo_inferido"] == "debito"

    continued = result[result["descricao"].str.contains("William Rafael", regex=False)].iloc[0]
    assert continued["data"].strftime("%Y-%m-%d") == "2025-05-02"

    resgate = result[result["descricao"].str.contains('Resgate:', regex=False)].iloc[0]
    assert resgate["valor"] > 0
