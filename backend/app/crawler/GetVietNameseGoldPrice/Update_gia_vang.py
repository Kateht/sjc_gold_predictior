import os
import shutil
import subprocess
from datetime import datetime, timedelta, date
import time
import tempfile
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import requests

import csv
import re


SESSION = requests.Session()
# Đường dẫn thư mục & file CSV (cùng folder với script này)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "gia_vang_pnj_sjc.csv")
BACKUP_CSV_PATH = os.path.join(BASE_DIR, "gia_vang_pnj_sjc.bak.csv")

# Local cache files
XAUUSD_STOOQ_CACHE_PATH = os.path.join(BASE_DIR, "stooq_cache", "xauusd_stooq_d.csv")

# SJC historical sources (available from 22/07/2009)
# - sjc.com.vn official service: /GoldPrice/Services/PriceService.ashx
# - giavang.org fallback pages
SJC_HISTORY_MIN_DATE = datetime.strptime("22/07/2009", "%d/%m/%Y").date()

# SJC official price service (POST form -> JSON)
SJC_PRICE_SERVICE_URL = "https://sjc.com.vn/GoldPrice/Services/PriceService.ashx"

# PNJ history API currently only starts returning gold_type data from this date (empirically verified).
# Keep this conservative to avoid hammering the endpoint with many empty pre-history requests.
PNJ_HISTORY_MIN_DATE = datetime.strptime("03/12/2010", "%d/%m/%Y").date()


# Columns used in the gold dataset
PNJ_SJC_COLS = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]
ALL_COLS = PNJ_SJC_COLS


def _atomic_write_csv_with_backup(df: pd.DataFrame, target_path: str, backup_path: str | None = None):
    """Write CSV atomically and keep a backup copy of the previous file."""
    folder = os.path.dirname(target_path) or "."
    os.makedirs(folder, exist_ok=True)

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=folder,
            prefix=os.path.basename(target_path) + ".tmp.",
            suffix=".csv",
        ) as f:
            tmp_file = f.name
            df.to_csv(f, index=False)

        if backup_path and os.path.exists(target_path) and os.path.getsize(target_path) > 0:
            try:
                shutil.copy2(target_path, backup_path)
            except Exception:
                pass

        os.replace(tmp_file, target_path)
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
##Crawler
def parse_price(text):
    try:
        if text is None:
            return None
        # Accept both strings and numbers
        text = str(text)
        # Loại bỏ dấu chấm, chuyển về int rồi chia cho 1000
        clean = text.replace('.', '').strip()
        value = int(clean)
        return round(value / 1000, 2)
    except:
        return None


def parse_million_vnd_per_luong(value):
    """Parse a provider value into 'triệu đồng/lượng'.

    Providers sometimes return values as:
    - thousand VND / chỉ (e.g. '17250')
    - VND / chỉ (e.g. '17170000')
    - thousand VND / lượng (e.g. PNJ already handled by parse_price)

    This function uses magnitude heuristics for best-effort normalization.
    """
    if value is None:
        return None
    # Try a numeric parse first (important for values like '17250000.000000').
    n_int: int | None = None
    try:
        if isinstance(value, (int, float)):
            n_int = int(round(float(value)))
        else:
            s = str(value).strip()
            s_num = s.replace(",", "")
            if re.fullmatch(r"-?\d+(?:\.\d+)?", s_num):
                n_int = int(round(float(s_num)))
    except Exception:
        n_int = None

    # Fallback: strip non-digits (handles HTML like '<b>17250</b>').
    if n_int is None:
        s = str(value)
        digits = re.sub(r"\D+", "", s)
        if not digits:
            return None
        try:
            n_int = int(digits)
        except Exception:
            return None

    n = n_int

    # Heuristics:
    # - very small values are usually thousand VND / chỉ (x10 chỉ per lượng)
    # - mid values in the millions are usually VND / chỉ
    # - very large values are usually VND / lượng
    if n < 500_000:
        # thousand VND / chỉ -> million VND / lượng: (n*1000*10)/1e6 = n/100
        return round(n / 100.0, 2)
    if n < 50_000_000:
        # VND / chỉ -> million VND / lượng: (n*10)/1e6 = n/100000
        return round(n / 100_000.0, 2)
    # VND / lượng
    return round(n / 1_000_000.0, 2)


def _fetch_text(
    url: str,
    params: dict | None = None,
    timeout: int | tuple[int, int] = (5, 15),
    retries: int = 3,
    backoff: float = 1.0,
):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0",
    }
    global SESSION
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status = None
            try:
                status = exc.response.status_code if exc.response is not None else None
            except Exception:
                status = None

            if status in {429, 500, 502, 503, 504} and attempt < retries:
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
                time.sleep(backoff * (attempt ** 2))
                continue
            raise
        except Exception as exc:
            last_exc = exc
            if isinstance(exc, requests.exceptions.RequestException):
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last_exc


def _fetch_json(
    url: str,
    params: dict | None = None,
    timeout: int | tuple[int, int] = (5, 15),
    retries: int = 3,
    backoff: float = 1.0,
):
    """Fetch JSON with simple retry/backoff."""
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    global SESSION
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status = None
            try:
                status = exc.response.status_code if exc.response is not None else None
            except Exception:
                status = None

            if status in {429, 500, 502, 503, 504} and attempt < retries:
                # Heavier backoff for server/rate-limit errors.
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
                time.sleep(backoff * (attempt ** 2))
                continue

            # Non-retriable (or out of retries)
            raise
        except Exception as exc:
            last_exc = exc
            # Reset session on network-ish failures to avoid stuck/bad pooled connections.
            if isinstance(exc, requests.exceptions.RequestException):
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last_exc


