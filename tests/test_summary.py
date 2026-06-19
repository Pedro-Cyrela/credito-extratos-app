import pandas as pd

from src.monthly_summary import build_monthly_summary


def test_build_monthly_summary_sorts_months_chronologically():
    df = pd.DataFrame(
        [
            {"mes_ref": "12/2025", "status_final": "considerado", "valor": 1000.0},
            {"mes_ref": "02/2026", "status_final": "considerado", "valor": 500.0},
            {"mes_ref": "01/2026", "status_final": "considerado", "valor": 750.0},
        ]
    )

    result = build_monthly_summary(df)

    assert result["mes_ref"].tolist() == ["12/2025", "01/2026", "02/2026"]
