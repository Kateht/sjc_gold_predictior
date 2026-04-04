import csv
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd
import requests


SESSION = requests.Session()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_CSV_PATH = os.path.join(BASE_DIR, "final_uso_usd.csv")
CACHE_DIR = os.path.join(BASE_DIR, "stooq_cache")
RHO_METALARY_URL = "https://www.metalary.com/rhodium-price/"
RHO_CACHE_PATH = os.path.join(CACHE_DIR, "rhodium_metalary.html")


REQUIRED_COLUMNS = [
    "Date",
    "Open",
    "High",
    "Low",
    "Close",
    "Adj Close",
    "Volume",
    "SP_open",
    "SP_high",
    "SP_low",
    "SP_close",
    "SP_Ajclose",
    "SP_volume",
    "DJ_open",
    "DJ_high",
    "DJ_low",
    "DJ_close",
    "DJ_Ajclose",
    "DJ_volume",
    "EG_open",
    "EG_high",
    "EG_low",
    "EG_close",
    "EG_Ajclose",
    "EG_volume",
    "EU_Price",
    "EU_open",
    "EU_high",
    "EU_low",
    "EU_Trend",
    "OF_Price",
    "OF_Open",
    "OF_High",
    "OF_Low",
    "OF_Volume",
    "OF_Trend",
    "OS_Price",
    "OS_Open",
    "OS_High",
    "OS_Low",
    "OS_Trend",
    "SF_Price",
    "SF_Open",
    "SF_High",
    "SF_Low",
    "SF_Volume",
    "SF_Trend",
    "USB_Price",
    "USB_Open",
    "USB_High",
    "USB_Low",
    "USB_Trend",
    "PLT_Price",
    "PLT_Open",
    "PLT_High",
    "PLT_Low",
    "PLT_Trend",
    "PLD_Price",
    "PLD_Open",
    "PLD_High",
    "PLD_Low",
    "PLD_Trend",
    "RHO_PRICE",
    "USDI_Price",
    "USDI_Open",
    "USDI_High",
    "USDI_Low",
    "USDI_Volume",
    "USDI_Trend",
    "GDX_Open",
    "GDX_High",
    "GDX_Low",
    "GDX_Close",
    "GDX_Adj Close",
    "GDX_Volume",
    "USO_Open",
    "USO_High",
    "USO_Low",
    "USO_Close",
    "USO_Adj Close",
    "USO_Volume",
]


@dataclass(frozen=True)
class SeriesSpec:
    symbol: str
    # If True, expect and use Volume column if present
    has_volume: bool = True


SERIES = {
    # Base series: USO
    "USO": SeriesSpec("uso.us", has_volume=True),
    # Equity proxies
    "SP": SeriesSpec("spy.us", has_volume=True),  # S&P 500 proxy
    "DJ": SeriesSpec("dia.us", has_volume=True),  # Dow Jones proxy
    # Gold proxy
    "EG": SeriesSpec("gld.us", has_volume=True),
    # FX
    "EU": SeriesSpec("eurusd", has_volume=False),
    # Oil proxies
    "OF": SeriesSpec("dbo.us", has_volume=True),  # Oil fund proxy
    "OS": SeriesSpec("bno.us", has_volume=True),  # Brent proxy
    # Silver
    "SF": SeriesSpec("slv.us", has_volume=True),
    # Bonds
    "USB": SeriesSpec("tlt.us", has_volume=True),
    # Platinum / Palladium (spot, no volume)
    "PLT": SeriesSpec("xptusd", has_volume=False),
    "PLD": SeriesSpec("xpdusd", has_volume=False),
    # USD index proxy
    "USDI": SeriesSpec("uup.us", has_volume=True),
    # Gold miners ETF
    "GDX": SeriesSpec("gdx.us", has_volume=True),
}


def _fetch_text(url: str, *, timeout=(5, 40), retries: int = 3, backoff: float = 1.0) -> str:
    global SESSION
    headers = {"User-Agent": "Mozilla/5.0"}
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            r = SESSION.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff * attempt)
                continue
            raise
    raise last_exc  # pragma: no cover