def _post_form_json(
    url: str,
    data: dict | None = None,
    timeout: int | tuple[int, int] = (5, 15),
    retries: int = 3,
    backoff: float = 1.0,
):
    """POST x-www-form-urlencoded and parse JSON, with retry/backoff."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "User-Agent": "Mozilla/5.0",
    }
    global SESSION
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.post(url, data=data, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            status = None
            try:
                status = exc.response.status_code if exc.response is not None else None
            except Exception:
                status = None

            if status in {429, 500, 502, 503, 504} and attempt < retries:
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
                time.sleep(backoff * (attempt ** 2))
                continue
            raise
        except Exception as exc:
            last_exc = exc
            if isinstance(exc, requests.exceptions.RequestException):
                try:
                    SESSION.close()
                except Exception:
                    pass
                SESSION = requests.Session()
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last_exc


def _vnd_to_million_vnd_per_luong(value) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value) / 1_000_000.0, 2)
    except Exception:
        return None

def get_gold_data_for_date(date_obj):
    """Lấy giá PNJ/SJC theo ngày từ API JSON của PNJ.

    Ghi chú: Website PNJ hiện render bằng JS nên cách scrape HTML cũ thường không còn bảng dữ liệu.
    API lịch sử theo ngày trả về nhiều mốc cập nhật trong ngày; ta lấy bản ghi cuối cùng (mới nhất) trong ngày.
    """

    ymd = date_obj.strftime("%Y%m%d")
    url = "https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history"

    def _extract_buy_sell(g: dict | None):
        if not g:
            return None, None
        data_points = g.get("data") or []
        if data_points:
            last = data_points[-1]
            return parse_price(last.get("gia_mua")), parse_price(last.get("gia_ban"))
        return parse_price(g.get("gia_mua")), parse_price(g.get("gia_ban"))

    def _get_current_price_today():
        # Current endpoint (works even when history endpoint is unstable), but has no per-day history.
        url_current = "https://edge-cf-api.pnj.io/ecom-frontend/v3/get-gold-price"
        payload_current = _fetch_json(url_current, timeout=(5, 20), retries=5, backoff=1.0)
        locations_current = payload_current.get("locations") or []
        if not locations_current:
            return {"PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}
        location_current = next((l for l in locations_current if l.get("name") == "TPHCM"), locations_current[0])
        gold_types_current = location_current.get("gold_type") or []
        g_pnj = next((x for x in gold_types_current if x.get("name") == "PNJ"), None)
        g_sjc = next((x for x in gold_types_current if x.get("name") == "SJC"), None)
        pnj_mua, pnj_ban = _extract_buy_sell(g_pnj)
        sjc_mua, sjc_ban = _extract_buy_sell(g_sjc)
        return {"PNJ_gia_mua": pnj_mua, "PNJ_gia_ban": pnj_ban, "SJC_gia_mua": sjc_mua, "SJC_gia_ban": sjc_ban}

    try:
        payload = _fetch_json(url, params={"date": ymd}, timeout=(5, 20), retries=5, backoff=1.0)
    except Exception:
        # Best-effort: for today, fallback to current endpoint.
        if date_obj == datetime.now().date():
            try:
                return _get_current_price_today()
            except Exception:
                pass
        return {"PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}

    locations = payload.get("locations") or []
    if not locations:
        # Best-effort: for today, fallback to current endpoint.
        if date_obj == datetime.now().date():
            try:
                return _get_current_price_today()
            except Exception:
                pass
        return {"PNJ_gia_mua": None, "PNJ_gia_ban": None, "SJC_gia_mua": None, "SJC_gia_ban": None}

    # Ưu tiên location TPHCM để đồng nhất với dữ liệu CSV cũ
    location = next((l for l in locations if l.get("name") == "TPHCM"), locations[0])
    gold_types = location.get("gold_type") or []

    def last_price(gold_name: str):
        g = next((x for x in gold_types if x.get("name") == gold_name), None)
        return _extract_buy_sell(g)

    pnj_mua, pnj_ban = last_price("PNJ")
    sjc_mua, sjc_ban = last_price("SJC")
    return {"PNJ_gia_mua": pnj_mua, "PNJ_gia_ban": pnj_ban, "SJC_gia_mua": sjc_mua, "SJC_gia_ban": sjc_ban}


def get_sjc_official_for_date(date_obj: date) -> dict:
    """Fetch SJC buy/sell for a date from SJC official price service.

    Returns values normalized to triệu đồng/lượng.
    """
    try:
        payload = _post_form_json(
            SJC_PRICE_SERVICE_URL,
            data={"method": "GetSJCGoldPriceByDate", "toDate": date_obj.strftime("%d/%m/%Y")},
            timeout=(5, 20),
            retries=3,
            backoff=1.0,
        )
    except Exception:
        return {"SJC_gia_mua": None, "SJC_gia_ban": None}

    if not isinstance(payload, dict) or payload.get("success") is not True:
        return {"SJC_gia_mua": None, "SJC_gia_ban": None}

    rows = payload.get("data") or []
    if not rows:
        return {"SJC_gia_mua": None, "SJC_gia_ban": None}

    def _is_sjc_1l_row(r: dict) -> bool:
        type_name = str(r.get("TypeName") or "").lower()
        return "sjc" in type_name and "1l" in type_name and "10l" in type_name and "1kg" in type_name

    # Prefer Hồ Chí Minh price for consistency with existing CSV.
    target = None
    for r in rows:
        branch = str(r.get("BranchName") or "").lower()
        if ("hồ chí minh" in branch or "ho chi minh" in branch) and _is_sjc_1l_row(r):
            target = r
            break
    if target is None:
        target = next((r for r in rows if _is_sjc_1l_row(r)), rows[0])

    mua = _vnd_to_million_vnd_per_luong(target.get("BuyValue"))
    ban = _vnd_to_million_vnd_per_luong(target.get("SellValue"))
    return {"SJC_gia_mua": mua, "SJC_gia_ban": ban}


def get_sjc_giavang_for_date(date_obj: date) -> dict:
    """Fetch SJC buy/sell for a date from giavang.org history pages.

    Values on the page are in x1000đ/lượng. We normalize to triệu đồng/lượng.
    Example: 21.060 (x1000đ/lượng) -> 21.06 (triệu/lượng)
    """
    url = f"https://giavang.org/trong-nuoc/sjc/lich-su/{date_obj.strftime('%Y-%m-%d')}.html"
    try:
        html = _fetch_text(url, timeout=(5, 25), retries=3, backoff=1.0)
    except Exception:
        return {"SJC_gia_mua": None, "SJC_gia_ban": None}

    # Robust HTML regex: pick the first data row with HCM + SJC 1L/10L/1KG.
    # Example row:
    # <tr><th ...>Hồ Chí Minh</th><td ...>Vàng SJC 1L, 10L, 1KG</td>
    #     <td ...>21.060</td><td ...>21.120</td>...
    m = re.search(
        r"<tr>\s*<th[^>]*>\s*Hồ\s*Chí\s*Minh\s*</th>\s*<td[^>]*>\s*Vàng\s*SJC\s*1L,\s*10L,\s*1KG\s*</td>\s*"
        r"<td[^>]*>\s*([0-9]{1,3}(?:\.[0-9]{3})+)\s*</td>\s*<td[^>]*>\s*([0-9]{1,3}(?:\.[0-9]{3})+)\s*</td>",
        html,
        re.IGNORECASE,
    )
    if not m:
        # Looser fallback: first occurrence of two consecutive price cells.
        m = re.search(
            r"<td[^>]*class=\"text-right\"[^>]*>\s*([0-9]{1,3}(?:\.[0-9]{3})+)\s*</td>\s*"
            r"<td[^>]*class=\"text-right\"[^>]*>\s*([0-9]{1,3}(?:\.[0-9]{3})+)\s*</td>",
            html,
            re.IGNORECASE,
        )
    if not m:
        return {"SJC_gia_mua": None, "SJC_gia_ban": None}

    mua = parse_price(m.group(1))
    ban = parse_price(m.group(2))
    return {"SJC_gia_mua": mua, "SJC_gia_ban": ban}


def get_btmc_sjc_data_for_date(date_obj):
    """Get BTMC SJC buy/sell for a specific date.

    Endpoint: https://btmc.vn/ProductHome/getGoldDate?date=dd/mm/YYYY
    Values are embedded as HTML tags (<b>..</b>).
    """
    try:
        payload = _fetch_json(
            "https://btmc.vn/ProductHome/getGoldDate",
            params={"date": date_obj.strftime("%d/%m/%Y")},
            timeout=(5, 20),
            retries=3,
            backoff=0.8,
        )
    except Exception:
        return {"BTMC_SJC_gia_mua": None, "BTMC_SJC_gia_ban": None}

    data = payload.get("Data") or {}
    mua = parse_million_vnd_per_luong(data.get("sjcmua"))
    ban = parse_million_vnd_per_luong(data.get("sjcban"))
    return {"BTMC_SJC_gia_mua": mua, "BTMC_SJC_gia_ban": ban}


_BTMH_SJC_SERIES_CACHE: dict[date, tuple[float | None, float | None]] | None = None
_BTMH_SJC_SERIES_FETCHED_AT: float | None = None


def _refresh_btmh_sjc_series(max_age_seconds: float = 15 * 60):
    """Refresh BTMH SJC series cache (best-effort).

    API provides limited daily history (currently ~last 72 days) via time_type='year'.
    """
    global _BTMH_SJC_SERIES_CACHE, _BTMH_SJC_SERIES_FETCHED_AT
    now = time.time()
    if (
        _BTMH_SJC_SERIES_CACHE is not None
        and _BTMH_SJC_SERIES_FETCHED_AT is not None
        and (now - _BTMH_SJC_SERIES_FETCHED_AT) <= max_age_seconds
    ):
        return

    try:
        payload = _fetch_json(
            "https://baotinmanhhai.vn/api/v1/exchangerate/goldRateChart",
            params={"gold_type": "SJC9999", "time_type": "year", "init": "false"},
            timeout=(5, 20),
            retries=3,
            backoff=0.8,
        )
    except Exception:
        _BTMH_SJC_SERIES_CACHE = {}
        _BTMH_SJC_SERIES_FETCHED_AT = now
        return

    labels = payload.get("labels") or []
    data = payload.get("data") or {}
    rates = data.get("rate") or []
    sells = data.get("sell") or []

    cache: dict[date, tuple[float | None, float | None]] = {}
    for label, rate, sell in zip(labels, rates, sells):
        try:
            d = datetime.strptime(str(label), "%Y-%m-%d").date()
        except Exception:
            continue
        cache[d] = (parse_million_vnd_per_luong(rate), parse_million_vnd_per_luong(sell))

    _BTMH_SJC_SERIES_CACHE = cache
    _BTMH_SJC_SERIES_FETCHED_AT = now


def get_btmh_sjc_data_for_date(date_obj):
    _refresh_btmh_sjc_series()
    if not _BTMH_SJC_SERIES_CACHE:
        return {"BTMH_SJC_gia_mua": None, "BTMH_SJC_gia_ban": None}
    mua, ban = _BTMH_SJC_SERIES_CACHE.get(date_obj, (None, None))
    return {"BTMH_SJC_gia_mua": mua, "BTMH_SJC_gia_ban": ban}


def get_doji_sjc_data_for_date(date_obj):
    """Best-effort DOJI SJC for today only (HTML page is not a stable history API)."""
    if date_obj != datetime.now().date():
        return {"DOJI_SJC_gia_mua": None, "DOJI_SJC_gia_ban": None}
    try:
        html = _fetch_text("https://giavang.doji.vn/", timeout=(5, 20), retries=3, backoff=0.8)
    except Exception:
        return {"DOJI_SJC_gia_mua": None, "DOJI_SJC_gia_ban": None}

    # Try to find the row "SJC" (usually "SJC -Bán Lẻ") with unit "(nghìn/chỉ)".
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
    for row in rows:
        if "sjc" not in row.lower():
            continue
        # Prefer the SJC row in nghìn/chỉ (thousand VND per chỉ)
        if "nghìn/chỉ" not in row.lower():
            continue

        nums = re.findall(r"\d[\d\.,]+", row)
        if len(nums) < 2:
            continue

        # The row also contains CSS sizes like 'size-18', 'size-13';
        # pick the two price-like numbers (>= 1000 after stripping).
        price_tokens: list[str] = []
        for tok in nums:
            digits = re.sub(r"\D+", "", tok)
            if not digits:
                continue
            try:
                n = int(digits)
            except Exception:
                continue
            if n >= 1000:
                price_tokens.append(tok)

        if len(price_tokens) < 2:
            continue

        mua = parse_million_vnd_per_luong(price_tokens[-2])
        ban = parse_million_vnd_per_luong(price_tokens[-1])
        if mua is not None or ban is not None:
            return {"DOJI_SJC_gia_mua": mua, "DOJI_SJC_gia_ban": ban}

    return {"DOJI_SJC_gia_mua": None, "DOJI_SJC_gia_ban": None}


def load_xauusd_ohlc_cache(start_date, end_date, *, max_file_age_hours: float = 24.0, cache_path: str = XAUUSD_STOOQ_CACHE_PATH):
    """Load XAU/USD OHLC data from Stooq into a dict for the requested date range."""
    need_download = True
    if os.path.exists(cache_path):
        age_seconds = time.time() - os.path.getmtime(cache_path)
        need_download = age_seconds > (max_file_age_hours * 3600.0)

    def _write_empty_cache() -> None:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])

    def _cache_has_required_headers() -> bool:
        if not os.path.exists(cache_path) or os.path.getsize(cache_path) <= 0:
            return False

        try:
            with open(cache_path, "r", encoding="utf-8", newline="") as f:
                header = f.readline().strip().lower()
        except Exception:
            return False

        return header.startswith("date,") and all(column in header for column in ("open", "high", "low", "close"))

    if need_download:
        url = "https://stooq.com/q/d/l/"
        params = {"s": "xauusd", "i": "d"}
        csv_text = _fetch_text(url, params=params, timeout=(5, 40), retries=3, backoff=1.0)

        # Guard against servers returning empty/invalid bodies (would wipe the local cache).
        head = (csv_text or "").strip().splitlines()[:1]
        looks_like_csv = bool(head) and head[0].strip().lower().startswith("date,")
        if not looks_like_csv:
            if not _cache_has_required_headers():
                _write_empty_cache()
            print("Warning: Stooq returned invalid XAUUSD CSV; using the local cache fallback.")
        else:
            with open(cache_path, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text)

    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)

    out: dict[date, dict[str, float]] = {}
    with open(cache_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d_raw = row.get("Date")
            if not d_raw:
                continue
            try:
                d = datetime.strptime(d_raw, "%Y-%m-%d").date()
            except Exception:
                continue
            if d < start_ts.date() or d > end_ts.date():
                continue
            try:
                out[d] = {
                    "XAUUSD_Open": float(row.get("Open")) if row.get("Open") else None,
                    "XAUUSD_High": float(row.get("High")) if row.get("High") else None,
                    "XAUUSD_Low": float(row.get("Low")) if row.get("Low") else None,
                    "XAUUSD_Close": float(row.get("Close")) if row.get("Close") else None,
                }
            except Exception:
                continue
    return out


def get_all_data_for_date(date_obj, *, xauusd_cache: dict | None = None, pnj_enabled: bool = True):
    data: dict[str, float | None] = {c: None for c in ALL_COLS}
    if pnj_enabled:
        data.update(get_gold_data_for_date(date_obj))

    # Fallback: SJC official history (from 22/07/2009), then giavang.org.
    if date_obj >= SJC_HISTORY_MIN_DATE:
        if data.get("SJC_gia_mua") is None or data.get("SJC_gia_ban") is None:
            sjc_official = get_sjc_official_for_date(date_obj)
            if data.get("SJC_gia_mua") is None:
                data["SJC_gia_mua"] = sjc_official.get("SJC_gia_mua")
            if data.get("SJC_gia_ban") is None:
                data["SJC_gia_ban"] = sjc_official.get("SJC_gia_ban")

        if data.get("SJC_gia_mua") is None or data.get("SJC_gia_ban") is None:
            sjc_fallback = get_sjc_giavang_for_date(date_obj)
            if data.get("SJC_gia_mua") is None:
                data["SJC_gia_mua"] = sjc_fallback.get("SJC_gia_mua")
            if data.get("SJC_gia_ban") is None:
                data["SJC_gia_ban"] = sjc_fallback.get("SJC_gia_ban")

    return data


def history_api_healthcheck(test_date: str = "20130107") -> tuple[bool, str]:
    """Check whether the PNJ history endpoint is currently healthy.

    Returns:
        (ok, message)
    """
    url = "https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history"
    try:
        _fetch_json(url, params={"date": test_date}, timeout=(5, 10), retries=1, backoff=0.0)
        return True, "ok"
    except requests.exceptions.HTTPError as exc:
        status = None
        try:
            status = exc.response.status_code if exc.response is not None else None
        except Exception:
            status = None
        return False, f"http_{status}"
    except Exception as exc:
        return False, type(exc).__name__


def api_has_data_for_date(date_obj) -> bool:
    """Kiểm tra API có trả dữ liệu (locations/gold_type) cho ngày này không."""
    ymd = date_obj.strftime("%Y%m%d")
    url = "https://edge-cf-api.pnj.io/ecom-frontend/v1/get-gold-price-history"
    try:
        payload = _fetch_json(url, params={"date": ymd}, timeout=(5, 15), retries=3, backoff=0.75)
    except Exception:
        return False
    locations = payload.get("locations") or []
    if not locations:
        return False
    gt = locations[0].get("gold_type") or []
    return len(gt) > 0


def find_earliest_api_date(start_date, end_date):
    """Tìm ngày sớm nhất trong [start_date, end_date] mà API có dữ liệu.

    Ghi chú: API có thể trả rỗng vào cuối tuần/ngày lễ => tính chất "có dữ liệu" không đơn điệu theo ngày.
    Vì vậy tránh binary-search trực tiếp trên toàn range.

    Chiến lược (thực dụng, ít request):
    - Probe thưa theo bước ~30 ngày để tìm một mốc bất kỳ có dữ liệu.
    - Sau đó scan lại từng ngày trong cửa sổ 30 ngày trước mốc đó để lấy ngày sớm nhất.
    """
    if start_date > end_date:
        return None

    # Start window: handle cases where start_date itself is weekend/holiday.
    for offset in range(0, 7):
        d0 = start_date + timedelta(days=offset)
        if d0 > end_date:
            break
        if api_has_data_for_date(d0):
            return d0

    # Probe with a shorter step and a small window to avoid repeatedly hitting weekends.
    step_days = 14
    probe = start_date
    found = None
    while probe <= end_date:
        for offset in range(0, 7):
            d0 = probe + timedelta(days=offset)
            if d0 > end_date:
                break
            if api_has_data_for_date(d0):
                found = d0
                break
        if found is not None:
            break
        probe += timedelta(days=step_days)

    if found is None:
        # Fallback: scan daily in the last window.
        d = max(start_date, end_date - timedelta(days=step_days))
        while d <= end_date:
            if api_has_data_for_date(d):
                found = d
                break
            d += timedelta(days=1)
        if found is None:
            return None

    window_start = max(start_date, found - timedelta(days=step_days))
    d = window_start
    while d <= found:
        if api_has_data_for_date(d):
            return d
        d += timedelta(days=1)
    return found


def report_missing_dates(start_date, end_date, csv_path: str = CSV_PATH, cols: list[str] | None = None):
    """Liệt kê các ngày bị thiếu dòng hoặc thiếu dữ liệu trong CSV theo khoảng ngày."""
    if cols is None:
        cols = PNJ_SJC_COLS
    if not os.path.exists(csv_path):
        print("CSV chưa tồn tại.")
        return

    df = pd.read_csv(csv_path)
    df["Ngày"] = pd.to_datetime(df["Ngày"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Ngày"]).copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA

    all_days = pd.date_range(start=pd.to_datetime(start_date), end=pd.to_datetime(end_date), freq="D")
    df = df.drop_duplicates(subset=["Ngày"], keep="first").set_index("Ngày")
    df = df.reindex(all_days)

    missing_row_dates = df[df[cols].isna().all(axis=1)].index
    missing_any_dates = df[df[cols].isna().any(axis=1)].index

    print(f"Khoảng kiểm tra: {start_date.strftime('%d/%m/%Y')} -> {end_date.strftime('%d/%m/%Y')}")
    print(f"Ngày thiếu toàn bộ 4 cột (toàn NaN): {len(missing_row_dates)}")
    if len(missing_row_dates):
        print(missing_row_dates.strftime("%d/%m/%Y").to_list())
    print(f"Ngày thiếu ít nhất 1 cột: {len(missing_any_dates)}")
    if len(missing_any_dates):
        print(missing_any_dates.strftime("%d/%m/%Y").to_list())


def _forward_fill_range(
    csv_path: str,
    start_date,
    end_date,
    cols: list[str],
    bfill_initial: bool = False,
    backup_csv_path: str = BACKUP_CSV_PATH,
):
    """Forward-fill các cột giá trong khoảng ngày (theo thứ tự thời gian tăng dần)."""
    df = pd.read_csv(csv_path)
    df["Ngày"] = pd.to_datetime(df["Ngày"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Ngày"]).copy()
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = pd.NA

    df = df.drop_duplicates(subset=["Ngày"], keep="first").set_index("Ngày").sort_index()

    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)

    # Only ensure daily rows exist within the requested range.
    all_days = pd.date_range(start=start_ts, end=end_ts, freq="D")
    df = df.reindex(df.index.union(all_days)).sort_index()

    # Fill based on the full series so the first day in [start_ts, end_ts]
    # can inherit a value from the day before start_ts.
    before = df.loc[start_ts:end_ts, cols].isna().sum().sum()
    filled = df[cols].ffill()
    if bfill_initial:
        filled = filled.bfill()
    df.loc[start_ts:end_ts, cols] = filled.loc[start_ts:end_ts, cols]

    after = df.loc[start_ts:end_ts, cols].isna().sum().sum()
    df_out = df.reset_index().rename(columns={"index": "Ngày"}).sort_values(by="Ngày", ascending=False)
    df_out["Ngày"] = df_out["Ngày"].dt.strftime("%d/%m/%Y")
    _atomic_write_csv_with_backup(df_out, csv_path, backup_csv_path)
    return int(before - after) if before >= after else 0


def fill_missing_data(
    start_date,
    end_date,
    csv_path: str = CSV_PATH,
    xauusd_cache_path: str = XAUUSD_STOOQ_CACHE_PATH,
    backup_csv_path: str = BACKUP_CSV_PATH,
    forward_fill: bool = True,
    bfill_initial: bool = False,
    limit_to_api_availability: bool = True,
    sleep_seconds: float = 0.15,
    progress_every: int = 200,
    save_every_requests: int | None = 200,
    verbose: bool = True,
    require_history_api_healthy: bool = True,
):
    """Crawl lại các ngày thiếu và (tuỳ chọn) forward-fill để lấp các ngày API không có dữ liệu."""

    # PNJ history endpoint health is important, but we still allow updating other sources.
    pnj_enabled = True
    ok, msg = history_api_healthcheck()
    if not ok:
        if require_history_api_healthy:
            print(
                "CẢNH BÁO: PNJ history API đang không ổn định/không truy cập được (" + msg + "). "
                "Sẽ tạm bỏ qua PNJ/SJC (PNJ) và vẫn cập nhật các nguồn khác nếu có."
            )
            pnj_enabled = False
            limit_to_api_availability = False
        else:
            print(
                "CẢNH BÁO: PNJ history API đang không ổn định/không truy cập được (" + msg + "). "
                "Sẽ chạy best-effort."
            )
            if forward_fill:
                print("Tạm tắt forward_fill để tránh lan truyền giá cũ qua khoảng trống lớn khi API lỗi.")
                forward_fill = False

    requested_start = start_date
    if limit_to_api_availability:
        # We no longer hard-clamp start_date. Instead, each provider is gated per-date/column.
        # This keeps the script flexible for future sources and still avoids calling unsupported APIs.
        if verbose and start_date < SJC_HISTORY_MIN_DATE:
            print(
                f"Lưu ý: dữ liệu SJC lịch sử hiện có từ {SJC_HISTORY_MIN_DATE.strftime('%d/%m/%Y')}; "
                "các ngày trước đó sẽ để trống cột SJC."
            )
        if verbose and start_date < PNJ_HISTORY_MIN_DATE:
            print(
                f"Lưu ý: PNJ history API hiện có dữ liệu từ {PNJ_HISTORY_MIN_DATE.strftime('%d/%m/%Y')}; "
                "các ngày trước đó sẽ để trống cột PNJ."
            )

    crawl_stats = code_update_gia_vang(
        start_date,
        end_date,
        pnj_enabled=pnj_enabled,
        sleep_seconds=sleep_seconds,
        verbose=verbose,
        progress_every=progress_every,
        save_every_requests=save_every_requests,
        filepath=csv_path,
        xauusd_cache_path=xauusd_cache_path,
        backup_csv_path=backup_csv_path,
    )
    forward_fill_cells = 0
    if forward_fill:
        forward_fill_cells = _forward_fill_range(
            csv_path,
            requested_start,
            end_date,
            ALL_COLS,
            bfill_initial=bfill_initial,
            backup_csv_path=backup_csv_path,
        )
        print("Đã forward-fill các ngày còn trống trong khoảng.")

    result = dict(crawl_stats)
    result.update(
        {
            "forward_fill_cells": forward_fill_cells,
            "filled_cells_total": int(crawl_stats.get("crawl_filled_cells", 0)) + int(forward_fill_cells),
            "csv_path": csv_path,
            "start_date": requested_start,
            "end_date": end_date,
        }
    )
    return result

def code_update_gia_vang(
    start_date,
    end_date,
    *,
    filepath: str = CSV_PATH,
    xauusd_cache_path: str = XAUUSD_STOOQ_CACHE_PATH,
    backup_csv_path: str = BACKUP_CSV_PATH,
    pnj_enabled: bool = True,
    sleep_seconds: float = 0.15,
    verbose: bool = True,
    progress_every: int = 50,
    save_every_requests: int | None = 200,
):
    # Thư mục chứa file và đường dẫn file CSV
    folder = os.path.dirname(filepath) or BASE_DIR
    os.makedirs(folder, exist_ok=True)    

    cols = ALL_COLS

    # Đọc dữ liệu đã có (nếu file tồn tại)
    if os.path.exists(filepath):
        df_existing = pd.read_csv(filepath)
        df_existing["Ngày"] = pd.to_datetime(df_existing["Ngày"], dayfirst=True, errors="coerce")
        df_existing = df_existing.dropna(subset=["Ngày"]).copy()
        # Chuẩn hoá NA và kiểu số
        df_existing.replace({"": pd.NA}, inplace=True)

        # Enforce canonical schema: keep only the columns we actively maintain.
        # This drops legacy ultra-sparse provider columns (e.g. DOJI/BTMC/BTMH) so they won't reappear.
        keep_cols = ["Ngày"] + cols
        df_existing = df_existing[[c for c in keep_cols if c in df_existing.columns]].copy()
        for c in cols:
            if c in df_existing.columns:
                df_existing[c] = pd.to_numeric(df_existing[c], errors="coerce")
            else:
                df_existing[c] = pd.NA
    else:
        df_existing = pd.DataFrame(columns=["Ngày"] + cols)
        df_existing["Ngày"] = pd.to_datetime(df_existing["Ngày"], errors="coerce")

    # Set index theo ngày để update in-place
    df_existing = df_existing.drop_duplicates(subset=["Ngày"], keep="first").set_index("Ngày")

    updated_count = 0
    inserted_count = 0
    filled_cells_count = 0

    crawled_requests = 0

    def _supports_col_for_date(d, col: str) -> bool:
        if col in PNJ_SJC_COLS:
            if col.startswith("SJC_"):
                # Allow SJC backfill from official SJC/giavang sources as early as 22/07/2009.
                return d >= SJC_HISTORY_MIN_DATE
            # PNJ history API returns empty gold_type before ~03/12/2010.
            return pnj_enabled and d >= PNJ_HISTORY_MIN_DATE
        return True

    def _save_csv_checkpoint():
        df_all = df_existing.reset_index().rename(columns={"index": "Ngày"})
        df_all = df_all[["Ngày"] + cols]
        df_all = df_all.sort_values(by="Ngày", ascending=False)
        df_all["Ngày"] = df_all["Ngày"].dt.strftime("%d/%m/%Y")
        _atomic_write_csv_with_backup(df_all, filepath, backup_csv_path)

    current_date = start_date
    try:
        while current_date <= end_date:
            dt = pd.to_datetime(current_date)
            date_str = current_date.strftime("%d/%m/%Y")

            is_new_row = dt not in df_existing.index

            # Nếu ngày đã có nhưng còn thiếu giá -> crawl lại để bù ô trống
            if is_new_row:
                missing_cols = cols.copy()
            else:
                row = df_existing.loc[dt]
                missing_cols = [c for c in cols if pd.isna(row.get(c))]

            supported_missing_cols = [c for c in missing_cols if _supports_col_for_date(current_date, c)]

            # Skip dates where only unsupported provider columns are missing (e.g. DOJI history).
            if (is_new_row or missing_cols) and not supported_missing_cols:
                current_date += timedelta(days=1)
                continue

            if is_new_row or supported_missing_cols:
                crawled_requests += 1
                if verbose:
                    show_missing = supported_missing_cols if supported_missing_cols else missing_cols
                    print(f"Crawling {date_str}... (missing: {', '.join(show_missing) if show_missing else 'new'})")
                else:
                    if crawled_requests % max(progress_every, 1) == 0:
                        print(f"Progress: crawled {crawled_requests} requests, current {date_str}")

                # Avoid unnecessary PNJ history calls when none of the PNJ columns are being filled.
                # This helps reduce 429 rate-limits on the PNJ endpoint.
                need_pnj = any(c.startswith("PNJ_") for c in supported_missing_cols)
                data = get_all_data_for_date(
                    current_date,
                    pnj_enabled=(pnj_enabled and need_pnj),
                )
                any_data = any(data.get(c) is not None for c in cols)

                # Avoid inserting a brand-new all-NaN row when API returns no data
                # (weekend/holiday or API outage). Forward-fill can later add daily rows.
                if is_new_row and not any_data:
                    if sleep_seconds and sleep_seconds > 0:
                        time.sleep(sleep_seconds)
                    if save_every_requests and crawled_requests % max(save_every_requests, 1) == 0:
                        _save_csv_checkpoint()
                        print(
                            f"Checkpoint saved: requests={crawled_requests}, inserted={inserted_count}, updated_missing={updated_count}"
                        )
                    current_date += timedelta(days=1)
                    continue

                if is_new_row:
                    df_existing.loc[dt, cols] = [pd.NA] * len(cols)

                filled_any = False
                for c in cols:
                    if pd.isna(df_existing.at[dt, c]) and data.get(c) is not None:
                        df_existing.at[dt, c] = data[c]
                        filled_any = True
                        filled_cells_count += 1

                if sleep_seconds and sleep_seconds > 0:
                    time.sleep(sleep_seconds)

                if is_new_row:
                    inserted_count += 1
                elif filled_any:
                    updated_count += 1

                if save_every_requests and crawled_requests % max(save_every_requests, 1) == 0:
                    _save_csv_checkpoint()
                    print(
                        f"Checkpoint saved: requests={crawled_requests}, inserted={inserted_count}, updated_missing={updated_count}"
                    )

            current_date += timedelta(days=1)
    except KeyboardInterrupt:
        print("\nInterrupted. Saving partial progress...")
    finally:
        _save_csv_checkpoint()
        print(f"Saved CSV: inserted={inserted_count}, updated_missing={updated_count} -> {filepath}")
    return {
        "crawled_requests": crawled_requests,
        "inserted_rows": inserted_count,
        "updated_rows": updated_count,
        "crawl_filled_cells": filled_cells_count,
        "csv_path": filepath,
    }

def update_missing_data(start_date, end_date):
    """
    Gọi batch crawl để đảm bảo CSV đã đầy đủ dữ liệu từ start_date đến end_date.
    """
    code_update_gia_vang(start_date, end_date)
    print(f"Đã cập nhật dữ liệu từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}.")


def visualize(start_date, end_date, columns):
    """
    Đọc CSV, lọc, vẽ đồ thị giá vàng cho các cột trong `columns`
    """
    df = pd.read_csv(CSV_PATH, parse_dates=["Ngày"], dayfirst=True)
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    mask = (df['Ngày'].dt.date >= start_date) & (df['Ngày'].dt.date <= end_date)
    df = df.loc[mask].copy()
    df.dropna(subset=columns, how='all', inplace=True)
    if df.empty:
        print("Không có dữ liệu để hiển thị sau khi loại NaN.")
        return

    # Giới hạn trục Y
    vals = df[columns]
    ymin, ymax = vals.min().min(), vals.max().max()

    fig, ax = plt.subplots(figsize=(10, 6))
    marker_map = {
        "PNJ_gia_mua": "o", "PNJ_gia_ban": "o",
        "SJC_gia_mua": "x", "SJC_gia_ban": "x"
    }
    for col in columns:
        ax.plot(
            df['Ngày'],
            df[col],
            marker=marker_map.get(col, 'o'),
            label=col
        )

    ax.set_ylim(ymin * 0.99, ymax * 1.01)
    ax.set_ylabel('Giá (triệu đồng/lượng)')

    # Định dạng trục X (giữ nguyên logic cũ)
    days = (end_date - start_date).days
    if days <= 10:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%y'))
        ax.xaxis.set_major_locator(mdates.DayLocator())
    else:
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
        for year, group in df.groupby(df['Ngày'].dt.year):
            dates = group['Ngày']
            mid = dates.iloc[len(dates)//2]
            ax.text(mid, ymin, str(year), ha='center', va='bottom')

    plt.title(f"Giá vàng từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}")
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    start_str = input("Enter start date (dd/mm/yyyy) or 'auto' (default 01/01/2026): ").strip()
    end_str   = input("Enter end date (dd/mm/yyyy) or blank for today: ").strip()

    today = datetime.now().date()
    if start_str.lower() == "auto" or start_str == "":
        sd = datetime.strptime("01/01/2026", "%d/%m/%Y").date()
    else:
        sd = datetime.strptime(start_str, "%d/%m/%Y").date()

    if end_str == "":
        ed = today
    else:
        ed = datetime.strptime(end_str, "%d/%m/%Y").date()

    print("\n1) Báo cáo ngày trống trước khi fill")
    report_missing_dates(sd, ed)

    print("\n2) Crawl + fill")
    fill_missing_data(sd, ed, forward_fill=True, bfill_initial=False)

    print("\n3) Báo cáo ngày trống sau khi fill")
    report_missing_dates(sd, ed)

    # Chọn cột để hiển thị
    print("Chọn cột để hiển thị:")
    print(" 1: PNJ_gia_mua")
    print(" 2: PNJ_gia_ban")
    print(" 3: SJC_gia_mua")
    print(" 4: SJC_gia_ban")
    nums = input("Nhập các số (cách nhau bởi dấu phẩy) hoặc 'all' để chọn tất cả: ")
    if nums.strip().lower() == 'all':
        cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]
    else:
        mapping = {'1': 'PNJ_gia_mua', '2': 'PNJ_gia_ban', '3': 'SJC_gia_mua', '4': 'SJC_gia_ban'}
        cols = [mapping[n.strip()] for n in nums.split(',') if n.strip() in mapping]
        if not cols:
            print("Không có lựa chọn hợp lệ, sử dụng mặc định cả 4 cột.")
            cols = ["PNJ_gia_mua", "PNJ_gia_ban", "SJC_gia_mua", "SJC_gia_ban"]

    # Vẽ biểu đồ với cột đã chọn
    visualize(sd, ed, cols)

if __name__ == '__main__':
    main()
