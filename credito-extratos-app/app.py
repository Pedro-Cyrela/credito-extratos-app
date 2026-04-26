from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from src.analysis_engine import analyze_uploaded_files
from src.export_excel import build_excel_export
from src.fx_ptax import FxQuote, fetch_ptax_sell_quote
from src.monthly_summary import build_monthly_summary, calculate_global_metrics


st.set_page_config(
    page_title="Análise de Crédito por Extratos",
    layout="wide",
)


MANUAL_OVERRIDE_REASON = "Ajuste manual do analista na interface."
FOREIGN_CURRENCY_OPTIONS = [
    "USD - Dolar americano",
    "EUR - Euro",
    "GBP - Libra esterlina",
    "CAD - Dolar canadense",
    "AUD - Dolar australiano",
    "CHF - Franco suico",
    "JPY - Iene japones",
    "ARS - Peso argentino",
    "CLP - Peso chileno",
    "COP - Peso colombiano",
    "MXN - Peso mexicano",
    "UYU - Peso uruguaio",
  "PYG - Guarani paraguaio",
  "CNY - Yuan chines",
  ]



st.markdown(
    """
    <style>
      .kpi-card { padding: 0.75rem 0.9rem; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.75rem; }
      .kpi-label { font-size: 0.85rem; opacity: 0.85; margin-bottom: 0.25rem; }
      .kpi-values { display: flex; gap: 0.5rem; align-items: baseline; flex-wrap: wrap; }
      .kpi-value { font-size: 1.45rem; font-weight: 650; line-height: 1.2; }
      .kpi-sep { opacity: 0.6; }
    </style>
    """,
    unsafe_allow_html=True,
)


def brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")



def currency_code(currency_option: str | None) -> str:
    if not currency_option:
        return "BRL"
    return currency_option.split(" - ", maxsplit=1)[0]



def money(value: float, currency: str = "BRL") -> str:
    if currency == "BRL":
        return brl(value)
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {formatted}"


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def get_latest_ptax_sell_quote(currency_code: str, reference_date: date) -> FxQuote | None:
    for days_back in range(0, 10):
        quote_date = reference_date - timedelta(days=days_back)
        quote = fetch_ptax_sell_quote(currency_code, quote_date)
        if quote:
            return quote
    return None


def format_dual_amount(value: float, currency: str, fx_quote: FxQuote | None) -> str:
    if not fx_quote or currency == "BRL":
        return money(value, currency)
    brl_value = float(value) * float(fx_quote.rate_brl_per_unit)
    return f"{money(value, currency)} - {brl(brl_value)}"


def dual_amount_parts(
    value: float, currency: str, fx_quote: FxQuote | None
) -> tuple[str, str | None]:
    if not fx_quote or currency == "BRL":
        return money(value, currency), None
    brl_value = float(value) * float(fx_quote.rate_brl_per_unit)
    return money(value, currency), brl(brl_value)


def format_dual_amount_md(value: float, currency: str, fx_quote: FxQuote | None) -> str:
    primary, secondary = dual_amount_parts(value, currency, fx_quote)
    if not secondary:
        return primary
    return f"{primary} ({secondary})"


def calculate_brl_metrics_from_summary(summary_df: pd.DataFrame) -> dict[str, float]:
    if summary_df.empty or "total_considerado_brl" not in summary_df.columns:
        return {
            "renda_media_mensal": 0.0,
            "meses_analisados": 0,
            "total_considerado": 0.0,
            "qtd_creditos": 0,
        }

    total_considerado = float(pd.to_numeric(summary_df["total_considerado_brl"], errors="coerce").fillna(0).sum())
    meses = int(len(summary_df))
    media = total_considerado / meses if meses else 0.0
    qtd_creditos = int(pd.to_numeric(summary_df["qtd_creditos_considerados"], errors="coerce").fillna(0).sum())

    return {
        "renda_media_mensal": round(media, 2),
        "meses_analisados": meses,
        "total_considerado": round(total_considerado, 2),
        "qtd_creditos": qtd_creditos,
    }



def has_foreign_detection(headers_df: pd.DataFrame, result: dict | None = None) -> bool:
    if result and result.get("foreign_detected") is not None:
        return bool(result["foreign_detected"])

    if headers_df.empty or "extrato_estrangeiro_detectado" not in headers_df.columns:
        return False
    return bool(headers_df["extrato_estrangeiro_detectado"].fillna(False).astype(bool).any())