def _fetch_cached(url: str, cache_path: str, *, max_age_hours: float = 24.0) -> str:
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    need = True
    if os.path.exists(cache_path):
        age_seconds = time.time() - os.path.getmtime(cache_path)
        need = age_seconds > max_age_hours * 3600.0
    if need:
        text = _fetch_text(url, timeout=(5, 60), retries=3, backoff=1.0)
        with open(cache_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    with open(cache_path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _parse_money_float(s: str) -> float | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t:
        return None
    t = t.replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except Exception:
        return None


def load_rhodium_yearly_metalary(*, max_age_hours: float = 24.0 * 7) -> dict[int, float]:
    """Return {year: price_usd_per_oz}.

    Source: Metalary rhodium price history table (yearly).
    """

    html = _fetch_cached(RHO_METALARY_URL, RHO_CACHE_PATH, max_age_hours=max_age_hours)

    # The table is rendered as <table class="tablepress"> with rows like:
    # <td class="column-1">2006</td><td class="column-2">$4,442.44</td>
    pattern = re.compile(
        r"<tr[^>]*>\s*<td[^>]*>\s*(\d{4})\s*</td>\s*<td[^>]*>\s*\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*</td>",
        re.IGNORECASE,
    )
    rows = pattern.findall(html)
    out: dict[int, float] = {}
    for year_s, price_s in rows:
        year = int(year_s)
        price = _parse_money_float(price_s)
        if price is None:
            continue
        out[year] = price
    return out


def _stooq_url(symbol: str) -> str:
    return f"https://stooq.com/q/d/l/?s={symbol}&i=d"


def _cache_path(symbol: str) -> str:
    safe = symbol.replace("/", "_").replace("\\", "_")
    return os.path.join(CACHE_DIR, f"{safe}.csv")


def download_stooq(symbol: str, *, max_age_hours: float = 24.0) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(symbol)

    need = True
    if os.path.exists(path):
        age_seconds = time.time() - os.path.getmtime(path)
        need = age_seconds > max_age_hours * 3600.0

    if need:
        text = _fetch_text(_stooq_url(symbol), timeout=(5, 60), retries=3, backoff=1.0)
        if text.strip().startswith("No data") or len(text.splitlines()) < 2:
            # Keep a small marker file to avoid hammering.
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("No data")
        else:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
    return path


def load_stooq_df(symbol: str) -> pd.DataFrame:
    path = download_stooq(symbol)
    with open(path, "r", encoding="utf-8", newline="") as f:
        if f.read(20).strip().startswith("No data"):
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])  # empty

    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])  # empty

    if "Date" not in df.columns:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])  # empty

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy()

    # Standardize column names
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA

    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
    df = df.drop_duplicates(subset=["Date"], keep="first").sort_values("Date")
    return df


