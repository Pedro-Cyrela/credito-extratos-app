from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.analysis_engine import analyze_uploaded_files
from src.export_excel import build_excel_export
from src.monthly_summary import build_monthly_summary, calculate_global_metrics


st.set_page_config(
    page_title="Análise de Crédito por Extratos",
    layout="wide",
)


MANUAL_OVERRIDE_REASON = "Ajuste manual do analista na interface."



def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def render_metrics(metrics: dict):
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Renda média mensal", brl(metrics["renda_media_mensal"]))
    col2.metric("Meses analisados", metrics["meses_analisados"])
    col3.metric("Total considerado", brl(metrics["total_considerado"]))
    col4.metric("Qtd. créditos considerados", metrics["qtd_creditos"])



def render_header_cards(headers_df: pd.DataFrame):
    if headers_df.empty:
        st.info("Nenhum cabeçalho de extrato foi identificado.")
        return

    for _, row in headers_df.iterrows():
        with st.container(border=True):
            st.markdown(f"**Arquivo:** {row.get('arquivo', '')}")
            c1, c2, c3, c4 = st.columns(4)
            c1.write(f"**Banco:** {row.get('banco', '') or 'Não identificado'}")
            c2.write(f"**Titular:** {row.get('titular', '') or 'Não identificado'}")
            c3.write(f"**Conta:** {row.get('conta', '') or 'Não identificado'}")
            c4.write(f"**Agência:** {row.get('agencia', '') or 'Não identificada'}")
            periodo = row.get("periodo", "")
            if periodo:
                st.caption(f"Período identificado: {periodo}")



