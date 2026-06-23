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


def test_parse_header_handles_c6_metadata():
    text_pages = [
        (
            "Extrato exportado no dia 2 de maio de 2026 às 15:27\n"
            "RAPHAELA GOMES DE CARVALHO BENTO • 203.723.007-90\n"
            "Agência: 1 • Conta: 167306170\n"
            "Extrato Período • 3 de novembro de 2025 até 2 de maio de 2026\n"
        ),
        "No app do C6 Bank\n",
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "C6 Bank"
    assert header.account_holder == "RAPHAELA GOMES DE CARVALHO BENTO"
    assert header.agency == "1"
    assert header.account_number == "167306170"
    assert header.statement_period == "3 de novembro de 2025 ate 2 de maio de 2026"


def test_parse_header_handles_itau_personnalite_inline_holder_metadata():
    text_pages = [
        (
            "ERICA CRUZEIRO MOREIRA CPF: 070.090.687-80 agência: 3830 conta: 12125-1\n"
            "saldo em conta Limite da Conta utilizado Limite da Conta disponível Limite da Conta total*\n"
            "extrato conta corrente\n"
            "lançamentos\n"
            "período de visualização: de 01/11/2025 até 02/05/2026 emitido em: 02/05/2026 14:54:34\n"
        )
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Itaú"
    assert header.account_holder == "ERICA CRUZEIRO MOREIRA"
    assert header.agency == "3830"
    assert header.account_number == "12125-1"


def test_parse_header_handles_nubank_pj_holder_with_cnpj_on_next_line():
    text_pages = [
        (
            "28.260.680 THAINA SILVA ALVES DA COSTA\n"
            "CNPJ 28.260.680/0001-00 Agência 0001 Conta\n"
            "58300273-3\n"
            "Movimentações\n"
        )
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Nubank"
    assert header.account_holder == "THAINA SILVA ALVES DA COSTA"
    assert header.agency == "0001"
    assert header.account_number == "58300273-3"


def test_parse_header_handles_inter_holder_above_cpf_cnpj_line():
    text_pages = [
        (
            "Solicitado em: 02/05/2026 - 15h01\n"
            "LETICIA JOANNI MATTEDI 14553370727\n"
            "CPF/CNPJ: 36.573.294/0001-98, Instituição: Banco Inter, Agência: 0001-9, Conta: 18866265-0\n"
            "Período: 02/05/2025 a 02/05/2026\n"
        )
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Inter"
    assert header.account_holder == "LETICIA JOANNI MATTEDI"
    assert header.agency == "0001-9"
    assert header.account_number == "18866265-0"


def test_parse_header_handles_xp_conta_digital_metadata():
    text_pages = [
        (
            "22/06/2026 19:08:59 Conta Digital XP | Extrato\n"
            "Conta Digital Extrato\n"
            "Data da consulta: 22/06/2026 19:08:59\n"
            "CLIENTE EXEMPLO Banco XP S.A | Agencia: 0001 | Conta: 12345678\n"
            "Documento: 000.000.000-00 De: 24/03/2026 Ate: 22/06/2026\n"
            "Data Descricao Valor Saldo\n"
        )
    ]

    header = parse_header(text_pages)

    assert header.bank_name == "Banco XP"
    assert header.account_holder == "CLIENTE EXEMPLO"
    assert header.agency == "0001"
    assert header.account_number == "12345678"
    assert header.statement_period == "24/03/2026 a 22/06/2026"
