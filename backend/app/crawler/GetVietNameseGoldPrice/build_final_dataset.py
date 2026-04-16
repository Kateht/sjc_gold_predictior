from __future__ import annotations

import os
import shutil
import tempfile
import time
from io import StringIO
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from app.core.config import settings


ROOT_DIR = Path(__file__).resolve().parent
RAW_GOLD_CSV = ROOT_DIR / "gia_vang_pnj_sjc.csv"
DEFAULT_START_DATE = pd.Timestamp("2009-01-01")
OZ_PER_LUONG = 37.5 / 31.1034768

FRED_SERIES = ["FEDFUNDS", "CPIAUCSL", "DFII10"]

FED_H15_WEEKLY_INTEREST_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx"
    "?rel=H15&series=8e83f7f17c5cea4d190d85ae6737639f"
    "&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_H15_WEEKLY_INTEREST_COLUMN = "Federal funds effective rate"
BLS_CPI_SERIES_ID = "CUSR0000SA0"
TREASURY_REAL_YIELD_PAGE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView"
    "?type=daily_treasury_real_yield_curve&page={page_number}"
)
TREASURY_REAL_YIELD_COLUMN = "10 YR"
TREASURY_REAL_YIELD_MAX_PAGES = 40

YFINANCE_SERIES = [
    ("GC=F", "Gold", ["Close", "High", "Low", "Volume"]),
    ("DX-Y.NYB", "USD_index", ["Close"]),
    ("CL=F", "Oil", ["Close"]),
    ("VND=X", "USD_VND", ["Close"]),
    ("^GVZ", "GVZ", ["Close"]),
    ("^VIX", "VIX", ["Close"]),
    ("GLD", "ETF_Holdings", ["Close"]),
    ("^MOVE", "MOVE_Index", ["Close"]),
    ("^GSPC", "SP500", ["Close"]),
    ("VNM", "VNIndex_ETF", ["Close"]),
    ("BTC-USD", "Bitcoin", ["Close"]),
]

FINAL_DATASET_COLUMNS = [
    "Date",
    "SJC",
    "Interest",
    "CPI",
    "Real_Yield_10Y",
    "Gold_Close",
    "Gold_High",
    "Gold_Low",
    "Gold_Volume",
    "USD_index_Close",
    "Oil_Close",
    "USD_VND_Close",
    "GVZ_Close",
    "VIX_Close",
    "ETF_Holdings_Close",
    "MOVE_Index_Close",
    "SP500_Close",
    "VNIndex_ETF_Close",
    "Bitcoin_Close",
    "Gold_world_vnd",
    "SJC_Premium",
    "SJC_Premium_Percent",
    "Shock_Index",
    "Gold_SP500_Ratio",
    "SJC_Premium_Zscore",
    "Policy_Risk_Zone",
    "SJC_lag1",
    "SJC_lag7",
    "SJC_ma7",
    "Gold_return",
    "Gold_volume_rank",
    "Gold_range",
    "Gold_volatility_7",
    "Gold_momentum",
    "Gold_Volume_Anomaly",
    "PVT",
    "SP500_return",
    "VNIndex_ETF_return",
    "Bitcoin_return",
]

SOURCE_DATA_COLUMNS = [
    "SJC",
    "Interest",
    "CPI",
    "Real_Yield_10Y",
    "Gold_Close",
    "Gold_High",
    "Gold_Low",
    "Gold_Volume",
    "USD_index_Close",
    "Oil_Close",
    "USD_VND_Close",
    "GVZ_Close",
    "VIX_Close",
    "ETF_Holdings_Close",
    "MOVE_Index_Close",
    "SP500_Close",
    "VNIndex_ETF_Close",
    "Bitcoin_Close",
]

MARKET_SEED_COLUMNS = [
    "Interest",
    "CPI",
    "Real_Yield_10Y",
    "Gold_Close",
    "Gold_High",
    "Gold_Low",
    "Gold_Volume",
    "USD_index_Close",
    "Oil_Close",
    "USD_VND_Close",
    "GVZ_Close",
    "VIX_Close",
    "ETF_Holdings_Close",
    "MOVE_Index_Close",
    "SP500_Close",
    "VNIndex_ETF_Close",
    "Bitcoin_Close",
]

FINAL_DATASET_MISSING_LOG_PATH = ROOT_DIR / "logs" / "final_dataset_missing_columns.log"
SUMMARY_LOG_DATE = "SUMMARY_RANGE"

SOURCE_COLUMN_GROUPS = {
    "RAW_SJC": ("SJC",),
    "FRED:FEDFUNDS": ("Interest",),
    "FRED:CPIAUCSL": ("CPI",),
    "FRED:DFII10": ("Real_Yield_10Y",),
    "YFINANCE:GC=F": ("Gold_Close", "Gold_High", "Gold_Low", "Gold_Volume"),
    "YFINANCE:DX-Y.NYB": ("USD_index_Close",),
    "YFINANCE:CL=F": ("Oil_Close",),
    "YFINANCE:VND=X": ("USD_VND_Close",),
    "YFINANCE:^GVZ": ("GVZ_Close",),
    "YFINANCE:^VIX": ("VIX_Close",),
    "YFINANCE:GLD": ("ETF_Holdings_Close",),
    "YFINANCE:^MOVE": ("MOVE_Index_Close",),
    "YFINANCE:^GSPC": ("SP500_Close",),
    "YFINANCE:VNM": ("VNIndex_ETF_Close",),
    "YFINANCE:BTC-USD": ("Bitcoin_Close",),
}

