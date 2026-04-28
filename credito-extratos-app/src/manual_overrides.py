from __future__ import annotations

from decimal import Decimal, InvalidOperation

import pandas as pd


def _serialize_date(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value).strip()
    return parsed.strftime("%Y-%m-%d")


def _serialize_number(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value).strip()
    return f"{decimal_value.quantize(Decimal('0.01'))}"


def build_transaction_key(row: pd.Series | dict) -> str:
    record = row if isinstance(row, dict) else row.to_dict()
    return "||".join(
        [
            _serialize_date(record.get("data")),
            str(record.get("descricao", "") or "").strip(),
            _serialize_number(record.get("valor")),
            str(record.get("arquivo_origem", "") or "").strip(),
        ]
    )


def ensure_transaction_keys(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy().reset_index(drop=True)
    result["transaction_key"] = result.apply(build_transaction_key, axis=1)
    return result


def normalize_manual_overrides(
    overrides: dict[object, dict[str, str]],
    df: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    if not overrides:
        return {}

    keyed_df = ensure_transaction_keys(df)
    row_id_to_key = {}
    if "row_id" in keyed_df.columns:
        row_id_to_key = keyed_df.set_index("row_id")["transaction_key"].to_dict()

    normalized: dict[str, dict[str, str]] = {}
    for raw_key, override in overrides.items():
        transaction_key = raw_key if isinstance(raw_key, str) else row_id_to_key.get(raw_key)
        if not transaction_key:
            continue
        normalized[str(transaction_key)] = dict(override)
    return normalized


def keep_matching_overrides(
    overrides: dict[str, dict[str, str]],
    df: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    if not overrides:
        return {}

    keyed_df = ensure_transaction_keys(df)
    valid_keys = set(keyed_df["transaction_key"].tolist())
    return {key: dict(override) for key, override in overrides.items() if key in valid_keys}


def _should_apply_override(current_status: str, override_status: str) -> bool:
    if override_status == "desconsiderado":
        return True
    if current_status == "desconsiderado" and override_status != "desconsiderado":
        return False
    return True


def reconcile_manual_overrides(
    overrides: dict[str, dict[str, str]],
    df: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    if not overrides:
        return {}

    keyed_df = ensure_transaction_keys(df)
    matching = keep_matching_overrides(overrides, keyed_df)
    status_by_key = keyed_df.set_index("transaction_key")["status_final"].to_dict()

    reconciled: dict[str, dict[str, str]] = {}
    for transaction_key, override_data in matching.items():
        current_status = str(status_by_key.get(transaction_key, "") or "")
        override_status = str(override_data.get("status_final", "") or "")
        if override_status and not _should_apply_override(current_status, override_status):
            continue
        reconciled[transaction_key] = dict(override_data)
    return reconciled


def apply_manual_overrides(df: pd.DataFrame, overrides: dict[str, dict[str, str]]) -> pd.DataFrame:
    result = ensure_transaction_keys(df)
    if result.empty or not overrides:
        return result

    for transaction_key, override_data in overrides.items():
        mask = result["transaction_key"] == transaction_key
        if not mask.any():
            continue

        for column, value in override_data.items():
            result.loc[mask, column] = value

    return result
