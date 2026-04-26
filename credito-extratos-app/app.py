from __future__ import annotations

from datetime import date, datetime, timedelta
import html

import pandas as pd
import streamlit as st

from src.analysis_engine import analyze_uploaded_files
from src.export_excel import build_excel_export
from src.fx_ptax import FxQuote, fetch_ptax_sell_quote
from src.monthly_summary import build_monthly_summary, calculate_global_metrics
try:
    from fpdf import FPDF  # noqa: F401
    from src.pdf_report import build_pdf_report

    PDF_REPORT_AVAILABLE = True
except ImportError:
    build_pdf_report = None
    PDF_REPORT_AVAILABLE = False


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
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

      :root {
        --bg:       #f5f6fa;
        --surface:  #ffffff;
        --surface2: #f0f1f8;
        --border:   #dde1f0;
        --text:     #1a1d35;
        --muted:    #6b7299;
        --accent:   #5b52e8;
        --green:    #00b894;
        --radius:   12px;
        --shadow:   0 2px 12px rgba(91,82,232,.06);
      }

      html, body, [class*="css"] { font-family: 'Inter', sans-serif; color: var(--text); }
      .stApp { background: var(--bg); }

      /* Hide Streamlit chrome */
      #MainMenu, footer { visibility: hidden; }
      [data-testid="stHeader"] { background: transparent; }

      /* Layout spacing (room for custom topbar) */
      .block-container { padding-top: 5.5rem; padding-left: 1.75rem; padding-right: 1.75rem; padding-bottom: 2.5rem; max-width: 1400px; }

      /* Sidebar */
      [data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
      [data-testid="stSidebar"] .block-container { padding-top: 1.25rem; }

      /* Custom topbar */
      .ce-topbar {
        position: fixed; top: 0; left: 0; right: 0; height: 56px;
        background: var(--surface);
        border-bottom: 1px solid var(--border);
        box-shadow: 0 1px 0 var(--border), 0 2px 8px rgba(0,0,0,.04);
        z-index: 1000;
        display: grid;
        grid-template-columns: 1fr auto 1fr;
        align-items: center;
        padding: 0 24px;
      }
      .ce-topbar-left { justify-self: start; }
      .ce-topbar-mid { justify-self: center; }
      .ce-topbar-right { justify-self: end; }

      .ce-brand { display:flex; align-items:center; gap:10px; font-weight:800; font-size: 15px; }
      .ce-mark {
        width: 32px; height: 32px; border-radius: 8px;
        background: linear-gradient(135deg, var(--accent), var(--green));
        display:flex; align-items:center; justify-content:center; color:white; font-weight:800;
      }
      .ce-chip {
        background: var(--surface2); border: 1px solid var(--border);
        border-radius: 999px; padding: 4px 12px;
        font-size: 12px; font-weight: 600; color: var(--muted);
        display:flex; align-items:center; gap:8px;
      }
      .ce-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); }

      /* Cards / containers */
      .ce-card {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: 14px 14px;
      }
      .ce-card + .ce-card { margin-top: 12px; }

      /* Section headers */
      .ce-section-head { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin: 6px 0 12px; }
      .ce-section-kicker { font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:1.2px; color: var(--muted); }
      .ce-section-title { font-size: 18px; font-weight: 850; letter-spacing: -0.02em; margin-top: 2px; }
      .ce-section-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
      .ce-pill {
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 700;
        color: var(--muted);
        white-space: nowrap;
      }
      .ce-chipline { display:flex; flex-wrap:wrap; gap:8px; margin-top: 10px; }
      .ce-chip2 {
        background: var(--surface2);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 700;
        color: var(--text);
        white-space: nowrap;
      }
      .ce-muted { color: var(--muted); }

      /* KPI */
      .kpi-card { background: var(--surface); box-shadow: var(--shadow); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 14px; }
      .kpi-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.1px; color: var(--muted); margin-bottom: 0.45rem; }
      .kpi-values { display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; }
      .kpi-value { font-size: 1.45rem; font-weight: 800; line-height: 1.2; }
      .kpi-sep { opacity: 0.35; }

      /* Buttons */
      .stButton > button, .stDownloadButton > button {
        border-radius: 10px;
        border: 1px solid var(--border);
      }
      .stButton > button[kind="primary"] {
        background: var(--accent);
        border: 1px solid rgba(0,0,0,0);
      }
      .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: rgba(91,82,232,.35);
      }

      /* Dataframes & editor */
      [data-testid="stDataFrame"], [data-testid="stDataEditor"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        padding: 8px;
      }
      [data-testid="stDataFrame"] table, [data-testid="stDataEditor"] table { font-size: 13px; }
      [data-testid="stDataFrame"] thead tr th, [data-testid="stDataEditor"] thead tr th {
        background: var(--surface2) !important;
        border-bottom: 1px solid var(--border) !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 1.0px;
        color: var(--muted) !important;
      }
      [data-testid="stDataFrame"] tbody tr:hover td, [data-testid="stDataEditor"] tbody tr:hover td {
        background: rgba(91,82,232,.06) !important;
      }

      /* Typography */
      h1, h2, h3 { letter-spacing: -0.02em; }
      h2 { font-size: 1.25rem; }
      h3 { font-size: 1.1rem; }
      .stCaption, [data-testid="stCaptionContainer"] { color: var(--muted); }
      [data-testid="stMetricValue"] { font-family: 'Inter', sans-serif; }

      /* Inputs */
      textarea, input, select {
        border-radius: 10px !important;
      }
      textarea:focus, input:focus, select:focus {
        border-color: rgba(91,82,232,.55) !important;
        box-shadow: 0 0 0 3px rgba(91,82,232,.12) !important;
      }

      /* Expander (Resumo inteligente) */
      [data-testid="stExpander"] {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
        overflow: hidden;
      }
      [data-testid="stExpander"] summary {
        padding: 10px 14px;
        font-weight: 850;
        letter-spacing: -0.01em;
      }
      [data-testid="stExpander"] summary:hover { background: rgba(91,82,232,.04); }
      [data-testid="stExpander"] div[role="region"] { padding: 0 14px 12px; }

      /* Alerts */
      [data-testid="stAlert"] { border-radius: var(--radius); border: 1px solid var(--border); box-shadow: var(--shadow); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="ce-topbar">
      <div class="ce-topbar-left"></div>
      <div class="ce-topbar-mid">
        <div class="ce-brand">
          <div class="ce-mark">CE</div>
          <div>Análise de Crédito - Extratos Bancários</div>
        </div>
      </div>
      <div class="ce-topbar-right">
        <div class="ce-chip"><span class="ce-dot"></span> Pronto</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


def render_section_header(title: str, subtitle: str | None = None, right_pill: str | None = None):
    subtitle_html = f"<div class='ce-section-sub'>{html.escape(subtitle)}</div>" if subtitle else ""
    right_html = f"<div class='ce-pill'>{html.escape(right_pill)}</div>" if right_pill else ""
    st.markdown(
        f"""
        <div class="ce-section-head">
          <div>
            <div class="ce-section-kicker">Seção</div>
            <div class="ce-section-title">{html.escape(title)}</div>
            {subtitle_html}
          </div>
          {right_html}
        </div>
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
        arquivo = html.escape(str(row.get("arquivo", "") or ""))
        banco = html.escape(str(row.get("banco", "") or "Não identificado"))
        titular = html.escape(str(row.get("titular", "") or "Não identificado"))
        conta = html.escape(str(row.get("conta", "") or "Não identificado"))
        agencia = html.escape(str(row.get("agencia", "") or "Não identificada"))
        periodo = html.escape(str(row.get("periodo", "") or ""))

        foreign_chip = ""
        if "extrato_estrangeiro_detectado" in row.index:
            detected_label = "Sim" if bool(row.get("extrato_estrangeiro_detectado", False)) else "Não"
            foreign_chip = f"<span class='ce-chip2'>Estrangeiro detectado: {html.escape(detected_label)}</span>"

        periodo_chip = f"<span class='ce-chip2'>Período: {periodo}</span>" if periodo else ""

        st.markdown(
            f"""
            <div class="ce-card">
              <div style="display:flex; align-items:baseline; justify-content:space-between; gap:16px;">
                <div style="font-weight:850; letter-spacing:-0.02em;">{arquivo}</div>
                <div class="ce-muted" style="font-size:12px; font-weight:700;">Cabeçalho</div>
              </div>
              <div style="margin-top:10px; display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:10px;">
                <div><div class="ce-section-kicker">Banco</div><div style="font-weight:700;">{banco}</div></div>
                <div><div class="ce-section-kicker">Titular</div><div style="font-weight:700;">{titular}</div></div>
                <div><div class="ce-section-kicker">Conta</div><div style="font-weight:700;">{conta}</div></div>
                <div><div class="ce-section-kicker">Agência</div><div style="font-weight:700;">{agencia}</div></div>
              </div>
              <div class="ce-chipline">
                {foreign_chip}
                {periodo_chip}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )



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
    column_order: list[str] | None = None,
):
    if df.empty:
        st.info("Nenhuma linha nesta visão.")
        return

    editor_df = df.copy()
    editor_df[action_label] = False

    column_config: dict[str, st.column_config.BaseColumn] = {
        action_label: st.column_config.CheckboxColumn(action_label),
        "data": st.column_config.DateColumn("data", format="DD/MM/YYYY"),
        "valor": st.column_config.NumberColumn("valor", format=value_format),
    }
    if "valor_brl" in editor_df.columns:
        column_config["valor_brl"] = st.column_config.NumberColumn("valor_brl", format="R$ %.2f")

    if column_order:
        preferred = [action_label, *[col for col in column_order if col != action_label]]
        existing = [col for col in preferred if col in editor_df.columns]
        remaining = [col for col in editor_df.columns if col not in set(existing)]
        editor_df = editor_df[existing + remaining]

    edited_df = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        disabled=[column for column in editor_df.columns if column != action_label],
        column_config=column_config,
        key=editor_key,
    )

    if st.button(f"Aplicar seleção - {action_label}", key=button_key, use_container_width=True):
        selected_ids = edited_df.loc[edited_df[action_label], "row_id"].tolist()
        apply_status_change(selected_ids, target_status)
        st.rerun()


    st.markdown(
        "<div class='ce-card' style='margin-bottom: 18px;'>"
        "<div style='display:flex; align-items:flex-end; justify-content:space-between; gap:16px;'>"
        "<div>"
        "<div class='ce-section-kicker'>Visão geral</div>"
        "<div style='font-size:18px; font-weight:850; letter-spacing:-0.02em; margin-top:2px;'>Análise pronta para revisão</div>"
        "<div class='ce-section-sub'>Leitura flexível de PDFs, exclusões automáticas, revisão manual e exportação auditável.</div>"
        "</div>"
        "<div class='ce-pill'>Backoffice</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

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
        st.session_state["pdf_bytes"] = None
        detected_foreign = bool(st.session_state["analysis_result"].get("foreign_detected"))
        st.session_state["foreign_statement_choice"] = "Sim" if detected_foreign else "Nao"
        st.session_state["foreign_currency"] = None

result = st.session_state.get("analysis_result")

if result:
    headers_df = result["headers"]
    base_transactions = ensure_row_ids(result["transactions"])
    transactions_df = apply_manual_overrides(base_transactions, st.session_state.get("manual_overrides", {}))

    render_section_header("Cabeçalho dos extratos", subtitle="Dados detectados no PDF (banco, titular, conta, período).")
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

    render_section_header("Painel executivo", subtitle="Métricas globais considerando o filtro atual.")
    if fx_quote and display_currency != "BRL":
        st.markdown(
            "<div class='ce-card'><div style='font-weight:850;'>"
            + html.escape(
                "Cotação PTAX venda ({}) - 1 {} = {}".format(
                    fx_quote.requested_date.strftime("%d/%m/%Y"),
                    display_currency,
                    brl(float(fx_quote.rate_brl_per_unit)),
                )
            )
            + "</div><div class='ce-section-sub'>Aplicada no BRL exibido ao lado quando disponível.</div></div>",
            unsafe_allow_html=True,
        )

    render_metrics(filtered_metrics, display_currency, fx_quote=fx_quote)

    months_count = len(filtered_summary) if isinstance(filtered_summary, pd.DataFrame) else 0
    render_section_header("Resumo mensal", subtitle="Totais por mês de referência.", right_pill=f"{months_count} mês(es)")
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

    considered_total = (
        float(pd.to_numeric(considered_view.get("valor"), errors="coerce").fillna(0).sum())
        if isinstance(considered_view, pd.DataFrame) and "valor" in considered_view.columns
        else 0.0
    )
    render_section_header(
        "Movimentações consideradas",
        subtitle="Créditos que entram no cálculo (você pode mover para desconsideradas).",
        right_pill=f"{len(considered_view)} registro(s) · {money(considered_total, display_currency)}",
    )
    render_transfer_editor(
        df=considered_view,
        action_label="Mover para desconsideradas",
        target_status="desconsiderado",
        editor_key="considered_editor",
        button_key="considered_button",
        value_format=value_format,
        column_order=[
            "data",
            "descricao",
            "valor",
            "valor_brl",
            "row_id",
            "mes_ref",
            "origem_identificada",
            "tipo_inferido",
            "status_inicial",
            "motivo_inicial",
            "score",
            "arquivo_origem",
            "status_final",
            "motivo_final",
            "termo_regra",
        ],
    )

    disregarded_total = (
        float(pd.to_numeric(disregarded_view.get("valor"), errors="coerce").fillna(0).sum())
        if isinstance(disregarded_view, pd.DataFrame) and "valor" in disregarded_view.columns
        else 0.0
    )
    render_section_header(
        "Movimentações desconsideradas",
        subtitle="Débitos e exclusões automáticas/manuais (você pode mover para consideradas).",
        right_pill=f"{len(disregarded_view)} registro(s) · {money(disregarded_total, display_currency)}",
    )
    render_transfer_editor(
        df=disregarded_view,
        action_label="Mover para consideradas",
        target_status="considerado",
        editor_key="disregarded_editor",
        button_key="disregarded_button",
        value_format=value_format,
        column_order=[
            "mes_ref",
            "data",
            "descricao",
            "valor",
            "valor_brl",
            "row_id",
            "origem_identificada",
            "tipo_inferido",
            "status_inicial",
            "motivo_inicial",
            "score",
            "arquivo_origem",
            "status_final",
            "termo_regra",
            "motivo_final",
        ],
    )

    render_section_header("Movimentações para revisão", subtitle="Linhas ambíguas que merecem validação manual.")
    review_df = review_view.copy()
    if "data" in review_df.columns:
        review_df = review_df.sort_values(["data", "descricao"], na_position="last")
    st.dataframe(
        review_df,
        use_container_width=True,
        hide_index=True,
        column_config={"data": st.column_config.DateColumn("data", format="DD/MM/YYYY")},
    )

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

    if PDF_REPORT_AVAILABLE:
        if st.button("Gerar PDF (resumo + créditos considerados)", use_container_width=True, key="pdf_generate"):
            with st.spinner("Gerando PDF..."):
                st.session_state["pdf_bytes"] = build_pdf_report(
                    headers_df=headers_for_export,
                    metrics=filtered_metrics,
                    considered_df=considered_view,
                    display_currency=display_currency,
                    fx_quote=fx_quote,
                )

        if st.session_state.get("pdf_bytes"):
            pdf_filename = f"relatorio_credito_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            st.download_button(
                "Baixar PDF do relatório",
                data=st.session_state["pdf_bytes"],
                file_name=pdf_filename,
                mime="application/pdf",
                use_container_width=True,
            )
    else:
        st.caption("PDF indisponível: instale a dependência `fpdf2` para habilitar este recurso.")

    if st.session_state.get("manual_overrides"):
        st.info("Existem ajustes manuais aplicados nesta análise.")

    st.success("Análise concluída. Revise as tabelas, ajuste o que for necessário e exporte o Excel.")
else:
    st.info(
        "Envie os PDFs na barra lateral, informe restrições opcionais e clique em **Processar análise**."
    )