SOURCE_BY_COLUMN = {
    column: source
    for source, columns in SOURCE_COLUMN_GROUPS.items()
    for column in columns
}

FRED_IMPUTATION_SPECS = (
    ("FRED:FEDFUNDS", "Interest", 45),
    ("FRED:CPIAUCSL", "CPI", 45),
    ("FRED:DFII10", "Real_Yield_10Y", 7),
)

MARKET_IMPUTE_COLUMNS = (
    "Gold_Close",
    "Gold_High",
    "Gold_Low",
    "Gold_Volume",
    "USD_index_Close",
    "Oil_Close",
    "USD_VND_Close",
    "GVZ_Close",
    "VIX_Close",
    "ETF_Holdings_Close",
    "MOVE_Index_Close",
    "SP500_Close",
    "VNIndex_ETF_Close",
    "Bitcoin_Close",
)

FRED_TIMEOUT_SECONDS = 60
FRED_RETRY_COUNT = 5
FRED_BACKOFF_SECONDS = 3.0
MARKET_SHORT_GAP_LIMIT = 3


@dataclass(frozen=True)
class SourceHealth:
    status: str
    missing_columns: tuple[str, ...]
    reason: str


def _normalize_timestamp(value: date | datetime | str | None, *, default: pd.Timestamp | None = None) -> pd.Timestamp:
    if value is None:
        if default is None:
            raise ValueError("Missing date value")
        return default
    return pd.Timestamp(value).normalize()


def _format_log_entry(date_text: str, source: str, missing_columns: list[str] | tuple[str, ...], reason: str | dict[str, str]) -> str:
    columns_text = ", ".join(missing_columns) if missing_columns else "-"
    if isinstance(reason, dict):
        reason_text = "; ".join(f"{column}: {reason[column]}" for column in missing_columns if column in reason)
        if not reason_text:
            reason_text = "-"
    else:
        reason_text = reason or "-"
    return f"date={date_text} | source={source} | missing_columns={columns_text} | reason={reason_text}"


def _append_missing_data_log(entries: list[str], *, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> None:
    if not entries:
        entries = [_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], "No missing source columns detected.")]

    FINAL_DATASET_MISSING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FINAL_DATASET_MISSING_LOG_PATH.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"\n--- {pd.Timestamp.now():%Y-%m-%d %H:%M:%S} ---\n")
        handle.write(f"Range: {start_ts:%Y-%m-%d} -> {end_ts:%Y-%m-%d}\n")
        handle.write("date | source | missing_columns | reason\n")
        for entry in entries:
            handle.write(f"{entry}\n")