def ensure_row_ids(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy().reset_index(drop=True)
    if "row_id" not in result.columns:
        result.insert(0, "row_id", range(1, len(result) + 1))
    return result



def apply_manual_overrides(df: pd.DataFrame, overrides: dict[int, dict[str, str]]) -> pd.DataFrame:
    result = df.copy()
    if result.empty or not overrides:
        return result

    if "row_id" not in result.columns:
        result = ensure_row_ids(result)

    for row_id, override_data in overrides.items():
        mask = result["row_id"] == row_id
        if not mask.any():
            continue
        for column, value in override_data.items():
            result.loc[mask, column] = value
    return result



def build_views(transactions_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    considered_df = transactions_df[
        (transactions_df["status_final"] == "considerado") & (transactions_df["valor"] > 0)
    ].copy()
    disregarded_df = transactions_df[transactions_df["status_final"] == "desconsiderado"].copy()
    review_df = transactions_df[transactions_df["status_final"] == "revisar"].copy()
    return considered_df, disregarded_df, review_df



def apply_status_change(selected_ids: list[int], new_status: str):
    if not selected_ids:
        return

    overrides = st.session_state.setdefault("manual_overrides", {})
    for row_id in selected_ids:
        overrides[int(row_id)] = {
            "status_final": new_status,
            "motivo_final": MANUAL_OVERRIDE_REASON,
        }



def render_transfer_editor(
    df: pd.DataFrame,
    action_label: str,
    target_status: str,
    editor_key: str,
    button_key: str,
):
    if df.empty:
        st.info("Nenhuma linha nesta visão.")
        return

    editor_df = df.copy().set_index("row_id")
    editor_df[action_label] = False

    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=False,
        disabled=[column for column in editor_df.columns if column != action_label],
        column_config={
            action_label: st.column_config.CheckboxColumn(action_label),
            "valor": st.column_config.NumberColumn("valor", format="%.2f"),
        },
        key=editor_key,
    )

    if st.button(f"Aplicar seleção - {action_label}", key=button_key, use_container_width=True):
        selected_ids = edited_df.index[edited_df[action_label]].tolist()
        apply_status_change(selected_ids, target_status)
        st.rerun()


st.title("Análise de Crédito por Extratos Bancários")
st.caption("Leitura flexível de extratos PDF com regras de exclusão automáticas, revisão manual e exportação auditável.")

if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None
if "manual_overrides" not in st.session_state:
    st.session_state["manual_overrides"] = {}

with st.sidebar:
    st.header("Parâmetros")
    uploaded_files = st.file_uploader(
        "Envie um ou mais extratos em PDF",
        type=["pdf"],
        accept_multiple_files=True,
        help="O app tenta interpretar diferentes layouts de extratos bancários.",
    )

    custom_names_raw = st.text_area(
        "Nomes de pessoas/empresas para desconsiderar",
        placeholder="Ex.: PEDRO LUCAS LOPES DE OLIVEIRA\nEMPRESA XPTO LTDA",
        help="Se o nome aparecer na descrição do crédito, a linha pode ser desconsiderada.",
        height=140,
    )

    custom_terms_raw = st.text_area(
        "Nomenclaturas extras para desconsiderar",
        placeholder="Ex.: empréstimo entre contas\najuste interno",
        height=120,
    )

    flexible_names = st.toggle(
        "Aplicar nomes com correspondência flexível",
        value=True,
        help="Quando ativo, o motor usa tokens do nome, como primeiro nome e combinações parciais, inclusive cortes comuns do primeiro nome.",
    )

    process = st.button("Processar análise", type="primary", use_container_width=True)

if process:
    if not uploaded_files:
        st.warning("Envie ao menos um PDF para processar.")
        st.stop()

    with st.spinner("Processando PDFs e consolidando a análise..."):
        st.session_state["analysis_result"] = analyze_uploaded_files(
            uploaded_files=uploaded_files,
            custom_terms_raw=custom_terms_raw,
            custom_names_raw=custom_names_raw,
            flexible_names=flexible_names,
        )
        st.session_state["manual_overrides"] = {}

result = st.session_state.get("analysis_result")

if result:
    headers_df = result["headers"]
    base_transactions = ensure_row_ids(result["transactions"])
    transactions_df = apply_manual_overrides(base_transactions, st.session_state.get("manual_overrides", {}))

    recalculated_summary = build_monthly_summary(transactions_df)

    st.subheader("Cabeçalho dos extratos")
    render_header_cards(headers_df)

    if not recalculated_summary.empty:
        default_months = recalculated_summary["mes_ref"].tolist()
        selected_months = st.multiselect(
            "Filtrar meses da análise",
            options=default_months,
            default=default_months,
        )
    else:
        selected_months = []

    filtered_transactions = transactions_df.copy()
    filtered_summary = recalculated_summary.copy()

    if selected_months:
        filtered_transactions = filtered_transactions[filtered_transactions["mes_ref"].isin(selected_months)].copy()
        filtered_summary = filtered_summary[filtered_summary["mes_ref"].isin(selected_months)].copy()

    filtered_metrics = calculate_global_metrics(filtered_summary)

    st.subheader("Painel executivo")
    render_metrics(filtered_metrics)

    st.subheader("Resumo mensal")
    st.dataframe(filtered_summary, use_container_width=True, hide_index=True)

    with st.expander("Resumo inteligente", expanded=True):
        if filtered_summary.empty:
            st.info("Não foi possível construir um resumo mensal com os dados extraídos.")
        else:
            meses = len(filtered_summary)
            media = filtered_summary["total_considerado"].mean() if meses else 0
            maior_mes = filtered_summary.sort_values("total_considerado", ascending=False).iloc[0]
            st.markdown(
                f"""
                - Foram analisados **{meses} mês(es)** com movimentações consideradas dentro do filtro atual.
                - A **média mensal considerada** está em **{brl(float(media))}**.
                - O mês com maior volume considerado foi **{maior_mes['mes_ref']}**, com **{brl(float(maior_mes['total_considerado']))}**.
                - As movimentações podem ser reclassificadas manualmente nas tabelas abaixo e exportadas no Excel.
                """
            )

    considered_view, disregarded_view, review_view = build_views(filtered_transactions)

    st.subheader("Movimentações consideradas")
    render_transfer_editor(
        df=considered_view,
        action_label="Mover para desconsideradas",
        target_status="desconsiderado",
        editor_key="considered_editor",
        button_key="considered_button",
    )

    st.subheader("Movimentações desconsideradas")
    render_transfer_editor(
        df=disregarded_view,
        action_label="Mover para consideradas",
        target_status="considerado",
        editor_key="disregarded_editor",
        button_key="disregarded_button",
    )

    st.subheader("Movimentações para revisão")
    st.dataframe(review_view, use_container_width=True, hide_index=True)

    export_bytes = build_excel_export(
        full_df=filtered_transactions,
        summary_df=filtered_summary,
        considered_df=considered_view,
        disregarded_df=disregarded_view,
        review_df=review_view,
        metadata_df=headers_df,
    )

    filename = f"analise_credito_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.download_button(
        "Baixar Excel da análise",
        data=export_bytes,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    if st.session_state.get("manual_overrides"):
        st.info("Existem ajustes manuais aplicados nesta análise.")

    st.success("Análise concluída. Revise as tabelas, ajuste o que for necessário e exporte o Excel.")
else:
    st.info(
        "Envie os PDFs na barra lateral, informe restrições opcionais e clique em **Processar análise**."
    )
