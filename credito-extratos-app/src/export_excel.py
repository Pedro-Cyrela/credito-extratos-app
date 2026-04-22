from __future__ import annotations

import pandas as pd

from .utils import to_excel_bytes


def build_excel_export(
    full_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    considered_df: pd.DataFrame,
    disregarded_df: pd.DataFrame,
    review_df: pd.DataFrame,
    metadata_df: pd.DataFrame,
) -> bytes:
    sheets = {
        "Resumo_Mensal": summary_df,
        "Mov_Consideradas": considered_df,
        "Mov_Desconsideradas": disregarded_df,
        "Mov_Revisar": review_df,
        "Analise_Completa": full_df,
        "Cabecalho": metadata_df,
    }
    return to_excel_bytes(sheets)
