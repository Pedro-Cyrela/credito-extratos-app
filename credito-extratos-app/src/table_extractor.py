from __future__ import annotations

from typing import Iterable

import pandas as pd

from .utils import normalize_text


def _make_unique_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []

    for index, raw_name in enumerate(columns):
        base_name = normalize_text(raw_name) or f"col_{index}"
        count = seen.get(base_name, 0)
        unique_name = base_name if count == 0 else f"{base_name}_{count}"
        seen[base_name] = count + 1
        unique.append(unique_name)

    return unique


def tables_to_dataframes(raw_tables: list[list[list[str | None]]]) -> list[pd.DataFrame]:
    dataframes: list[pd.DataFrame] = []

    for table in raw_tables:
        if not table or len(table) < 2:
            continue

        rows = [[normalize_text(cell) for cell in row] for row in table]
        header = rows[0]
        body = rows[1:]

        if len(set(header)) <= 1:
            continue

        max_len = max(len(header), *(len(r) for r in body))
        header = header + [f"col_{i}" for i in range(len(header), max_len)]
        header = _make_unique_columns(header)
        normalized_rows = [r + [""] * (max_len - len(r)) for r in body]
        df = pd.DataFrame(normalized_rows, columns=header)

        if df.empty:
            continue

        if df.dropna(how="all").empty:
            continue

        dataframes.append(df)

    return dataframes