def render_foreign_gate(headers_df: pd.DataFrame, result: dict) -> tuple[bool, str | None]:
    detected = has_foreign_detection(headers_df, result)

    with st.container(border=True):
        st.subheader("Extrato estrangeiro")
        if detected:
            st.info("O app encontrou indicios de extrato estrangeiro e marcou esta opcao como Sim. Confirme antes de seguir.")

        foreign_choice = st.radio(
            "Extrato estrangeiro?",
            options=["Nao", "Sim"],
            horizontal=True,
            key="foreign_statement_choice",
        )

        selected_currency = None
        if foreign_choice == "Sim":
            selected_currency = st.selectbox(
                "Moeda do extrato",
                options=FOREIGN_CURRENCY_OPTIONS,
                index=None,
                placeholder="Digite para pesquisar e selecione uma moeda",
                key="foreign_currency",
                help="A moeda nao e identificada automaticamente. Selecione uma unica moeda para liberar as analises.",
            )

            if not selected_currency:
                st.warning("Escolha a moeda estrangeira para liberar o painel de medias, resumo e tabelas.")

    return foreign_choice == "Sim", selected_currency



def render_kpi_card(label: str, primary: str, secondary: str | None = None):
    values_html = f"<span class='kpi-value'>{primary}</span>"
    if secondary:
        values_html = (
            f"<span class='kpi-value'>{primary}</span>"
            f"<span class='kpi-value kpi-sep'>|</span>"
            f"<span class='kpi-value'>{secondary}</span>"
        )
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{label}</div>
          <div class="kpi-values">{values_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(metrics: dict, display_currency: str = "BRL", fx_quote: FxQuote | None = None):
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        primary, secondary = dual_amount_parts(float(metrics["renda_media_mensal"]), display_currency, fx_quote)
        render_kpi_card("Renda média mensal", primary, secondary)
    with col2:
        render_kpi_card("Meses analisados", str(metrics["meses_analisados"]))
    with col3:
        primary, secondary = dual_amount_parts(float(metrics["total_considerado"]), display_currency, fx_quote)
        render_kpi_card("Total considerado", primary, secondary)
    with col4:
        render_kpi_card("Qtd. créditos considerados", str(metrics["qtd_creditos"]))



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
            if "extrato_estrangeiro_detectado" in row.index:
                detected_label = "Sim" if bool(row.get("extrato_estrangeiro_detectado", False)) else "Nao"
                st.caption(f"Extrato estrangeiro detectado: {detected_label}")
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
    value_format: str = "%.2f",
):
    if df.empty:
        st.info("Nenhuma linha nesta visão.")
        return

    editor_df = df.copy().set_index("row_id")
    editor_df[action_label] = False

    column_config: dict[str, st.column_config.BaseColumn] = {
        action_label: st.column_config.CheckboxColumn(action_label),
        "valor": st.column_config.NumberColumn("valor", format=value_format),
    }
    if "valor_brl" in editor_df.columns:
        column_config["valor_brl"] = st.column_config.NumberColumn("valor_brl", format="R$ %.2f")

    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=False,
        disabled=[column for column in editor_df.columns if column != action_label],
        column_config=column_config,
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
if "foreign_statement_choice" not in st.session_state:
    st.session_state["foreign_statement_choice"] = "Nao"
if "foreign_currency" not in st.session_state:
    st.session_state["foreign_currency"] = None

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
        detected_foreign = bool(st.session_state["analysis_result"].get("foreign_detected"))
        st.session_state["foreign_statement_choice"] = "Sim" if detected_foreign else "Nao"
        st.session_state["foreign_currency"] = None

result = st.session_state.get("analysis_result")