def _build_preflight_entries(source_health: dict[str, SourceHealth], *, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> list[str]:
    entries: list[str] = []
    range_text = f"{start_ts:%Y-%m-%d} -> {end_ts:%Y-%m-%d}"
    for source, health in source_health.items():
        if health.status == "healthy":
            continue
        reason_map = {column: health.reason for column in health.missing_columns}
        entries.append(_format_log_entry(range_text, source, list(health.missing_columns), reason_map))
    return entries


def _infer_missing_reason(
    *,
    source: str,
    column: str,
    row_date: pd.Timestamp,
    source_frames: dict[str, pd.DataFrame],
    source_health: dict[str, SourceHealth],
) -> str:
    health = source_health.get(source)
    if health is not None and health.status == "unavailable":
        return health.reason

    frame = source_frames.get(source)
    if frame is None or frame.empty or "Date" not in frame.columns:
        if health is not None and health.status == "partial" and health.reason:
            return health.reason
        return "source returned no usable rows"

    frame_dates = pd.to_datetime(frame["Date"], errors="coerce").dt.normalize()
    row_mask = frame_dates == row_date.normalize()
    if not row_mask.any():
        return "source has no row for this date"

    if column not in frame.columns:
        if health is not None and health.status == "partial" and health.reason:
            return health.reason
        return "source response missing this column"

    value = frame.loc[row_mask, column].iloc[-1]
    if pd.isna(value):
        if health is not None and health.status == "partial" and column in health.missing_columns:
            return health.reason
        return "source row contains a missing value"

    if health is not None and health.status == "partial" and health.reason:
        return health.reason
    return "missing after merge"


def _build_row_issue_entries(
    df: pd.DataFrame,
    *,
    source_frames: dict[str, pd.DataFrame],
    source_health: dict[str, SourceHealth],
) -> list[str]:
    entries: list[str] = []
    missing_rows = df.loc[df[SOURCE_DATA_COLUMNS].isna().any(axis=1)]

    for _, row in missing_rows.iterrows():
        row_date = pd.Timestamp(row["Date"]).normalize()
        date_text = row_date.strftime("%Y-%m-%d")
        grouped_columns: dict[str, list[str]] = {}
        grouped_reasons: dict[str, dict[str, str]] = {}

        for column in SOURCE_DATA_COLUMNS:
            if pd.isna(row[column]):
                source = SOURCE_BY_COLUMN[column]
                grouped_columns.setdefault(source, []).append(column)
                grouped_reasons.setdefault(source, {})[column] = _infer_missing_reason(
                    source=source,
                    column=column,
                    row_date=row_date,
                    source_frames=source_frames,
                    source_health=source_health,
                )

        for source, columns in grouped_columns.items():
            entries.append(_format_log_entry(date_text, source, columns, grouped_reasons[source]))

    return entries


def _load_cached_final_dataset_frame() -> pd.DataFrame | None:
    candidate_paths = [Path(settings.LOCAL_DATASET_PATH)]
    crawler_dataset_path = getattr(settings, "CRAWLER_DATASET_PATH", None)
    if crawler_dataset_path:
        candidate_paths.append(Path(str(crawler_dataset_path)))

    for candidate_path in candidate_paths:
        if not candidate_path.exists():
            continue

        try:
            frame = pd.read_csv(candidate_path)
        except Exception:
            continue

        if "Date" not in frame.columns:
            continue

        frame = frame.copy()
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
        if not frame.empty:
            return frame

    return None


def _align_series_to_dates(target_dates: pd.Series, source_frame: pd.DataFrame, value_column: str, *, tolerance_days: int) -> pd.Series:
    if source_frame.empty or "Date" not in source_frame.columns or value_column not in source_frame.columns:
        return pd.Series(np.nan, index=target_dates.index, dtype="float64")

    source = source_frame[["Date", value_column]].copy()
    source["Date"] = pd.to_datetime(source["Date"], errors="coerce")
    source[value_column] = pd.to_numeric(source[value_column], errors="coerce")
    source = source.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    source = source.dropna(subset=[value_column])
    if source.empty:
        return pd.Series(np.nan, index=target_dates.index, dtype="float64")

    target = pd.DataFrame({"Date": pd.to_datetime(target_dates, errors="coerce")})
    aligned = pd.merge_asof(
        target,
        source,
        on="Date",
        direction="backward",
        tolerance=pd.Timedelta(days=tolerance_days),
    )
    return pd.to_numeric(aligned[value_column], errors="coerce")


def _finalize_macro_series_frame(
    frame: pd.DataFrame,
    *,
    value_column: str,
    target_column: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    if "Date" not in frame.columns or value_column not in frame.columns:
        raise RuntimeError(f"Series frame for {target_column} is missing required columns")

    working = frame[["Date", value_column]].copy()
    working = working.rename(columns={value_column: target_column})
    working["Date"] = pd.to_datetime(working["Date"], errors="coerce")
    working[target_column] = pd.to_numeric(working[target_column], errors="coerce")
    working = working.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    working = working[(working["Date"] >= start_date) & (working["Date"] <= end_date)].copy()
    if working.empty:
        raise RuntimeError(f"{target_column} returned no data for the requested range")
    return working.reset_index(drop=True)


def _resolve_macro_series_candidates(
    target_column: str,
    candidates,
    cached_frame: pd.DataFrame | None,
    *,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> tuple[pd.DataFrame, SourceHealth]:
    failures: list[str] = []

    for source_key, loader in candidates:
        try:
            frame = loader()
            if source_key.startswith("FRED:"):
                return frame, SourceHealth(status="healthy", missing_columns=(), reason="")
            reason = "; ".join(failures) if failures else f"{source_key} used"
            return frame, SourceHealth(
                status="fallback",
                missing_columns=(target_column,),
                reason=f"{reason}; fallback source={source_key} used",
            )
        except Exception as exc:
            failures.append(f"{source_key} unavailable: {exc}")

    if cached_frame is not None and target_column in cached_frame.columns:
        try:
            frame = _finalize_macro_series_frame(
                cached_frame[["Date", target_column]].copy(),
                value_column=target_column,
                target_column=target_column,
                start_date=start_date,
                end_date=end_date,
            )
            return frame, SourceHealth(
                status="fallback",
                missing_columns=(target_column,),
                reason=f"{'; '.join(failures)}; using cached canonical values",
            )
        except Exception as exc:
            failures.append(f"cached canonical values unavailable: {exc}")

    return _empty_source_frame([target_column]), SourceHealth(
        status="unavailable",
        missing_columns=(target_column,),
        reason="; ".join(failures) if failures else f"{target_column} unavailable",
    )


def _fill_short_forward_gaps(frame: pd.DataFrame, columns: tuple[str, ...], *, limit: int) -> pd.DataFrame:
    working = frame.copy().sort_values("Date").reset_index(drop=True)
    for column in columns:
        if column not in working.columns:
            continue
        working[column] = pd.to_numeric(working[column], errors="coerce").astype(float)
        working[column] = working[column].ffill(limit=limit)
    return working


def _apply_source_imputation(
    df: pd.DataFrame,
    *,
    source_frames: dict[str, pd.DataFrame],
    cached_frame: pd.DataFrame | None,
) -> pd.DataFrame:
    working = df.copy().sort_values("Date").reset_index(drop=True)

    for source_key, target_column, tolerance_days in FRED_IMPUTATION_SPECS:
        source_frame = source_frames.get(source_key)
        if source_frame is None or source_frame.empty:
            if cached_frame is None or target_column not in cached_frame.columns:
                continue
            source_frame = cached_frame[["Date", target_column]].copy()
        elif cached_frame is not None and target_column in cached_frame.columns:
            source_frame = pd.concat(
                [
                    source_frame[["Date", target_column]].copy(),
                    cached_frame[["Date", target_column]].copy(),
                ],
                ignore_index=True,
            )

        working[target_column] = _align_series_to_dates(
            working["Date"],
            source_frame,
            target_column,
            tolerance_days=tolerance_days,
        )

    working = _fill_short_forward_gaps(working, MARKET_IMPUTE_COLUMNS, limit=MARKET_SHORT_GAP_LIMIT)
    return working


def _empty_source_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=["Date", *columns])


def _get_fred_client():
    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return None

    cached_key = getattr(_get_fred_client, "_cached_key", None)
    cached_client = getattr(_get_fred_client, "_cached_client", None)
    if cached_key == api_key and cached_client is not None:
        return cached_client

    try:
        from fredapi import Fred
    except Exception:
        return None

    client = Fred(api_key=api_key)
    _get_fred_client._cached_key = api_key
    _get_fred_client._cached_client = client
    return client


def _download_fred_series(
    series_id: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    *,
    retries: int = FRED_RETRY_COUNT,
    timeout_seconds: int = FRED_TIMEOUT_SECONDS,
    backoff_seconds: float = FRED_BACKOFF_SECONDS,
) -> pd.DataFrame:
    fred_client = _get_fred_client()
    if fred_client is not None:
        try:
            series = fred_client.get_series(series_id, observation_start=start_date, observation_end=end_date)
            if series is None or len(series) == 0:
                raise RuntimeError(f"fredapi returned empty data for {series_id}")

            frame = series.to_frame(name=series_id).reset_index()
            date_column = frame.columns[0]
            value_column = frame.columns[1]
            frame = frame.rename(columns={date_column: "Date", value_column: series_id})
            frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
            frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
            frame = frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
            frame = frame[(frame["Date"] >= start_date) & (frame["Date"] <= end_date)].copy()
            if frame.empty:
                raise RuntimeError(f"fredapi returned empty data for {series_id}")
            return frame
        except Exception:
            pass

    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}&cosd={start_date:%Y-%m-%d}&coed={end_date:%Y-%m-%d}"
    )
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout_seconds)
            response.raise_for_status()
            csv_text = response.text
            frame = pd.read_csv(StringIO(csv_text))
            date_column = frame.columns[0]
            value_column = frame.columns[1]
            frame = frame.rename(columns={date_column: "Date", value_column: series_id})
            frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
            frame[series_id] = pd.to_numeric(frame[series_id], errors="coerce")
            frame = frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
            frame = frame[(frame["Date"] >= start_date) & (frame["Date"] <= end_date)].copy()
            if frame.empty:
                raise RuntimeError(f"FRED returned empty data for {series_id}")
            return frame
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_seconds * attempt)
                continue
            raise RuntimeError(f"FRED request failed for {series_id}: {exc}") from exc

    raise RuntimeError(f"FRED request failed for {series_id}") from last_error


