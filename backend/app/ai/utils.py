from __future__ import annotations

from datetime import datetime
from pathlib import Path
import math
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf

from app.core.config import settings


SOURCE_ALIASES = {
    "sjc": "sjc",
    "local": "sjc",
    "dataset": "sjc",
    "gold": "sjc",
    "world": "world",
    "gc=f": "world",
    "gc": "world",
}


def normalize_source(source: str | None) -> str:
    key = (source or "sjc").strip().lower()
    return SOURCE_ALIASES.get(key, key)


def _synthetic_history(days: int = 180, start_price: float = 80.0) -> pd.DataFrame:
    end_date = pd.Timestamp.utcnow().normalize()
    dates = pd.date_range(end=end_date, periods=days, freq="D")
    prices: list[float] = []
    for index in range(days):
        seasonal = math.sin(index / 9.0) * 0.45
        drift = index * 0.02
        value = start_price + drift + seasonal
        prices.append(round(float(value), 4))
    return pd.DataFrame({"date": dates, "price": prices})


def _detect_date_column(frame: pd.DataFrame) -> str | None:
    candidates = ["date", "Date", "datetime", "Datetime", "time", "Time"]
    lower_map = {column.lower(): column for column in frame.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


def _detect_price_column(frame: pd.DataFrame) -> str | None:
    preferred = ["sjc", "price", "close", "adj close", "value", "gold", "giavang"]
    lower_map = {column.lower(): column for column in frame.columns}
    for candidate in preferred:
        if candidate in lower_map:
            return lower_map[candidate]

    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column]):
            return column
    return None


def _coerce_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    date_column = _detect_date_column(working)
    if date_column is None and working.index.name is not None:
        working = working.reset_index()
        date_column = _detect_date_column(working) or working.columns[0]

    price_column = _detect_price_column(working)
    if price_column is None:
        raise ValueError("Could not detect a usable price column")

    if date_column is None:
        working = working.reset_index(drop=True)
        working["date"] = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=len(working), freq="D")
        date_column = "date"

    result = working[[date_column, price_column]].copy()
    result.columns = ["date", "price"]
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["price"] = pd.to_numeric(result["price"], errors="coerce")
    result = result.dropna().sort_values("date").reset_index(drop=True)
    if result.empty:
        raise ValueError("History frame is empty after cleaning")
    return result


def _read_csv_history(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)

def load_and_preprocess_data1(csv_path: str):
    import pandas as pd
    import numpy as np
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    csv_path = BASE_DIR / "dataset" / "final_dataset.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))
        
    # 1. Đọc Raw Data
    df_raw = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    if 'Unnamed: 0' in df_raw.columns:
        df_raw.drop(columns=['Unnamed: 0'], inplace=True)
        
    # 2. Tính Ma trận sai phân (Vì Engine của bạn dùng df_diff)
    df_diff = df_raw.diff().dropna()
    df_diff.replace([np.inf, -np.inf], np.nan, inplace=True)
    df_diff.fillna(0, inplace=True)
    
    # 3. Lấy giá chốt sổ
    last_price = df_raw['SJC'].iloc[-1] if 'SJC' in df_raw.columns else 0
    
    # Trả về ĐÚNG 2 BỘ DỮ LIỆU mà __init__ đang cần
    return df_diff, last_price
def load_and_preprocess_data_for_gemini(csv_path: str):
    import pandas as pd
    import numpy as np
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    candidate_paths = []
    if csv_path:
        requested_path = Path(csv_path)
        candidate_paths.append(requested_path if requested_path.is_absolute() else (BASE_DIR / requested_path))
    candidate_paths.extend(
        [
            BASE_DIR / "dataset" / "final_dataset_new.csv",
            BASE_DIR / "dataset" / "final_dataset.csv",
            Path(settings.LOCAL_DATASET_PATH),
            Path(settings.CRAWLER_DATASET_PATH),
        ]
    )

    actual_path = next((path for path in candidate_paths if path.exists()), None)
    if actual_path is None:
        tried_paths = ", ".join(str(path) for path in candidate_paths)
        raise FileNotFoundError(f"Không tìm thấy file dataset phù hợp. Đã thử: {tried_paths}")
        
    # Đọc dữ liệu gốc
    df_raw = pd.read_csv(actual_path, index_col=0, parse_dates=True)
    if 'Unnamed: 0' in df_raw.columns:
        df_raw.drop(columns=['Unnamed: 0'], inplace=True)
        
    # Tính sai phân
    df_diff = df_raw.diff().dropna()
    df_diff.replace([np.inf, -np.inf], np.nan, inplace=True)
    df_diff.fillna(0, inplace=True)
    
    # Lấy giá cuối
    last_price = df_raw['SJC'].iloc[-1] if 'SJC' in df_raw.columns else 0
    
    # TRẢ VỀ ĐỦ 3 BIẾN CHO GEMINI
    return df_raw, df_diff, last_price

