import pandas as pd

from src.exclusion_rules import apply_exclusion_rules


def test_full_name_rule_requires_the_informed_name():
    df = pd.DataFrame(
        [
            {
                "descricao": "PIX RECEBIDO DE PEDRO",
                "tipo_inferido": "credito",
                "valor": 1000.0,
                "status_inicial": "considerado",
                "motivo_inicial": "ok",
            }
        ]
    )
    result = apply_exclusion_rules(df, custom_terms=[], custom_names=["PEDRO LUCAS"])
    assert result.loc[0, "status_final"] == "considerado"


def test_exact_first_name_rule_disregards_credit_without_matching_longer_name():
    df = pd.DataFrame(
        [
            {
                "descricao": "PIX RECEBIDO DE PEDRO SILVA",
                "tipo_inferido": "credito",
                "valor": 1000.0,
                "status_inicial": "considerado",
                "motivo_inicial": "ok",
            },
            {
                "descricao": "PIX RECEBIDO DE PEDROSA LTDA",
                "tipo_inferido": "credito",
                "valor": 500.0,
                "status_inicial": "considerado",
                "motivo_inicial": "ok",
            },
        ]
    )

    result = apply_exclusion_rules(df, custom_terms=["word:PEDRO"], custom_names=[])

    assert result.loc[0, "status_final"] == "desconsiderado"
    assert result.loc[1, "status_final"] == "considerado"
