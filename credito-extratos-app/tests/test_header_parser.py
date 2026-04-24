from src.header_parser import parse_header


def test_parse_header_detects_nubank_before_counterparty_banks():
    text_pages = [
        (
            "Lucas Faria Malvao\n"
            "CPF •••.605.277-•• Agência 0001 Conta\n"
            "33163745-6\n"
            "01 DE DEZEMBRO DE 2025 a 31 DE DEZEMBRO DE 2025 VALORES EM R$\n"
            "Movimentações\n"
        ),
        (
            "Transferência recebida pelo Pix JAQUELYNE NUNES LIMOEIRO - •••.287.967-•• - 50,00\n"
            "ITAÚ UNIBANCO S.A. (0341) Agência: 7032 Conta:\n"
            "2992-3\n"
            "disponíveis em nubank.com.br/contatos#ouvidoria\n"
        ),
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Nubank"
    assert header.account_holder == "Lucas Faria Malvao"
    assert header.agency == "0001"
    assert header.account_number == "33163745-6"


def test_parse_header_handles_bradesco_celular_metadata():
    text_pages = [
        (
            "Bradesco Celular\n"
            "Data: 06/03/2026 - 13h30\n"
            "Nome: WILLIAM VARGAS\n"
            "Extrato de: Agencia: 3204 | Conta: 130776-2 | Movimentacao entre: 01/12/2025 e 28/02/2026\n"
            "Data Historico Docto. Credito (R$) Debito (R$) Saldo (R$)\n"
        )
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Bradesco"
    assert header.account_holder == "WILLIAM VARGAS"
    assert header.agency == "3204"
    assert header.account_number == "130776-2"
    assert header.statement_period == "01/12/2025 e 28/02/2026"


def test_parse_header_handles_bank_of_america_metadata():
    text_pages = [
        (
            "MARIA A POSADA DUQUE bankofamerica.com\n"
            "Bank of America, N.A.\n"
            "Your combined statement\n"
            "for January 22, 2026 to February 18, 2026\n"
        ),
        "MARIA A POSADA DUQUE ! Account # 4830 2436 2176 ! January 22, 2026 to February 18, 2026\n",
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Bank of America"
    assert header.account_holder == "MARIA A POSADA DUQUE"
    assert header.account_number == "4830 2436 2176"
    assert header.statement_period == "January 22, 2026 to February 18, 2026"
