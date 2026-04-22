from __future__ import annotations

import pandas as pd


def build_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "mes_ref",
                "total_considerado",
                "qtd_creditos_considerados",
                "total_desconsiderado",
                "qtd_revisao",
            ]
        )

    grouped_rows = []
    for mes, month_df in df.groupby("mes_ref", dropna=False):
        considered = month_df[(month_df["status_final"] == "considerado") & (month_df["valor"] > 0)]
        disregarded = month_df[month_df["status_final"] == "desconsiderado"]
        review = month_df[month_df["status_final"] == "revisar"]

        grouped_rows.append(
            {
                "mes_ref": mes,
                "total_considerado": round(float(considered["valor"].sum()), 2),
                "qtd_creditos_considerados": int(len(considered)),
                "total_desconsiderado": round(float(disregarded["valor"].abs().sum()), 2),
                "qtd_revisao": int(len(review)),
            }
        )

    summary = pd.DataFrame(grouped_rows)
    summary["_mes_ordem"] = pd.to_datetime("01/" + summary["mes_ref"], format="%d/%m/%Y", errors="coerce")
    summary = summary.sort_values(["_mes_ordem", "mes_ref"]).drop(columns="_mes_ordem").reset_index(drop=True)
    return summary


def calculate_global_metrics(summary_df: pd.DataFrame) -> dict[str, float]:
    if summary_df.empty:
        return {
            "renda_media_mensal": 0.0,
            "meses_analisados": 0,
            "total_considerado": 0.0,
            "qtd_creditos": 0,
        }

    total_considerado = float(summary_df["total_considerado"].sum())
    meses = int(len(summary_df))
    media = total_considerado / meses if meses else 0.0
    qtd_creditos = int(summary_df["qtd_creditos_considerados"].sum())

    return {
        "renda_media_mensal": round(media, 2),
        "meses_analisados": meses,
        "total_considerado": round(total_considerado, 2),
        "qtd_creditos": qtd_creditos,
    }