if result:
    headers_df = result["headers"]
    base_transactions = ensure_row_ids(result["transactions"])
    transactions_df = apply_manual_overrides(base_transactions, st.session_state.get("manual_overrides", {}))

    st.subheader("Cabeçalho dos extratos")
    render_header_cards(headers_df)

    fx_quote: FxQuote | None = None
    with st.sidebar:
        st.divider()
        is_foreign_statement, selected_currency = render_foreign_gate(headers_df, result)

        display_currency = currency_code(selected_currency) if is_foreign_statement else "BRL"
        if is_foreign_statement and selected_currency:
            fx_quote = get_latest_ptax_sell_quote(display_currency, date.today())
            if fx_quote:
                st.caption(
                    "Cotacao PTAX venda ({}) - 1 {} = {}".format(
                        fx_quote.requested_date.strftime("%d/%m/%Y"),
                        display_currency,
                        brl(float(fx_quote.rate_brl_per_unit)),
                    )
                )
            else:
                st.warning("Nao foi possivel obter cotacao PTAX para conversao em BRL (tentado hoje e dias anteriores).")

    if is_foreign_statement and not selected_currency:
        st.stop()

    headers_for_export = headers_df.copy()
    headers_for_export["extrato_estrangeiro_confirmado"] = "Sim" if is_foreign_statement else "Nao"
    if is_foreign_statement:
        headers_for_export["moeda_selecionada"] = selected_currency
        transactions_df = transactions_df.copy()
        transactions_df["moeda_extrato"] = display_currency
        if fx_quote:
            transactions_df["cotacao_ptax_venda"] = float(fx_quote.rate_brl_per_unit)
            transactions_df["data_cotacao_ptax"] = fx_quote.requested_date.strftime("%d/%m/%Y")
            valor_numeric = pd.to_numeric(transactions_df["valor"], errors="coerce")
            transactions_df["valor_brl"] = (valor_numeric * float(fx_quote.rate_brl_per_unit)).round(2)
            headers_for_export["cotacao_ptax_venda"] = float(fx_quote.rate_brl_per_unit)
            headers_for_export["data_cotacao_ptax"] = fx_quote.requested_date.strftime("%d/%m/%Y")

        if fx_quote:
            st.caption(
                "Valores em {} com conversao para BRL via PTAX venda ({}).".format(
                    display_currency,
                    fx_quote.requested_date.strftime("%d/%m/%Y"),
                )
            )
        else:
            st.caption("Valores em {} (sem conversao automatica para BRL).".format(display_currency))

    recalculated_summary = build_monthly_summary(transactions_df)
    if fx_quote and "valor_brl" in transactions_df.columns:
        brl_base = transactions_df.copy()
        brl_base["valor"] = pd.to_numeric(brl_base["valor_brl"], errors="coerce").fillna(0)
        brl_summary = build_monthly_summary(brl_base)
        brl_summary = brl_summary.rename(
            columns={
                "total_considerado": "total_considerado_brl",
                "total_desconsiderado": "total_desconsiderado_brl",
            }
        )
        brl_summary = brl_summary.drop(
            columns=[c for c in ["qtd_creditos_considerados", "qtd_revisao"] if c in brl_summary.columns],
            errors="ignore",
        )
        recalculated_summary = recalculated_summary.merge(brl_summary, on="mes_ref", how="left")

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
    filtered_metrics_brl = calculate_brl_metrics_from_summary(filtered_summary) if fx_quote else None

    st.subheader("Painel executivo")
    if fx_quote and display_currency != "BRL":
        with st.container(border=True):
            st.markdown(
                "**Cotação PTAX venda ({})** — 1 {} = {}".format(
                    fx_quote.requested_date.strftime("%d/%m/%Y"),
                    display_currency,
                    brl(float(fx_quote.rate_brl_per_unit)),
                )
            )

    render_metrics(filtered_metrics, display_currency, fx_quote=fx_quote)

    st.subheader("Resumo mensal")
    summary_value_format = "%.2f" if display_currency == "BRL" else f"{display_currency} %.2f"
    summary_column_config: dict[str, st.column_config.BaseColumn] = {
        "total_considerado": st.column_config.NumberColumn("total_considerado", format=summary_value_format),
        "total_desconsiderado": st.column_config.NumberColumn("total_desconsiderado", format=summary_value_format),
    }
    if fx_quote and "total_considerado_brl" in filtered_summary.columns:
        summary_column_config["total_considerado_brl"] = st.column_config.NumberColumn(
            "total_considerado_brl", format="R$ %.2f"
        )
    if fx_quote and "total_desconsiderado_brl" in filtered_summary.columns:
        summary_column_config["total_desconsiderado_brl"] = st.column_config.NumberColumn(
            "total_desconsiderado_brl", format="R$ %.2f"
        )

    st.dataframe(
        filtered_summary,
        use_container_width=True,
        hide_index=True,
        column_config=summary_column_config,
    )

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
                  - A **média mensal considerada** está em **{format_dual_amount_md(float(media), display_currency, fx_quote)}**.
                  - O mês com maior volume considerado foi **{maior_mes['mes_ref']}**, com **{format_dual_amount_md(float(maior_mes['total_considerado']), display_currency, fx_quote)}**.
                  - As movimentações podem ser reclassificadas manualmente nas tabelas abaixo e exportadas no Excel.
                  """
              )

    considered_view, disregarded_view, review_view = build_views(filtered_transactions)
    value_format = "%.2f" if display_currency == "BRL" else f"{display_currency} %.2f"

    st.subheader("Movimentações consideradas")
    render_transfer_editor(
        df=considered_view,
        action_label="Mover para desconsideradas",
        target_status="desconsiderado",
        editor_key="considered_editor",
        button_key="considered_button",
        value_format=value_format,
    )

    st.subheader("Movimentações desconsideradas")
    render_transfer_editor(
        df=disregarded_view,
        action_label="Mover para consideradas",
        target_status="considerado",
        editor_key="disregarded_editor",
        button_key="disregarded_button",
        value_format=value_format,
    )

    st.subheader("Movimentações para revisão")
    st.dataframe(review_view, use_container_width=True, hide_index=True)

    export_bytes = build_excel_export(
        full_df=filtered_transactions,
        summary_df=filtered_summary,
        considered_df=considered_view,
        disregarded_df=disregarded_view,
        review_df=review_view,
        metadata_df=headers_for_export,
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
