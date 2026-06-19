from src.utils import infer_counterparty, parse_brl_number, parse_date


def test_parse_brl_number_understands_trailing_minus_and_cd_suffixes():
    assert parse_brl_number("1.234,56-") == -1234.56
    assert parse_brl_number("1.234,56 D") == -1234.56
    assert parse_brl_number("1.234,56 C") == 1234.56


def test_infer_counterparty_removes_transfer_prefix():
    assert infer_counterparty("PIX RECEBIDO DE JOAO SILVA") == "JOAO SILVA"


def test_infer_counterparty_handles_nubank_pix_layout():
    descricao = "Transferência recebida pelo Pix JAQUELYNE NUNES LIMOEIRO - •••.287.967-••"
    assert infer_counterparty(descricao) == "JAQUELYNE NUNES LIMOEIRO"


def test_parse_date_rejects_partial_dates_that_can_degrade_to_year_0001():
    assert parse_date("22/01") is None
    assert parse_date("01/0001") is None
    assert parse_date("0001-01-22") is None
