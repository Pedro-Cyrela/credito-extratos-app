from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen


@dataclass(frozen=True)
class FxQuote:
    currency: str
    rate_brl_per_unit: float
    quote_datetime: datetime
    requested_date: date


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_ptax_sell_quote(currency_code: str, quote_date: date, timeout_seconds: int = 15) -> FxQuote | None:
    """
    Fetches PTAX sell quote (BRL per 1 unit of foreign currency) from BCB Olinda OData.

    Returns None when no quote exists for that date/currency or when the API is unreachable.
    """
    currency_code = (currency_code or "").strip().upper()
    if not currency_code or currency_code == "BRL":
        return None

    # BCB expects MM-DD-YYYY (US-style) in @dataCotacao
    date_str = quote_date.strftime("%m-%d-%Y")
    moeda = quote(currency_code, safe="")
    data_cotacao = quote(date_str, safe="")

    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        "CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)?"
        f"@moeda='{moeda}'&@dataCotacao='{data_cotacao}'&$top=1&$format=json"
    )

    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except URLError:
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    values = data.get("value") or []
    if not values:
        return None

    item = values[0] or {}
    rate = _safe_float(item.get("cotacaoVenda"))
    quote_dt_raw = item.get("dataHoraCotacao")
    if rate is None or not quote_dt_raw:
        return None

    try:
        quote_dt = datetime.fromisoformat(str(quote_dt_raw).replace("Z", "+00:00"))
    except ValueError:
        quote_dt = datetime.now()

    return FxQuote(
        currency=currency_code,
        rate_brl_per_unit=rate,
        quote_datetime=quote_dt,
        requested_date=quote_date,
    )

