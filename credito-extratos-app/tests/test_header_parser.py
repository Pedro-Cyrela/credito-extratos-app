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
