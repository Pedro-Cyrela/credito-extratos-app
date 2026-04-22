import pandas as pd

from src.exclusion_rules import apply_exclusion_rules


def test_name_rule_disregards_credit():
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
    result = apply_exclusion_rules(df, custom_terms=[], custom_names=["PEDRO LUCAS"], flexible_names=True)
    assert result.loc[0, "status_final"] == "desconsiderado"