def _read_csv_history(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    attempts = (
        {"index_col": 0, "parse_dates": True},
        {"parse_dates": [0]},
        {},
    )
    last_error: Exception | None = None
    for read_kwargs in attempts:
        try:
            frame = pd.read_csv(csv_path, **read_kwargs)
            return _coerce_history_frame(frame)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Could not load history CSV from {csv_path}") from last_error


def _coerce_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    if "Unnamed: 0" in working.columns:
        working = working.drop(columns=["Unnamed: 0"])

    date_column = _detect_date_column(working)
    if date_column is None and not isinstance(working.index, pd.RangeIndex):
        working = working.reset_index()
        date_column = _detect_date_column(working) or working.columns[0]

    if date_column is None:
        working = working.reset_index(drop=True)
        working["date"] = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=len(working), freq="D")
        date_column = "date"

    if date_column != "date":
        working = working.rename(columns={date_column: "date"})

    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    if working.empty:
        raise ValueError("Feature frame is empty after cleaning")
    return working


def _ensure_trend_feature_columns(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()

    if "SJC_Premium" not in working.columns and {"SJC", "Gold_world_vnd"}.issubset(working.columns):
        sjc_price = pd.to_numeric(working["SJC"], errors="coerce")
        world_price = pd.to_numeric(working["Gold_world_vnd"], errors="coerce")
        working["SJC_Premium"] = sjc_price - world_price

    if "SJC_Premium_Zscore" not in working.columns:
        if "SJC_Premium" in working.columns:
            premium = pd.to_numeric(working["SJC_Premium"], errors="coerce")
        else:
            premium = pd.Series(0.0, index=working.index)

        rolling_mean = premium.rolling(window=30, min_periods=5).mean()
        rolling_std = premium.rolling(window=30, min_periods=5).std(ddof=0).replace(0, np.nan)
        zscore = (premium - rolling_mean) / rolling_std
        working["SJC_Premium_Zscore"] = zscore.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if "Policy_Risk_Zone" not in working.columns:
        risk_source = None
        for candidate_column in ("Shock_Index", "VIX_Close", "CPI"):
            if candidate_column in working.columns:
                risk_source = pd.to_numeric(working[candidate_column], errors="coerce").fillna(0.0)
                break

        if risk_source is None or risk_source.nunique(dropna=True) < 3:
            working["Policy_Risk_Zone"] = 0.0
        else:
            ranked = risk_source.rank(method="first")
            working["Policy_Risk_Zone"] = pd.qcut(ranked, q=3, labels=False, duplicates="drop").astype(float)

    return working


def _read_feature_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(str(csv_path))

    attempts = (
        {"index_col": 0, "parse_dates": True},
        {"parse_dates": [0]},
        {},
    )
    last_error: Exception | None = None
    for read_kwargs in attempts:
        try:
            frame = pd.read_csv(csv_path, **read_kwargs)
            return _coerce_feature_frame(frame)
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Could not load feature CSV from {csv_path}") from last_error


def _feature_dataset_candidates(csv_path: str | Path | None = None) -> list[Path]:
    base_dir = Path(__file__).resolve().parents[2]
    candidates: list[Path] = []
    if csv_path:
        candidate = Path(csv_path).expanduser()
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        candidates.append(candidate)

    candidates.extend(
        [
            (base_dir / "dataset" / "final_dataset.csv").resolve(),
            (base_dir / "dataset" / "final_dataset_new.csv").resolve(),
            Path(settings.LOCAL_DATASET_PATH),
            Path(settings.CRAWLER_DATASET_PATH),
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        deduped.append(candidate)
        seen.add(key)
    return deduped


def load_feature_dataset_frame(csv_path: str | Path | None = None, required_columns: Iterable[str] | None = None) -> pd.DataFrame:
    required = set(required_columns or [])
    last_error: Exception | None = None

    for candidate in _feature_dataset_candidates(csv_path):
        try:
            frame = _read_feature_csv(candidate)
        except Exception as exc:
            last_error = exc
            continue

        frame = _ensure_trend_feature_columns(frame)

        if required and not required.issubset(set(frame.columns)):
            last_error = ValueError(f"Missing required feature columns in {candidate}")
            continue
        return frame

    raise FileNotFoundError("No usable feature dataset CSV was found") from last_error


def load_feature_prediction_data(csv_path: str | Path | None = None, required_columns: Iterable[str] | None = None):
    frame = load_feature_dataset_frame(csv_path=csv_path, required_columns=required_columns)
    if "SJC" not in frame.columns:
        raise ValueError("Feature dataset must contain an SJC column")

    numeric_columns = [column for column in frame.columns if column != "date"]
    working = frame.copy()
    working[numeric_columns] = working[numeric_columns].apply(pd.to_numeric, errors="coerce")
    working = working.dropna(subset=["SJC"]).sort_values("date").reset_index(drop=True)
    working[numeric_columns] = working[numeric_columns].ffill().bfill().fillna(0.0)

    last_price = float(working["SJC"].iloc[-1])
    df_diff = working[numeric_columns].diff().dropna().reset_index(drop=True)
    df_diff = df_diff.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df_diff, last_price, working


def load_and_preprocess_data1(csv_path: str):
    df_diff, last_price, _ = load_feature_prediction_data(csv_path=csv_path)
    return df_diff, last_price


def _fetch_world_history(period: str = "2y") -> pd.DataFrame:
    ticker = yf.Ticker("GC=F")
    history = ticker.history(period=period)
    if history.empty:
        raise ValueError("No world gold data returned by yfinance")
    frame = history.reset_index()
    if "Date" not in frame.columns:
        frame = frame.rename(columns={frame.columns[0]: "Date"})
    return _coerce_history_frame(frame[["Date", "Close"]])


def load_price_history_frame(source: str = "sjc") -> pd.DataFrame:
    normalized = normalize_source(source)
    if normalized == "world":
        try:
            return _fetch_world_history()
        except Exception:
            return _synthetic_history()

    candidate_paths = [settings.LOCAL_DATASET_PATH, settings.CRAWLER_DATASET_PATH]
    for candidate in candidate_paths:
        try:
            frame = _read_csv_history(candidate)
            if not frame.empty:
                return frame
        except Exception:
            continue

    try:
        return _fetch_world_history()
    except Exception:
        return _synthetic_history()


def _resolve_history_window_days(range_value: str | None) -> int | None:
    normalized = (range_value or "30d").strip().lower()
    if normalized in {"all", "max", "full"}:
        return None

    digits = "".join(character for character in normalized if character.isdigit())
    if not digits:
        return 30

    amount = max(1, int(digits))
    if normalized.endswith("y"):
        return amount * 365
    if normalized.endswith("m"):
        return amount * 30
    return amount


def limit_history_frame(frame: pd.DataFrame, range_value: str | None) -> pd.DataFrame:
    if frame.empty:
        return frame

    days = _resolve_history_window_days(range_value)
    if days is None:
        return frame.reset_index(drop=True)
    return frame.tail(days).reset_index(drop=True)


def build_future_dates(last_date: pd.Timestamp | datetime | str, days: int) -> list[str]:
    base_date = pd.to_datetime(last_date, errors="coerce")
    if pd.isna(base_date):
        base_date = pd.Timestamp.utcnow().normalize()

    future_dates = pd.date_range(start=base_date + pd.Timedelta(days=1), periods=days, freq="D")
    return [date.strftime("%Y-%m-%d") for date in future_dates]


def build_recent_prices_from_diffs(df_diff: pd.DataFrame | pd.Series | Iterable[float], last_actual_price: float, window: int = 30) -> list[float]:
    if isinstance(df_diff, pd.DataFrame):
        candidate_columns = ["SJC", "price", "Close", "close"]
        diff_series = None
        for column in candidate_columns:
            if column in df_diff.columns:
                diff_series = pd.to_numeric(df_diff[column], errors="coerce").dropna().tolist()
                break
        if diff_series is None:
            numeric_columns = [column for column in df_diff.columns if pd.api.types.is_numeric_dtype(df_diff[column])]
            if not numeric_columns:
                return [float(last_actual_price)]
            diff_series = pd.to_numeric(df_diff[numeric_columns[0]], errors="coerce").dropna().tolist()
    elif isinstance(df_diff, pd.Series):
        diff_series = pd.to_numeric(df_diff, errors="coerce").dropna().tolist()
    else:
        diff_series = [float(value) for value in df_diff]

    diffs = diff_series[-window:]
    history = [float(last_actual_price)]
    for delta in reversed(diffs):
        history.append(float(history[-1] - float(delta)))
    history.reverse()
    return history


def load_and_preprocess_data(csv_path: str | None = None):
    frame: pd.DataFrame | None = None
    if csv_path:
        try:
            frame = _read_csv_history(csv_path)
        except Exception:
            frame = None

    if frame is None:
        frame = load_price_history_frame("sjc")

    frame = frame.sort_values("date").reset_index(drop=True)
    frame = frame.rename(columns={"price": "SJC"})
    frame["SJC"] = pd.to_numeric(frame["SJC"], errors="coerce")
    frame = frame.dropna().reset_index(drop=True)
    last_actual_price = float(frame["SJC"].iloc[-1])
    df_diff = frame[["date", "SJC"]].copy()
    df_diff["SJC"] = df_diff["SJC"].diff().fillna(0.0)
    df_diff = df_diff.dropna().reset_index(drop=True)
    return df_diff, last_actual_price
