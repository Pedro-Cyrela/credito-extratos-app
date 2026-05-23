import pandas as pd

from src.analysis_engine import _ensure_transaction_schema


def test_ensure_transaction_schema_preserves_extra_columns_on_empty_dataframe():
    df = pd.DataFrame(columns=["status_final", "motivo_final", "termo_regra"])

    result = _ensure_transaction_schema(df)

    assert "status_final" in result.columns
    assert "motivo_final" in result.columns
    assert "termo_regra" in result.columns