def _date_filter(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df
    mask = (df["Date"].dt.date >= start) & (df["Date"].dt.date <= end)
    return df.loc[mask].copy()


def _trend(price: pd.Series, open_: pd.Series) -> pd.Series:
    return price - open_


def build_dataset(start: date, end: date) -> pd.DataFrame:
    uso = _date_filter(load_stooq_df(SERIES["USO"].symbol), start, end)
    if uso.empty:
        raise RuntimeError("USO series returned no data for the requested range.")

    out = pd.DataFrame({"Date": uso["Date"].dt.strftime("%Y-%m-%d")})

    # Base OHLCV (USO)
    out["Open"] = uso["Open"]
    out["High"] = uso["High"]
    out["Low"] = uso["Low"]
    out["Close"] = uso["Close"]
    out["Adj Close"] = uso["Close"]
    out["Volume"] = uso["Volume"]

    def add_ohlcv(prefix: str, symbol: str, *, open_name: str, high_name: str, low_name: str, close_name: str, adj_name: str | None, vol_name: str | None):
        df = _date_filter(load_stooq_df(symbol), start, end)
        if df.empty:
            return
        key = df["Date"].dt.strftime("%Y-%m-%d")
        m = pd.DataFrame({
            "Date": key,
            open_name: df["Open"],
            high_name: df["High"],
            low_name: df["Low"],
            close_name: df["Close"],
        })
        if adj_name is not None:
            m[adj_name] = df["Close"]
        if vol_name is not None:
            m[vol_name] = df["Volume"]
        nonlocal out
        out = out.merge(m, on="Date", how="left")

    # SP, DJ, EG
    add_ohlcv("SP", SERIES["SP"].symbol, open_name="SP_open", high_name="SP_high", low_name="SP_low", close_name="SP_close", adj_name="SP_Ajclose", vol_name="SP_volume")
    add_ohlcv("DJ", SERIES["DJ"].symbol, open_name="DJ_open", high_name="DJ_high", low_name="DJ_low", close_name="DJ_close", adj_name="DJ_Ajclose", vol_name="DJ_volume")
    add_ohlcv("EG", SERIES["EG"].symbol, open_name="EG_open", high_name="EG_high", low_name="EG_low", close_name="EG_close", adj_name="EG_Ajclose", vol_name="EG_volume")

    # EU (EURUSD): Price=Close, Trend=Price-Open
    eu = _date_filter(load_stooq_df(SERIES["EU"].symbol), start, end)
    if not eu.empty:
        eu_key = eu["Date"].dt.strftime("%Y-%m-%d")
        eu_m = pd.DataFrame({
            "Date": eu_key,
            "EU_Price": eu["Close"],
            "EU_open": eu["Open"],
            "EU_high": eu["High"],
            "EU_low": eu["Low"],
        })
        eu_m["EU_Trend"] = _trend(eu_m["EU_Price"], eu_m["EU_open"])
        out = out.merge(eu_m, on="Date", how="left")

    # OF/OS/SF/USB: Price=Close, Trend=Price-Open
    def add_price_block(key_name: str, spec: SeriesSpec, *, price_col: str, open_col: str, high_col: str, low_col: str, vol_col: str | None, trend_col: str):
        df = _date_filter(load_stooq_df(spec.symbol), start, end)
        if df.empty:
            return
        k = df["Date"].dt.strftime("%Y-%m-%d")
        m = pd.DataFrame({
            "Date": k,
            price_col: df["Close"],
            open_col: df["Open"],
            high_col: df["High"],
            low_col: df["Low"],
        })
        if vol_col is not None:
            m[vol_col] = df["Volume"]
        m[trend_col] = _trend(m[price_col], m[open_col])
        nonlocal out
        out = out.merge(m, on="Date", how="left")

    add_price_block("OF", SERIES["OF"], price_col="OF_Price", open_col="OF_Open", high_col="OF_High", low_col="OF_Low", vol_col="OF_Volume", trend_col="OF_Trend")
    add_price_block("OS", SERIES["OS"], price_col="OS_Price", open_col="OS_Open", high_col="OS_High", low_col="OS_Low", vol_col=None, trend_col="OS_Trend")
    add_price_block("SF", SERIES["SF"], price_col="SF_Price", open_col="SF_Open", high_col="SF_High", low_col="SF_Low", vol_col="SF_Volume", trend_col="SF_Trend")
    add_price_block("USB", SERIES["USB"], price_col="USB_Price", open_col="USB_Open", high_col="USB_High", low_col="USB_Low", vol_col=None, trend_col="USB_Trend")

    # PLT / PLD
    add_price_block("PLT", SERIES["PLT"], price_col="PLT_Price", open_col="PLT_Open", high_col="PLT_High", low_col="PLT_Low", vol_col=None, trend_col="PLT_Trend")
    add_price_block("PLD", SERIES["PLD"], price_col="PLD_Price", open_col="PLD_Open", high_col="PLD_High", low_col="PLD_Low", vol_col=None, trend_col="PLD_Trend")

    # RHO_PRICE: fill from Metalary yearly history (USD/oz), then ffill/bfill.
    try:
        yearly = load_rhodium_yearly_metalary()
    except Exception:
        yearly = {}
    if yearly:
        years = pd.to_numeric(out["Date"].str.slice(0, 4), errors="coerce").astype("Int64")
        out["RHO_PRICE"] = years.map(yearly)
    else:
        out["RHO_PRICE"] = pd.NA

    # USDI (UUP ETF): Price=Close
    add_price_block(
        "USDI",
        SERIES["USDI"],
        price_col="USDI_Price",
        open_col="USDI_Open",
        high_col="USDI_High",
        low_col="USDI_Low",
        vol_col="USDI_Volume",
        trend_col="USDI_Trend",
    )

    # GDX OHLCV
    add_ohlcv("GDX", SERIES["GDX"].symbol, open_name="GDX_Open", high_name="GDX_High", low_name="GDX_Low", close_name="GDX_Close", adj_name="GDX_Adj Close", vol_name="GDX_Volume")

    # Duplicate USO_* columns
    out["USO_Open"] = out["Open"]
    out["USO_High"] = out["High"]
    out["USO_Low"] = out["Low"]
    out["USO_Close"] = out["Close"]
    out["USO_Adj Close"] = out["Adj Close"]
    out["USO_Volume"] = out["Volume"]

    # Ensure all required columns exist
    for c in REQUIRED_COLUMNS:
        if c not in out.columns:
            out[c] = pd.NA

    out = out[REQUIRED_COLUMNS]

    # Final fill pass to remove NaNs due to calendar mismatches.
    numeric_cols = [c for c in REQUIRED_COLUMNS if c != "Date"]
    out[numeric_cols] = out[numeric_cols].apply(pd.to_numeric, errors="coerce")
    out[numeric_cols] = out[numeric_cols].ffill().bfill()
    return out


def _load_existing(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    df = pd.read_csv(path)
    if "Date" not in df.columns:
        df.insert(0, "Date", pd.NA)
    # Normalize columns
    for c in REQUIRED_COLUMNS:
        if c not in df.columns:
            df[c] = pd.NA
    df = df[REQUIRED_COLUMNS]
    return df


def _fill_only_missing(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    if existing.empty:
        return new.copy()

    ex = existing.copy()
    nw = new.copy()

    ex["Date"] = ex["Date"].astype(str)
    nw["Date"] = nw["Date"].astype(str)

    ex = ex.drop_duplicates(subset=["Date"], keep="first").set_index("Date")
    nw = nw.drop_duplicates(subset=["Date"], keep="first").set_index("Date")

    # Union index
    all_idx = ex.index.union(nw.index)
    ex = ex.reindex(all_idx)
    nw = nw.reindex(all_idx)

    # Fill missing cells only
    for c in REQUIRED_COLUMNS:
        if c == "Date":
            continue
        ex[c] = ex[c].where(~ex[c].isna(), nw[c])

    out = ex.reset_index().rename(columns={"index": "Date"})
    out = out.sort_values("Date")
    return out


def update_csv(start: date, end: date, *, output_path: str = OUTPUT_CSV_PATH) -> None:
    new = build_dataset(start, end)
    existing = _load_existing(output_path)
    merged = _fill_only_missing(existing, new)

    # Write CSV
    merged.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)
    print(f"Saved: {output_path} (rows={len(merged)})")


def _parse_date_input(s: str, default: date) -> date:
    s = (s or "").strip()
    if not s:
        return default
    if s.lower() == "auto":
        return default
    return datetime.strptime(s, "%d/%m/%Y").date()


def main() -> None:
    print("Update FINAL_USO-like USD dataset (Stooq)")
    sd = _parse_date_input(input("Start date dd/mm/yyyy (or auto): "), default=date(2006, 4, 10))
    ed_in = input("End date dd/mm/yyyy (blank=today): ").strip()
    ed = datetime.now().date() if not ed_in else datetime.strptime(ed_in, "%d/%m/%Y").date()
    if sd > ed:
        raise SystemExit("Start date must be <= end date")

    update_csv(sd, ed)


if __name__ == "__main__":
    main()
