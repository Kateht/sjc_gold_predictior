from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


OZ_PER_LUONG = 37.5 / 31.1034768
VND_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class MergePaths:
    root_dir: Path
    gold_csv: Path
    xauusd_cache_csv: Path
    usd_vnd_cache_csv: Path
    final_uso_csv: Path
    vn_gold_usd_oz_csv: Path
    final_uso_usd_with_vn_gold_usd_oz_csv: Path
    final_uso_usd_with_vn_gold_usd_oz_imputed_csv: Path
    final_uso_with_vn_gold_vnd_thousand_imputed_csv: Path


def _parse_gold_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "Ngày" not in df.columns:
        raise ValueError(f"Missing 'Ngày' in {path}. Columns={list(df.columns)}")

    df["Ngày"] = pd.to_datetime(df["Ngày"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Ngày"]).copy()
    for col in df.columns:
        if col == "Ngày":
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("Ngày").drop_duplicates(subset=["Ngày"], keep="last")
    return df


def _load_xauusd_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["Date", "XAUUSD_Open", "XAUUSD_High", "XAUUSD_Low", "XAUUSD_Close"])

    df = pd.read_csv(path)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' in {path}. Columns={list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy()
    df = df.drop_duplicates(subset=["Date"], keep="last")
    wanted = ["Date", "Open", "High", "Low", "Close"]
    missing = [c for c in wanted if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in {path}: {missing}")

    df = df[wanted].copy()
    df = df.rename(
        columns={
            "Date": "Date",
            "Open": "XAUUSD_Open",
            "High": "XAUUSD_High",
            "Low": "XAUUSD_Low",
            "Close": "XAUUSD_Close",
        }
    )
    for col in ["XAUUSD_Open", "XAUUSD_High", "XAUUSD_Low", "XAUUSD_Close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("Date")


def _download_usdvnd_close_yfinance(start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    try:
        import yfinance as yf
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Missing dependency 'yfinance'. Install it and retry.") from exc

    y_start = start.strftime("%Y-%m-%d")
    y_end = (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    fx = yf.download("VND=X", start=y_start, end=y_end, auto_adjust=False, progress=False)
    if fx is None or getattr(fx, "empty", True):
        raise RuntimeError("yfinance returned empty FX data for VND=X")

    if isinstance(fx.columns, pd.MultiIndex):
        close_df = fx["Close"]
        if isinstance(close_df, pd.DataFrame):
            if "VND=X" in close_df.columns:
                close = close_df["VND=X"].copy()
            else:
                close = close_df.iloc[:, 0].copy()
        else:
            close = close_df.copy()
    else:
        close = fx["Close"].copy()

    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    close = close[~close.index.duplicated(keep="last")]
    close.name = "USDVND_Close"
    return close


def _normalize_usdvnd_close_to_vnd_per_usd(close: pd.Series) -> pd.Series:
    s = pd.to_numeric(close, errors="coerce").astype(float)
    s = s.where(s > 0)
    inv_mask = s.notna() & (s < 1)
    if inv_mask.any():
        s.loc[inv_mask] = 1.0 / s.loc[inv_mask]
    s = s.where(s.between(10_000, 100_000))
    return s


def _load_or_fetch_usdvnd_close(paths: MergePaths, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    if paths.usd_vnd_cache_csv.exists():
        cached = pd.read_csv(paths.usd_vnd_cache_csv, parse_dates=["Date"])
        if {"Date", "USDVND_Close"}.issubset(cached.columns):
            cached = cached.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
            series = cached.set_index("Date")["USDVND_Close"]
            series = _normalize_usdvnd_close_to_vnd_per_usd(series)
            if series.index.min() <= start and series.index.max() >= end:
                out = series.reset_index()
                out.to_csv(paths.usd_vnd_cache_csv, index=False)
                return series

    series = _download_usdvnd_close_yfinance(start, end)
    series = _normalize_usdvnd_close_to_vnd_per_usd(series)
    out = series.reset_index().rename(columns={"index": "Date"})
    paths.usd_vnd_cache_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(paths.usd_vnd_cache_csv, index=False)
    return series


def _safe_impute_series_time(s: pd.Series, max_gap_days: int = 3) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").astype(float)
    first = s.first_valid_index()
    last = s.last_valid_index()
    if first is None or last is None:
        return s

    window = s.loc[first:last].copy()
    if window.isna().any():
        is_nan = window.isna()
        grp = (is_nan != is_nan.shift(fill_value=False)).cumsum()
        run_len = is_nan.groupby(grp).transform("sum")
        fill_mask = is_nan & (run_len <= max_gap_days)
        if fill_mask.any():
            interp = window.interpolate(method="time")
            window.loc[fill_mask] = interp.loc[fill_mask]
    s.loc[first:last] = window
    return s


def build_vn_gold_usd_oz(paths: MergePaths) -> Path:
    gold = _parse_gold_csv(paths.gold_csv)
    start = pd.Timestamp(gold["Ngày"].min()).normalize()
    end = pd.Timestamp(gold["Ngày"].max()).normalize()
    full_days = pd.date_range(start, end, freq="D")

    out = gold.set_index("Ngày").reindex(full_days)
    out.index.name = "Ngày"

    xau = _load_xauusd_cache(paths.xauusd_cache_csv)
    if not xau.empty:
        xau = xau.set_index("Date").reindex(full_days).ffill().bfill()
        for col in ["XAUUSD_Open", "XAUUSD_High", "XAUUSD_Low", "XAUUSD_Close"]:
            out[col] = xau[col]

    fx = _load_or_fetch_usdvnd_close(paths, start, end).reindex(full_days).ffill().bfill()

    gold_cols = [c for c in out.columns if c != "Ngày" and not c.startswith("XAUUSD_")]
    for col in gold_cols:
        out[col] = (out[col] * VND_PER_MILLION) / fx / OZ_PER_LUONG
        out[col] = _safe_impute_series_time(out[col], max_gap_days=3)

    out = out.reset_index()
    out["Ngày"] = pd.to_datetime(out["Ngày"]).dt.strftime("%Y-%m-%d")
    ordered_cols = ["Ngày"] + [c for c in gold.columns if c != "Ngày"] + [c for c in ["XAUUSD_Open", "XAUUSD_High", "XAUUSD_Low", "XAUUSD_Close"] if c in out.columns]
    out = out[[c for c in ordered_cols if c in out.columns]]
    out.to_csv(paths.vn_gold_usd_oz_csv, index=False)
    return paths.vn_gold_usd_oz_csv


def build_final_uso_usd_with_vn_gold_usd_oz(paths: MergePaths) -> Path:
    uso = pd.read_csv(paths.final_uso_csv)
    if "Date" not in uso.columns:
        raise ValueError(f"Missing 'Date' in {paths.final_uso_csv}. Columns={list(uso.columns)}")
    uso["Date"] = pd.to_datetime(uso["Date"], errors="coerce")
    uso = uso.dropna(subset=["Date"]).copy()
    for col in uso.columns:
        if col != "Date":
            uso[col] = pd.to_numeric(uso[col], errors="coerce")
    uso = uso.sort_values("Date").drop_duplicates(subset=["Date"], keep="last")

    gold = pd.read_csv(paths.vn_gold_usd_oz_csv)
    if "Ngày" not in gold.columns:
        raise ValueError(f"Missing 'Ngày' in {paths.vn_gold_usd_oz_csv}. Columns={list(gold.columns)}")
    gold["Ngày"] = pd.to_datetime(gold["Ngày"], errors="coerce")
    gold = gold.dropna(subset=["Ngày"]).copy().sort_values("Ngày").drop_duplicates(subset=["Ngày"], keep="last")
    gold = gold.rename(columns={"Ngày": "Date"})

    merged = uso.merge(gold, on="Date", how="left")

    if paths.xauusd_cache_csv.exists():
        xau = _load_xauusd_cache(paths.xauusd_cache_csv)
        xau = xau.rename(columns={"Date": "Date"})
        merged = merged.merge(xau, on="Date", how="left", suffixes=("", "_stooq"))
        for col in ["XAUUSD_Open", "XAUUSD_High", "XAUUSD_Low", "XAUUSD_Close"]:
            stooq_col = f"{col}_stooq"
            if stooq_col in merged.columns:
                merged[col] = merged[col].combine_first(merged[stooq_col]) if col in merged.columns else merged[stooq_col]
                merged = merged.drop(columns=[stooq_col])

    merged = merged.sort_values("Date")
    merged["Date"] = pd.to_datetime(merged["Date"]).dt.strftime("%Y-%m-%d")
    merged.to_csv(paths.final_uso_usd_with_vn_gold_usd_oz_csv, index=False)
    return paths.final_uso_usd_with_vn_gold_usd_oz_csv


def build_final_uso_usd_with_vn_gold_usd_oz_imputed(paths: MergePaths) -> Path:
    df = pd.read_csv(paths.final_uso_usd_with_vn_gold_usd_oz_csv)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' in {paths.final_uso_usd_with_vn_gold_usd_oz_csv}. Columns={list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy().sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    for col in df.columns:
        if col != "Date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.set_index("Date")
    for col in df.columns:
        df[col] = _safe_impute_series_time(df[col], max_gap_days=3)

    out = df.reset_index()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(paths.final_uso_usd_with_vn_gold_usd_oz_imputed_csv, index=False)
    return paths.final_uso_usd_with_vn_gold_usd_oz_imputed_csv


def build_final_uso_with_vn_gold_vnd_thousand_imputed(paths: MergePaths) -> Path:
    df = pd.read_csv(paths.final_uso_usd_with_vn_gold_usd_oz_imputed_csv)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' in {paths.final_uso_usd_with_vn_gold_usd_oz_imputed_csv}. Columns={list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy().sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
    for col in df.columns:
        if col != "Date":
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.set_index("Date")
    start = pd.Timestamp(df.index.min()).normalize()
    end = pd.Timestamp(df.index.max()).normalize()
    fx = _load_or_fetch_usdvnd_close(paths, start, end).reindex(df.index).ffill().bfill()

    gold_cols = {
        "PNJ_gia_mua",
        "PNJ_gia_ban",
        "SJC_gia_mua",
        "SJC_gia_ban",
        "XAUUSD_Open",
        "XAUUSD_High",
        "XAUUSD_Low",
        "XAUUSD_Close",
    }

    def _is_volume_col(col: str) -> bool:
        return "volume" in col.lower()

    for col in df.columns:
        if _is_volume_col(col):
            continue
        if col in gold_cols:
            df[col] = (df[col] * fx * OZ_PER_LUONG) / 1000.0
        else:
            df[col] = (df[col] * fx) / 1000.0

    out = df.reset_index()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    out.to_csv(paths.final_uso_with_vn_gold_vnd_thousand_imputed_csv, index=False)
    return paths.final_uso_with_vn_gold_vnd_thousand_imputed_csv


def build_all(paths: MergePaths) -> list[Path]:
    outputs = [
        Path(build_vn_gold_usd_oz(paths)),
        Path(build_final_uso_usd_with_vn_gold_usd_oz(paths)),
        Path(build_final_uso_usd_with_vn_gold_usd_oz_imputed(paths)),
        Path(build_final_uso_with_vn_gold_vnd_thousand_imputed(paths)),
    ]
    return outputs
