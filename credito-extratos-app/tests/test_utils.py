from src.utils import infer_counterparty, parse_brl_number


def test_parse_brl_number_understands_trailing_minus_and_cd_suffixes():
    assert parse_brl_number("1.234,56-") == -1234.56
    assert parse_brl_number("1.234,56 D") == -1234.56
    assert parse_brl_number("1.234,56 C") == 1234.56


def test_infer_counterparty_removes_transfer_prefix():
    assert infer_counterparty("PIX RECEBIDO DE JOAO SILVA") == "JOAO SILVA"


def test_infer_counterparty_handles_nubank_pix_layout():
    descricao = "Transferência recebida pelo Pix JAQUELYNE NUNES LIMOEIRO - •••.287.967-••"
    assert infer_counterparty(descricao) == "JAQUELYNE NUNES LIMOEIRO"