def _fetch_fred_with_retry(series_list: list[str], start_date: pd.Timestamp, end_date: pd.Timestamp, retries: int = 2, backoff_factor: float = 1.0) -> pd.DataFrame:
    merged: pd.DataFrame | None = None
    last_error: Exception | None = None

    for series_id in series_list:
        for attempt in range(1, retries + 1):
            try:
                frame = _download_fred_series(series_id, start_date, end_date)
                merged = frame if merged is None else merged.merge(frame, on="Date", how="outer")
                break
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(backoff_factor * attempt)
                    continue
                raise RuntimeError("Không thể tải dữ liệu từ FRED") from exc

    if merged is None or merged.empty:
        raise RuntimeError("Không thể tải dữ liệu từ FRED") from last_error

    merged = merged.sort_values("Date").reset_index(drop=True)
    return merged


def _download_fed_h15_weekly_interest_series(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    response = requests.get(FED_H15_WEEKLY_INTEREST_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=FRED_TIMEOUT_SECONDS)
    response.raise_for_status()

    frame = pd.read_csv(StringIO(response.text))
    if "Series Description" not in frame.columns or FED_H15_WEEKLY_INTEREST_COLUMN not in frame.columns:
        raise RuntimeError("Fed H.15 weekly package is missing the expected interest-rate columns")

    date_mask = pd.to_datetime(frame["Series Description"], format="%Y-%m-%d", errors="coerce").notna()
    working = frame.loc[date_mask, ["Series Description", FED_H15_WEEKLY_INTEREST_COLUMN]].copy()
    working = working.rename(columns={"Series Description": "Date", FED_H15_WEEKLY_INTEREST_COLUMN: "Interest"})
    return _finalize_macro_series_frame(
        working,
        value_column="Interest",
        target_column="Interest",
        start_date=start_date,
        end_date=end_date,
    )


def _download_bls_cpi_series(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    response = requests.post(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json={
            "seriesid": [BLS_CPI_SERIES_ID],
            "startyear": str(start_date.year),
            "endyear": str(end_date.year),
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS request failed for {BLS_CPI_SERIES_ID}: {payload.get('message') or payload.get('status')}")

    series_list = payload.get("Results", {}).get("series", [])
    if not series_list:
        raise RuntimeError(f"BLS returned no series for {BLS_CPI_SERIES_ID}")

    rows: list[dict[str, object]] = []
    for item in series_list[0].get("data", []):
        period = str(item.get("period", ""))
        if not period.startswith("M"):
            continue
        try:
            year = int(item["year"])
            month = int(period[1:])
        except Exception:
            continue

        rows.append(
            {
                "Date": pd.Timestamp(year=year, month=month, day=1),
                "CPI": pd.to_numeric(item.get("value"), errors="coerce"),
            }
        )

    if not rows:
        raise RuntimeError(f"BLS returned no usable data for {BLS_CPI_SERIES_ID}")

    frame = pd.DataFrame(rows)
    return _finalize_macro_series_frame(
        frame,
        value_column="CPI",
        target_column="CPI",
        start_date=start_date,
        end_date=end_date,
    )


def _download_treasury_real_yield_series(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    collected_frames: list[pd.DataFrame] = []
    last_page_max_date: pd.Timestamp | None = None

    for page_number in range(TREASURY_REAL_YIELD_MAX_PAGES):
        response = requests.get(
            TREASURY_REAL_YIELD_PAGE_URL.format(page_number=page_number),
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=FRED_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        tables = pd.read_html(StringIO(response.text), flavor="lxml")
        if not tables:
            break

        table = tables[0]
        if "Date" not in table.columns or TREASURY_REAL_YIELD_COLUMN not in table.columns:
            break

        page_frame = table[["Date", TREASURY_REAL_YIELD_COLUMN]].copy()
        page_frame["Date"] = pd.to_datetime(page_frame["Date"], format="%m/%d/%Y", errors="coerce")
        page_frame[TREASURY_REAL_YIELD_COLUMN] = pd.to_numeric(page_frame[TREASURY_REAL_YIELD_COLUMN], errors="coerce")
        page_frame = page_frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

        if not page_frame.empty:
            page_frame = page_frame[(page_frame["Date"] >= start_date) & (page_frame["Date"] <= end_date)].copy()
            if not page_frame.empty:
                collected_frames.append(page_frame.rename(columns={TREASURY_REAL_YIELD_COLUMN: "Real_Yield_10Y"}))

        page_dates = pd.to_datetime(table["Date"], format="%m/%d/%Y", errors="coerce")
        page_max_date = page_dates.max()
        if pd.isna(page_max_date):
            break
        if last_page_max_date is not None and page_max_date <= last_page_max_date:
            break
        last_page_max_date = page_max_date
        if page_max_date >= end_date:
            break

    if not collected_frames:
        raise RuntimeError("Treasury real-yield page returned no usable data")

    frame = pd.concat(collected_frames, ignore_index=True)
    return _finalize_macro_series_frame(
        frame,
        value_column="Real_Yield_10Y",
        target_column="Real_Yield_10Y",
        start_date=start_date,
        end_date=end_date,
    )


def _download_yfinance_frame(ticker: str, start_date: pd.Timestamp, end_date: pd.Timestamp, columns: list[str], retries: int = 2, backoff_factor: float = 1.0) -> tuple[pd.DataFrame, list[str]]:
    start_text = start_date.strftime("%Y-%m-%d")
    end_text = (end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            frame = yf.download(
                ticker,
                start=start_text,
                end=end_text,
                progress=False,
                auto_adjust=False,
                threads=False,
            )
            if frame is None or getattr(frame, "empty", True):
                raise RuntimeError(f"yfinance returned empty data for {ticker}")

            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)

            frame = frame.reset_index()
            date_column = frame.columns[0]
            if date_column != "Date":
                frame = frame.rename(columns={date_column: "Date"})

            missing_columns = [column for column in columns if column not in frame.columns]
            for column in missing_columns:
                frame[column] = np.nan

            selected_columns = ["Date"] + columns
            frame = frame[selected_columns].copy()
            frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
            for column in columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")

            frame = frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
            return frame, missing_columns
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_factor * attempt)
                continue
            raise RuntimeError(f"Không thể tải dữ liệu từ yfinance cho {ticker}") from exc

    raise RuntimeError(f"Không thể tải dữ liệu từ yfinance cho {ticker}") from last_error


def _load_raw_gold_frame(csv_path: Path, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    frame = pd.read_csv(csv_path)
    date_column = None
    if "Date" in frame.columns:
        date_column = "Date"
    elif "Ngày" in frame.columns:
        date_column = "Ngày"

    if date_column is None:
        raise ValueError(f"No date column found in {csv_path}. Columns={list(frame.columns)}")

    frame[date_column] = pd.to_datetime(frame[date_column], dayfirst=True, errors="coerce")
    frame = frame.dropna(subset=[date_column]).copy()
    frame = frame.sort_values(date_column).drop_duplicates(subset=[date_column], keep="last")

    if "SJC" in frame.columns:
        sjc_column = "SJC"
    elif "SJC_gia_ban" in frame.columns:
        sjc_column = "SJC_gia_ban"
    elif "SJC_gia_mua" in frame.columns:
        sjc_column = "SJC_gia_mua"
    else:
        raise ValueError(f"Could not detect SJC price column in {csv_path}. Columns={list(frame.columns)}")

    raw = frame[[date_column, sjc_column]].copy()
    raw.columns = ["Date", "SJC"]
    raw["SJC"] = pd.to_numeric(raw["SJC"], errors="coerce")
    raw = raw.dropna(subset=["SJC"]).copy()
    raw = raw[(raw["Date"] >= start_date) & (raw["Date"] <= end_date)].copy()
    if raw.empty:
        raise RuntimeError("Raw SJC source returned no data for the requested range")
    return raw.reset_index(drop=True)


def _rename_market_columns(frame: pd.DataFrame, prefix: str, columns: list[str]) -> pd.DataFrame:
    renamed = {"Date": "Date"}
    for column in columns:
        renamed[column] = f"{prefix}_{column}"
    return frame.rename(columns=renamed)


def _write_csv_atomically(frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = output_path.with_name(f"{output_path.stem}.bak{output_path.suffix}")

    if output_path.exists() and output_path.stat().st_size > 0:
        try:
            shutil.copy2(output_path, backup_path)
        except Exception:
            pass

    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", delete=False, dir=str(output_path.parent), prefix=output_path.stem + ".tmp.", suffix=output_path.suffix) as handle:
        temp_path = Path(handle.name)
        frame.to_csv(handle, index=False)

    os.replace(temp_path, output_path)


def _merge_with_existing_output(frame: pd.DataFrame, output_path: Path) -> pd.DataFrame:
    if not output_path.exists() or output_path.stat().st_size <= 0:
        return frame.copy()

    try:
        existing = pd.read_csv(output_path)
    except Exception:
        return frame.copy()

    if "Date" not in existing.columns:
        return frame.copy()

    existing = existing.copy()
    existing["Date"] = pd.to_datetime(existing["Date"], errors="coerce")
    existing = existing.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

    new_frame = frame.copy()
    new_frame["Date"] = pd.to_datetime(new_frame["Date"], errors="coerce")
    new_frame = new_frame.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

    for column in FINAL_DATASET_COLUMNS:
        if column not in existing.columns:
            existing[column] = np.nan
        if column not in new_frame.columns:
            new_frame[column] = np.nan

    existing = existing[FINAL_DATASET_COLUMNS].copy().set_index("Date")
    new_frame = new_frame[FINAL_DATASET_COLUMNS].copy().set_index("Date")

    merged = new_frame.combine_first(existing)
    merged = merged.reset_index().sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    merged = merged[FINAL_DATASET_COLUMNS]
    numeric_columns = [column for column in FINAL_DATASET_COLUMNS if column != "Date"]
    merged[numeric_columns] = merged[numeric_columns].apply(pd.to_numeric, errors="coerce")
    return merged


def _build_backup_path(output_path: Path) -> Path:
    if output_path.name.endswith(".bak.csv"):
        return output_path
    return output_path.with_name(f"{output_path.stem}.bak{output_path.suffix}")


def _engineer_final_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("Date").reset_index(drop=True)

    df["Gold_world_vnd"] = (df["Gold_Close"] * OZ_PER_LUONG * df["USD_VND_Close"]) / 1_000_000.0
    df["SJC_Premium"] = df["SJC"] - df["Gold_world_vnd"]
    df["SJC_Premium_Percent"] = (df["SJC_Premium"] / df["Gold_world_vnd"]) * 100.0
    df["Shock_Index"] = (df["GVZ_Close"] * df["VIX_Close"]) / 100.0
    df["Gold_SP500_Ratio"] = df["Gold_Close"] / df["SP500_Close"]

    premium_pct_clean = pd.to_numeric(df["SJC_Premium_Percent"], errors="coerce")
    roll_mean = premium_pct_clean.rolling(window=30, min_periods=7).mean()
    roll_std = premium_pct_clean.rolling(window=30, min_periods=7).std().replace(0, np.nan)
    df["SJC_Premium_Zscore"] = (premium_pct_clean - roll_mean) / roll_std
    df["Policy_Risk_Zone"] = (df["SJC_Premium_Zscore"] > 2).astype(int)

    df["SJC_lag1"] = df["SJC"].shift(1)
    df["SJC_lag7"] = df["SJC"].shift(7)
    df["SJC_ma7"] = df["SJC"].rolling(7).mean()

    df["Gold_return"] = df["Gold_Close"].pct_change()
    df["Gold_volume_rank"] = df["Gold_Volume"].pct_change().replace([np.inf, -np.inf], np.nan)
    df["Gold_range"] = df["Gold_High"] - df["Gold_Low"]
    df["Gold_volatility_7"] = df["Gold_return"].rolling(7).std()
    df["Gold_momentum"] = df["Gold_Close"] - df["Gold_Close"].shift(7)
    df["Gold_Volume_Anomaly"] = df["Gold_Volume"] / df["Gold_Volume"].rolling(window=7, min_periods=1).mean()
    df["PVT"] = (df["Gold_return"] * df["Gold_Volume"]).fillna(0).cumsum()
    df["SP500_return"] = df["SP500_Close"].pct_change()
    df["VNIndex_ETF_return"] = df["VNIndex_ETF_Close"].pct_change()
    df["Bitcoin_return"] = df["Bitcoin_Close"].pct_change()

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna().copy()
    if df.empty:
        raise RuntimeError("Final dataset is empty after feature engineering")

    df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
    for column in FINAL_DATASET_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan

    df = df[FINAL_DATASET_COLUMNS]
    numeric_columns = [column for column in FINAL_DATASET_COLUMNS if column != "Date"]
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")
    return df


def _build_from_cached_dataset(
    *,
    raw_path: Path,
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    output_path: Path,
) -> Path:
    cached_path = Path(settings.LOCAL_DATASET_PATH)
    if not cached_path.exists():
        raise RuntimeError("Cached final_dataset.csv is not available for fallback")

    cached = pd.read_csv(cached_path)
    if "Date" not in cached.columns:
        raise RuntimeError(f"Cached dataset is missing Date column: {cached_path}")

    cached["Date"] = pd.to_datetime(cached["Date"], errors="coerce")
    cached = cached.dropna(subset=["Date"]).copy().sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

    raw = _load_raw_gold_frame(raw_path, start_ts, end_ts)
    all_days = pd.DataFrame({"Date": pd.date_range(start=start_ts, end=end_ts, freq="D")})
    df = all_days.merge(raw, on="Date", how="left")

    seed_columns = [column for column in MARKET_SEED_COLUMNS if column in cached.columns]
    if seed_columns:
        df = df.merge(cached[["Date", *seed_columns]], on="Date", how="left")

    if "SJC" in cached.columns:
        cached_sjc = cached[["Date", "SJC"]].rename(columns={"SJC": "SJC_cached"})
        df = df.merge(cached_sjc, on="Date", how="left")
        df["SJC"] = df["SJC"].combine_first(df["SJC_cached"])
        df = df.drop(columns=["SJC_cached"])

    return _engineer_final_features(df).pipe(lambda frame: _write_and_return(frame, output_path))


def _write_and_return(frame: pd.DataFrame, output_path: Path) -> Path:
    merged_frame = _merge_with_existing_output(frame, output_path)
    _write_csv_atomically(merged_frame, output_path)
    backup_path = _build_backup_path(output_path)
    if backup_path != output_path:
        _write_csv_atomically(merged_frame, backup_path)
    return output_path


def build_final_dataset(
    *,
    gold_csv_path: str | Path | None = None,
    output_csv_path: str | Path | None = None,
    start_date: date | datetime | str = DEFAULT_START_DATE,
    end_date: date | datetime | str | None = None,
) -> Path:
    output_path = Path(output_csv_path or settings.LOCAL_DATASET_PATH)
    raw_path = Path(gold_csv_path or RAW_GOLD_CSV)
    start_ts = _normalize_timestamp(start_date, default=DEFAULT_START_DATE)
    end_ts = _normalize_timestamp(end_date, default=pd.Timestamp.today().normalize())
    cached_frame = _load_cached_final_dataset_frame()
    log_entries: list[str] = []
    source_frames: dict[str, pd.DataFrame] = {}
    source_health: dict[str, SourceHealth] = {}

    print(f"Progress: 5% - Loading raw SJC source from {raw_path}")

    try:
        sjc = _load_raw_gold_frame(raw_path, start_ts, end_ts)
    except Exception as exc:
        source_health["RAW_SJC"] = SourceHealth(
            status="unavailable",
            missing_columns=("SJC",),
            reason=f"RAW_SJC unavailable: {exc}",
        )
        log_entries.extend(_build_preflight_entries(source_health, start_ts=start_ts, end_ts=end_ts))
        log_entries.append(_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], "Build aborted before merge because raw SJC source could not be loaded."))
        _append_missing_data_log(log_entries, start_ts=start_ts, end_ts=end_ts)
        print(f"Missing-column log: {FINAL_DATASET_MISSING_LOG_PATH}")
        raise

    source_frames["RAW_SJC"] = sjc.copy()
    df = sjc.copy()
    print(f"Progress: 15% - Raw SJC source loaded ({len(df)} rows)")

    macro_frames: list[pd.DataFrame] = []
    macro_source_candidates = (
        (
            "FRED:FEDFUNDS",
            "Interest",
            (
                (
                    "FRED:FEDFUNDS",
                    lambda: _finalize_macro_series_frame(
                        _download_fred_series("FEDFUNDS", start_ts, end_ts, retries=1, timeout_seconds=30),
                        value_column="FEDFUNDS",
                        target_column="Interest",
                        start_date=start_ts,
                        end_date=end_ts,
                    ),
                ),
                ("FED:H15_WEEKLY", lambda: _download_fed_h15_weekly_interest_series(start_ts, end_ts)),
            ),
        ),
        (
            "FRED:CPIAUCSL",
            "CPI",
            (
                (
                    "FRED:CPIAUCSL",
                    lambda: _finalize_macro_series_frame(
                        _download_fred_series("CPIAUCSL", start_ts, end_ts, retries=1, timeout_seconds=30),
                        value_column="CPIAUCSL",
                        target_column="CPI",
                        start_date=start_ts,
                        end_date=end_ts,
                    ),
                ),
                ("BLS:CUSR0000SA0", lambda: _download_bls_cpi_series(start_ts, end_ts)),
            ),
        ),
        (
            "FRED:DFII10",
            "Real_Yield_10Y",
            (
                (
                    "FRED:DFII10",
                    lambda: _finalize_macro_series_frame(
                        _download_fred_series("DFII10", start_ts, end_ts, retries=1, timeout_seconds=30),
                        value_column="DFII10",
                        target_column="Real_Yield_10Y",
                        start_date=start_ts,
                        end_date=end_ts,
                    ),
                ),
                ("TREASURY:REAL_YIELD_10Y", lambda: _download_treasury_real_yield_series(start_ts, end_ts)),
            ),
        ),
    )

    print("Progress: 25% - Resolving macro series")

    for index, (source_key, target_column, candidates) in enumerate(macro_source_candidates, start=1):
        frame, health = _resolve_macro_series_candidates(
            target_column,
            candidates,
            cached_frame,
            start_date=start_ts,
            end_date=end_ts,
        )
        source_frames[source_key] = frame.copy()
        source_health[source_key] = health
        macro_frames.append(frame)
        print(f"Progress: {25 + index * 10}% - {target_column} series resolved")

    fred = macro_frames[0]
    for frame in macro_frames[1:]:
        fred = fred.merge(frame, on="Date", how="outer")

    print("Progress: 55% - Resolving market series")
    market_frames: list[pd.DataFrame] = []
    for index, (ticker, prefix, columns) in enumerate(YFINANCE_SERIES, start=1):
        source_key = f"YFINANCE:{ticker}"
        try:
            frame, missing_columns = _download_yfinance_frame(ticker, start_ts, end_ts, columns)
            if missing_columns:
                source_health[source_key] = SourceHealth(
                    status="partial",
                    missing_columns=tuple(missing_columns),
                    reason=f"{source_key} missing columns: {', '.join(missing_columns)}",
                )
        except Exception as exc:
            source_health[source_key] = SourceHealth(
                status="unavailable",
                missing_columns=tuple(columns),
                reason=f"{source_key} unavailable: {exc}",
            )
            frame = _empty_source_frame(columns)
        renamed_frame = _rename_market_columns(frame, prefix, columns)
        source_frames[source_key] = renamed_frame.copy()
        market_frames.append(renamed_frame)
        if index in {3, 6, 9}:
            print(f"Progress: {55 + index * 2}% - {ticker} market series prepared")

    for market_frame in market_frames:
        df = df.merge(market_frame, on="Date", how="left")

    df = df.merge(fred, on="Date", how="left")
    df = df.sort_values("Date").reset_index(drop=True)
    df = _apply_source_imputation(df, source_frames=source_frames, cached_frame=cached_frame)
    print(f"Progress: 78% - Source imputation complete ({len(df)} rows)")

    preflight_entries = _build_preflight_entries(source_health, start_ts=start_ts, end_ts=end_ts)
    if preflight_entries:
        print(f"Preflight source-health issues: {len(preflight_entries)}")
    log_entries.extend(preflight_entries)

    base_missing = df[SOURCE_DATA_COLUMNS].isna()
    base_missing_counts = base_missing.sum().sort_values(ascending=False)
    skipped_base_rows = int(base_missing.any(axis=1).sum())
    grouped_missing_counts: dict[str, list[tuple[str, int]]] = {}
    for column_name, missing_count in base_missing_counts.items():
        if int(missing_count) > 0:
            source = SOURCE_BY_COLUMN[column_name]
            grouped_missing_counts.setdefault(source, []).append((column_name, int(missing_count)))
    for source, column_counts in grouped_missing_counts.items():
        log_entries.append(
            _format_log_entry(
                SUMMARY_LOG_DATE,
                source,
                [column for column, _ in column_counts],
                {column: f"{count} rows missing before strict drop" for column, count in column_counts},
            )
        )
    if skipped_base_rows > 0:
        log_entries.extend(
            _build_row_issue_entries(
                df,
                source_frames=source_frames,
                source_health=source_health,
            )
        )
        log_entries.append(
            _format_log_entry(
                SUMMARY_LOG_DATE,
                "ALL",
                [],
                f"Skipped {skipped_base_rows} rows with incomplete source columns.",
            )
        )

    df = df.loc[~base_missing.any(axis=1)].copy()
    if df.empty:
        log_entries.append(_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], "No complete rows remained after source filtering."))
        _append_missing_data_log(log_entries, start_ts=start_ts, end_ts=end_ts)
        print(f"Missing-column log: {FINAL_DATASET_MISSING_LOG_PATH}")
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"Strict build produced no rows; preserved existing file: {output_path}")
            return output_path
        empty_out = pd.DataFrame(columns=FINAL_DATASET_COLUMNS)
        _write_csv_atomically(empty_out, output_path)
        return output_path

    try:
        engineered = _engineer_final_features(df)
    except RuntimeError as exc:
        if "Final dataset is empty after feature engineering" not in str(exc):
            raise
        log_entries.append(_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], "No complete rows remained after feature engineering."))
        _append_missing_data_log(log_entries, start_ts=start_ts, end_ts=end_ts)
        print(f"Missing-column log: {FINAL_DATASET_MISSING_LOG_PATH}")
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"Strict build produced no rows; preserved existing file: {output_path}")
            return output_path
        empty_out = pd.DataFrame(columns=FINAL_DATASET_COLUMNS)
        _write_csv_atomically(empty_out, output_path)
        return output_path
    skipped_warmup_rows = int(len(df) - len(engineered))
    if skipped_warmup_rows > 0:
        log_entries.append(
            _format_log_entry(
                SUMMARY_LOG_DATE,
                "ALL",
                [],
                f"Skipped {skipped_warmup_rows} rows during feature warm-up / rolling-window cleanup.",
            )
        )

    if engineered.empty:
        log_entries.append(_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], "No complete rows remained after feature engineering."))
        _append_missing_data_log(log_entries, start_ts=start_ts, end_ts=end_ts)
        print(f"Missing-column log: {FINAL_DATASET_MISSING_LOG_PATH}")
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"Strict build produced no rows; preserved existing file: {output_path}")
            return output_path
        empty_out = pd.DataFrame(columns=FINAL_DATASET_COLUMNS)
        _write_csv_atomically(empty_out, output_path)
        return output_path

    print(f"Progress: 90% - Feature engineering produced {len(engineered)} rows")
    _write_and_return(engineered, output_path)
    log_entries.append(_format_log_entry(SUMMARY_LOG_DATE, "ALL", [], f"Wrote {len(engineered)} complete rows to {output_path}"))
    _append_missing_data_log(log_entries, start_ts=start_ts, end_ts=end_ts)
    print(f"Missing-column log: {FINAL_DATASET_MISSING_LOG_PATH}")
    print(f"Progress: 100% - Final dataset written to {output_path}")
    return output_path
