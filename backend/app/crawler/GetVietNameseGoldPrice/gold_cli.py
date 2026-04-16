from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from app.core.config import settings
import app.crawler.GetVietNameseGoldPrice.build_final_dataset as fd
import app.crawler.GetVietNameseGoldPrice.Update_gia_vang as ug
import app.crawler.GetVietNameseGoldPrice.Update_final_uso_usd as uf
import app.crawler.GetVietNameseGoldPrice.merge_outputs as mo


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "gold_cli.json"
DATE_HINT = "dd/mm/YYYY (vd: 26/03/2026) hoặc YYYY-mm-dd hoặc 'today'"
START_MODE_SELECTED = "selected"
START_MODE_NEAREST_DATA = "nearest-data"

DEFAULT_CONFIG = {
    "csv_path": str(ROOT_DIR / "gia_vang_pnj_sjc.csv"),
    "xauusd_cache_path": str(ROOT_DIR / "stooq_cache" / "xauusd_stooq_d.csv"),
    "usd_vnd_cache_path": str(ROOT_DIR / "stooq_cache" / "usd_vnd_close_yf.csv"),
    "backup_csv_path": str(ROOT_DIR / "gia_vang_pnj_sjc.bak.csv"),
    "log_dir": str(ROOT_DIR / "logs"),
    "lock_path": str(ROOT_DIR / "gia_vang_pnj_sjc.lock"),
    "default_start_date": "26/03/2026",
    "default_forward_fill": True,
    "default_bfill_initial": False,
    "default_sleep_seconds": 0.15,
    "checkpoint_every": 200,
    "progress_every": 50,
    "quiet": False,
    "final_uso_csv": str(ROOT_DIR / "final_uso_usd.csv"),
    "vn_gold_usd_oz_csv": str(ROOT_DIR / "gia_vang_pnj_sjc_usd_oz.csv"),
    "final_uso_usd_with_vn_gold_usd_oz_csv": str(ROOT_DIR / "final_uso_usd_with_vn_gold_usd_oz.csv"),
    "final_uso_usd_with_vn_gold_usd_oz_imputed_csv": str(ROOT_DIR / "final_uso_usd_with_vn_gold_usd_oz_imputed.csv"),
    "final_uso_with_vn_gold_vnd_thousand_imputed_csv": str(ROOT_DIR / "final_uso_with_vn_gold_vnd_thousand_imputed.csv"),
}

INTERACTIVE_TASK_MENU = [
    ("1", "Dataset Report", "show missing dates and file coverage against today"),
    ("7", "Build ML training dataset", "run the full chain and rebuild final_dataset.csv"),
    ("2", "Update Vietnamese gold", "refresh PNJ/SJC, cache, and output files"),
    ("3", "Update world gold and market dataset", "refresh XAU/USD and rebuild market outputs"),
    ("8", "Print config", "show the loaded JSON config"),
    ("9", "Print paths", "show current file paths"),
    ("0", "Exit", "quit the crawler menu"),
]


@dataclass(frozen=True)
class BackfillStats:
    start: date
    end: date
    filled_cells: int
    missing_before: int
    missing_after: int


@dataclass(frozen=True)
class CsvAuditResult:
    scope: str
    path: Path
    status_kind: str
    status_text: str
    rows: int | None = None
    columns: int | None = None
    date_column: str | None = None
    first_date: date | None = None
    last_date: date | None = None
    unique_dates: int | None = None
    duplicate_date_rows: int | None = None
    calendar_gaps: int | None = None
    freshness_days_behind: int | None = None
    missing_cells: int | None = None
    all_nan_rows: int | None = None
    empty_columns: int | None = None
    missing_dates_preview: tuple[date, ...] = ()


def _parse_date(text: str, *, default: date | None = None) -> date:
    value = (text or "").strip()
    if not value:
        if default is None:
            raise ValueError("Missing date")
        return default

    low = value.lower()
    if low in {"today", "now", "homnay", "hôm nay", "hn"}:
        return date.today()

    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue

    raise ValueError(f"Invalid date: '{text}'. Expected {DATE_HINT}.")


def _resolve_path(value: str | None, base_dir: Path) -> str:
    if value is None or str(value).strip() == "":
        return ""
    path = Path(str(value))
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return str(path)


def _resolve_crawler_path(value: str | None) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return (ROOT_DIR / path).resolve()


def _load_config(config_path: str | None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = dict(DEFAULT_CONFIG)

    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Config file must contain a JSON object: {path}")
        config.update(raw)

    base_dir = path.parent if path.exists() else ROOT_DIR
    for key in (
        "csv_path",
        "xauusd_cache_path",
        "backup_csv_path",
        "log_dir",
        "lock_path",
        "final_uso_csv",
        "vn_gold_usd_oz_csv",
        "final_uso_usd_with_vn_gold_usd_oz_csv",
        "final_uso_usd_with_vn_gold_usd_oz_imputed_csv",
        "final_uso_with_vn_gold_vnd_thousand_imputed_csv",
    ):
        config[key] = _resolve_path(config.get(key), base_dir)

    config["default_start_date"] = str(config.get("default_start_date", DEFAULT_CONFIG["default_start_date"]))
    config["default_forward_fill"] = bool(config.get("default_forward_fill", True))
    config["default_bfill_initial"] = bool(config.get("default_bfill_initial", False))
    config["default_sleep_seconds"] = float(config.get("default_sleep_seconds", 0.15))
    config["checkpoint_every"] = int(config.get("checkpoint_every", 200))
    config["progress_every"] = int(config.get("progress_every", 50))
    config["quiet"] = bool(config.get("quiet", False))
    config["config_path"] = str(path)
    return config


def _resolve_flag(flag_value, default_value: bool, *, invert: bool = False) -> bool:
    if flag_value is None:
        return default_value
    return (not bool(flag_value)) if invert else bool(flag_value)


def _emit_progress(percent: int, message: str) -> None:
    percent = max(0, min(100, int(percent)))
    print(f"Progress: {percent}% - {message}")


def _load_csv_date_floor(csv_path: str) -> date | None:
    path = Path(csv_path)
    if not path.exists():
        return None

    try:
        frame = pd.read_csv(path)
    except Exception:
        return None

    date_column = None
    if "Date" in frame.columns:
        date_column = "Date"
    elif "Ngày" in frame.columns:
        date_column = "Ngày"

    if not date_column:
        return None

    dates = pd.to_datetime(frame[date_column], dayfirst=True, errors="coerce").dropna()
    if dates.empty:
        return None

    return dates.min().date()


def _resolve_start_for_task(task_name: str, start_text: str | None, *, config: dict, default_start: str, start_mode: str) -> date:
    requested_start = _parse_date(start_text or "", default=_parse_date(default_start))
    if start_mode != START_MODE_NEAREST_DATA:
        return requested_start

    floor_path: str | None = None
    if task_name in {"update", "report", "update-backfill", "pipeline"}:
        floor_path = str(config["csv_path"])
    elif task_name == "backfill-xauusd":
        floor_path = str(config["xauusd_cache_path"])
    elif task_name == "final-uso":
        floor_path = str(config["final_uso_csv"])
    elif task_name == "final-dataset":
        floor_path = str(config["csv_path"])

    if not floor_path:
        return requested_start

    floor_date = _load_csv_date_floor(floor_path)
    if floor_date and requested_start < floor_date:
        print(
            "Start mode nearest-data: clamping start from "
            f"{requested_start.strftime('%d/%m/%Y')} to {floor_date.strftime('%d/%m/%Y')} "
            f"based on {floor_path}"
        )
        return floor_date

    return requested_start


class TeeTextIO(io.TextIOBase):
    def __init__(self, primary, mirror):
        self._primary = primary
        self._mirror = mirror

    def write(self, text):
        self._primary.write(text)
        self._mirror.write(text)
        self.flush()
        return len(text)

    def flush(self):
        try:
            self._primary.flush()
        except ValueError:
            pass
        try:
            self._mirror.flush()
        except ValueError:
            pass

    def isatty(self):
        return bool(getattr(self._primary, "isatty", lambda: False)())

    def __getattr__(self, name):
        return getattr(self._primary, name)


@contextlib.contextmanager
def acquire_run_lock(lock_path: str):
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    for _ in range(2):
        if path.exists():
            try:
                info = json.loads(path.read_text(encoding="utf-8"))
                pid = int(info.get("pid") or 0)
                if pid > 0:
                    try:
                        os.kill(pid, 0)
                        raise RuntimeError(f"Another run is already active (pid={pid}).")
                    except OSError:
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                else:
                    path.unlink(missing_ok=True)
            except RuntimeError:
                raise
            except Exception:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "pid": os.getpid(),
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "argv": sys.argv,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
                f.write("\n")
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError(f"Could not acquire lock file: {path}")

    try:
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


@contextlib.contextmanager
def tee_output(log_path: str):
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as log_handle:
        log_handle.write(f"\n--- {datetime.now().isoformat(timespec='seconds')} ---\n")
        log_handle.flush()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = TeeTextIO(old_stdout, log_handle)
        sys.stderr = TeeTextIO(old_stderr, log_handle)
        try:
            yield path
        finally:
            try:
                sys.stdout.flush()
                sys.stderr.flush()
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr


def _print_paths(config: dict) -> None:
    print("Data paths:")
    print(f"- Config file:   {config['config_path']}")
    print(f"- VN gold CSV:   {config['csv_path']}")
    print(f"- XAUUSD cache:  {config['xauusd_cache_path']}")
    print(f"- USD/VND cache: {config['usd_vnd_cache_path']}")
    print(f"- Backup CSV:    {config['backup_csv_path']}")
    print(f"- VN gold USD/OZ: {config['vn_gold_usd_oz_csv']}")
    print(f"- Final USO USD/OZ merged: {config['final_uso_usd_with_vn_gold_usd_oz_csv']}")
    print(f"- Final USO USD/OZ imputed: {config['final_uso_usd_with_vn_gold_usd_oz_imputed_csv']}")
    print(f"- Final USO VND/1000: {config['final_uso_with_vn_gold_vnd_thousand_imputed_csv']}")
    print(f"- Log dir:       {config['log_dir']}")
    print(f"- Lock file:     {config['lock_path']}")


def _print_config(config: dict) -> None:
    print("Current config:")
    for key in [
        "config_path",
        "csv_path",
        "xauusd_cache_path",
        "usd_vnd_cache_path",
        "backup_csv_path",
        "final_uso_csv",
        "vn_gold_usd_oz_csv",
        "final_uso_usd_with_vn_gold_usd_oz_csv",
        "final_uso_usd_with_vn_gold_usd_oz_imputed_csv",
        "final_uso_with_vn_gold_vnd_thousand_imputed_csv",
        "log_dir",
        "lock_path",
        "default_start_date",
        "default_forward_fill",
        "default_bfill_initial",
        "default_sleep_seconds",
        "checkpoint_every",
        "progress_every",
        "quiet",
    ]:
        print(f"- {key}: {config.get(key)}")


def _print_csv_summary(csv_path: str, *, label: str = "CSV summary") -> None:
    path = Path(csv_path)
    if not path.exists():
        print(f"{label}: missing file {path}")
        return

    df = pd.read_csv(path)
    date_col = "Ngày" if "Ngày" in df.columns else ("Date" if "Date" in df.columns else None)
    if date_col is not None:
        sample_values = df[date_col].dropna().astype(str).head(20)
        use_dayfirst = any("/" in value for value in sample_values)
        dates = pd.to_datetime(df[date_col], dayfirst=use_dayfirst, errors="coerce").dropna()
        if len(dates):
            print(f"{label}: rows={len(df)}, range={dates.min().date()} -> {dates.max().date()}")
        else:
            print(f"{label}: rows={len(df)}, range=unknown")
    else:
        print(f"{label}: rows={len(df)}")

    missing = (df.isna().mean() * 100).sort_values(ascending=False)
    print(f"{label}: missing% by column")
    for col, pct in missing.items():
        if col == date_col:
            continue
        print(f"  - {col}: {pct:.3f}%")


def _load_csv_date_index(csv_path: Path) -> tuple[pd.DatetimeIndex | None, str | None]:
    if not csv_path.exists():
        return None, None

    try:
        frame = pd.read_csv(csv_path)
    except Exception:
        return None, None

    date_col = None
    use_dayfirst = False
    if "Date" in frame.columns:
        date_col = "Date"
    elif "Ngày" in frame.columns:
        date_col = "Ngày"
        use_dayfirst = True

    if not date_col:
        return None, None

    dates = pd.to_datetime(frame[date_col], dayfirst=use_dayfirst, errors="coerce").dropna()
    if dates.empty:
        return None, date_col

    normalized = pd.DatetimeIndex(sorted({timestamp.normalize() for timestamp in dates.tolist()}))
    return normalized, date_col


def _find_report_start_date(config: dict) -> date:
    earliest: date | None = None
    for path in _collect_report_targets(config):
        date_index, _ = _load_csv_date_index(path)
        if date_index is None or len(date_index) == 0:
            continue

        candidate = date_index.min().date()
        if earliest is None or candidate < earliest:
            earliest = candidate

    if earliest is not None:
        return earliest

    return _parse_date(str(config["default_start_date"]), default=date.today())


def _classify_report_scope(path: Path) -> str:
    lowered_name = path.name.lower()
    if "bak" in lowered_name or "copy" in lowered_name:
        return "Dataset snapshots"
    if "stooq_cache" in path.parts or "cache" in lowered_name:
        return "Cache files"
    return "Primary data files"


def _collect_report_targets(config: dict) -> list[Path]:
    roots = [
        Path(config["csv_path"]).expanduser().parent,
        Path(settings.LOCAL_DATASET_PATH).expanduser().parent,
    ]

    targets: list[Path] = []
    seen: set[Path] = set()

    for root in roots:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*.csv")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            targets.append(path)

    return targets


def _extract_date_summary(frame: pd.DataFrame) -> tuple[str | None, pd.DatetimeIndex | None, int, bool]:
    candidate_columns: list[object] = []
    for column in frame.columns:
        normalized = str(column).strip().lower()
        if normalized in {"date", "ngay", "ngày", "datetime", "timestamp"} or "date" in normalized or "ngay" in normalized or "ngày" in normalized:
            candidate_columns.append(column)

    if not candidate_columns and len(frame.columns):
        candidate_columns.append(frame.columns[0])

    best_date_column: str | None = None
    best_dates: pd.Series | None = None
    best_valid_count = 0
    best_dayfirst = False

    for column in candidate_columns:
        series = frame[column]
        sample_values = series.dropna().astype(str).head(20)
        prefer_dayfirst = False
        if not sample_values.empty:
            if any(
                len(value) >= 10
                and value[0:4].isdigit()
                and value[4] in {"-", "/"}
                and value[5:7].isdigit()
                and value[7] in {"-", "/"}
                for value in sample_values
            ):
                prefer_dayfirst = False
            elif any("/" in value for value in sample_values):
                prefer_dayfirst = True

        for index, dayfirst in enumerate((prefer_dayfirst, not prefer_dayfirst)):
            parsed = pd.to_datetime(series, dayfirst=dayfirst, errors="coerce")
            valid_count = int(parsed.notna().sum())
            if valid_count > best_valid_count:
                best_date_column = str(column)
                best_dates = parsed.dropna()
                best_valid_count = valid_count
                best_dayfirst = dayfirst
            if index == 0 and valid_count > 0:
                break

    if best_date_column is None or best_dates is None or best_valid_count == 0:
        return None, None, 0, False

    normalized = pd.DatetimeIndex(sorted({timestamp.normalize() for timestamp in best_dates.tolist()}))
    return best_date_column, normalized, best_valid_count, best_dayfirst


def _audit_csv_file(path: Path) -> CsvAuditResult:
    scope = _classify_report_scope(path)

    if not path.exists():
        return CsvAuditResult(
            scope=scope,
            path=path,
            status_kind="missing",
            status_text="missing file",
        )

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return CsvAuditResult(
            scope=scope,
            path=path,
            status_kind="unreadable",
            status_text=f"unreadable ({exc})",
        )

    rows = int(frame.shape[0])
    columns = int(frame.shape[1])
    missing_cells = int(frame.isna().sum().sum())
    all_nan_rows = int(frame.isna().all(axis=1).sum())
    empty_columns = int(frame.isna().all(axis=0).sum())

    date_column, date_index, parsed_count, _dayfirst = _extract_date_summary(frame)
    if date_column is None or date_index is None:
        status_text = "no date column detected"
        if missing_cells or all_nan_rows:
            status_text = f"{status_text}; missing cells={missing_cells}, all-NaN rows={all_nan_rows}"
        return CsvAuditResult(
            scope=scope,
            path=path,
            status_kind="no-date",
            status_text=status_text,
            rows=rows,
            columns=columns,
            missing_cells=missing_cells,
            all_nan_rows=all_nan_rows,
            empty_columns=empty_columns,
        )

    first_date = date_index.min().date()
    last_date = date_index.max().date()
    freshness_days_behind = max(0, (date.today() - last_date).days)
    expected_dates = pd.date_range(start=pd.Timestamp(first_date), end=pd.Timestamp(last_date), freq="D")
    missing_dates = expected_dates.difference(date_index)
    calendar_gaps = int(len(missing_dates))
    duplicate_date_rows = int(parsed_count - len(date_index))
    missing_dates_preview = tuple(timestamp.date() for timestamp in missing_dates[:10])

    lowered_name = path.name.lower()
    is_snapshot = "bak" in lowered_name or "copy" in lowered_name
    is_cache = scope == "Cache files"

    issue_parts: list[str] = []
    if missing_cells:
        issue_parts.append(f"missing cells={missing_cells}")
    if all_nan_rows:
        issue_parts.append(f"all-NaN rows={all_nan_rows}")
    if duplicate_date_rows:
        issue_parts.append(f"duplicate date rows={duplicate_date_rows}")
    if calendar_gaps and not is_cache:
        issue_parts.append(f"calendar gaps={calendar_gaps}")

    if issue_parts:
        status_kind = "needs-attention"
        status_text = "; ".join(issue_parts)
    elif is_snapshot:
        status_kind = "snapshot"
        status_text = "backup/copy snapshot"
    elif not is_cache and freshness_days_behind > 0:
        status_kind = "stale"
        status_text = f"latest data is {freshness_days_behind} day(s) behind today"
    else:
        status_kind = "ok"
        status_text = "complete and current"

    return CsvAuditResult(
        scope=scope,
        path=path,
        status_kind=status_kind,
        status_text=status_text,
        rows=rows,
        columns=columns,
        date_column=date_column,
        first_date=first_date,
        last_date=last_date,
        unique_dates=int(len(date_index)),
        duplicate_date_rows=duplicate_date_rows,
        calendar_gaps=calendar_gaps,
        freshness_days_behind=freshness_days_behind,
        missing_cells=missing_cells,
        all_nan_rows=all_nan_rows,
        empty_columns=empty_columns,
        missing_dates_preview=missing_dates_preview,
    )


def _format_optional_int(value: int | None) -> str:
    return "n/a" if value is None else str(value)


def _format_csv_audit_result(result: CsvAuditResult) -> list[str]:
    lines = [f"- {result.path}"]
    lines.append(f"  status: {result.status_kind} ({result.status_text})")
    lines.append(f"  scope: {result.scope}")
    lines.append(f"  rows: {_format_optional_int(result.rows)}")
    lines.append(f"  columns: {_format_optional_int(result.columns)}")
    lines.append(f"  date column: {result.date_column or 'n/a'}")

    if result.first_date is not None and result.last_date is not None:
        lines.append(f"  data range: {result.first_date.isoformat()} -> {result.last_date.isoformat()}")
        lines.append(f"  freshness: {('current' if result.freshness_days_behind == 0 else f'{result.freshness_days_behind} day(s) behind today')}")
        lines.append(f"  unique dates: {_format_optional_int(result.unique_dates)}")
        lines.append(f"  calendar gaps: {_format_optional_int(result.calendar_gaps)}")
        lines.append(f"  duplicate date rows: {_format_optional_int(result.duplicate_date_rows)}")
        lines.append(f"  missing cells: {_format_optional_int(result.missing_cells)}")
        lines.append(f"  all-NaN rows: {_format_optional_int(result.all_nan_rows)}")
        lines.append(f"  empty columns: {_format_optional_int(result.empty_columns)}")
        if result.missing_dates_preview:
            preview = ", ".join(timestamp.isoformat() for timestamp in result.missing_dates_preview)
            lines.append(f"  missing date preview: {preview}")
    else:
        lines.append("  data range: n/a")
        lines.append("  freshness: n/a")
        lines.append(f"  unique dates: {_format_optional_int(result.unique_dates)}")
        lines.append(f"  calendar gaps: {_format_optional_int(result.calendar_gaps)}")
        lines.append(f"  duplicate date rows: {_format_optional_int(result.duplicate_date_rows)}")
        lines.append(f"  missing cells: {_format_optional_int(result.missing_cells)}")
        lines.append(f"  all-NaN rows: {_format_optional_int(result.all_nan_rows)}")
        lines.append(f"  empty columns: {_format_optional_int(result.empty_columns)}")

    return lines


def _render_csv_coverage_lines(
    label: str,
    csv_path: Path,
    *,
    reference_start: date | None = None,
    reference_end: date | None = None,
    show_missing_dates: bool = False,
) -> list[str]:
    lines = [f"- {label}: {csv_path}"]
    if not csv_path.exists():
        lines.append("  status: missing")
        return lines

    try:
        frame = pd.read_csv(csv_path)
    except Exception as exc:
        lines.append(f"  status: unreadable ({exc})")
        return lines

    lines.append(f"  rows: {len(frame)}")
    date_index, date_col = _load_csv_date_index(csv_path)
    if date_index is None or date_col is None:
        lines.append("  date column: not available")
        return lines

    first_date = date_index.min().date()
    last_date = date_index.max().date()
    lines.append(f"  date column: {date_col}")
    lines.append(f"  range: {first_date} -> {last_date}")

    if reference_end is not None:
        lines.append(f"  behind today: {max(0, (reference_end - last_date).days)} day(s)")

    if show_missing_dates and reference_start is not None and reference_end is not None:
        expected = pd.date_range(start=pd.Timestamp(reference_start), end=pd.Timestamp(reference_end), freq="D")
        missing = expected.difference(date_index)
        lines.append(f"  missing dates in range: {len(missing)}")
        if len(missing):
            preview = ", ".join(timestamp.strftime("%Y-%m-%d") for timestamp in missing[:10])
            if len(missing) > 10:
                preview += " ..."
            lines.append(f"  missing preview: {preview}")

    return lines


def _build_dataset_report_text(config: dict, *, start: date, end: date) -> str:
    audit_targets = _collect_report_targets(config)
    audit_results = [_audit_csv_file(path) for path in audit_targets]
    scope_counts = Counter(result.scope for result in audit_results)
    status_counts = Counter(result.status_kind for result in audit_results)

    report_lines = [
        "Crawler audit report",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"Current day: {date.today().isoformat()}",
        f"Requested window: {start.strftime('%d/%m/%Y')} -> {end.strftime('%d/%m/%Y')}",
        "Scope: every CSV data file is checked individually. Cache files may skip non-trading days, so calendar gaps are informational for those files.",
        "",
        "Summary:",
        f"- Files audited: {len(audit_results)}",
        f"- Primary data files: {scope_counts.get('Primary data files', 0)}",
        f"- Cache files: {scope_counts.get('Cache files', 0)}",
        f"- Dataset snapshots: {scope_counts.get('Dataset snapshots', 0)}",
        f"- Ok: {status_counts.get('ok', 0)}",
        f"- Stale: {status_counts.get('stale', 0)}",
        f"- Needs attention: {status_counts.get('needs-attention', 0)}",
        f"- Snapshot: {status_counts.get('snapshot', 0)}",
        f"- Missing: {status_counts.get('missing', 0)}",
        f"- Unreadable: {status_counts.get('unreadable', 0)}",
        f"- Empty: {status_counts.get('empty', 0)}",
        f"- No date column: {status_counts.get('no-date', 0)}",
        "",
    ]

    grouped_results: dict[str, list[CsvAuditResult]] = {
        "Primary data files": [],
        "Cache files": [],
        "Dataset snapshots": [],
    }
    for result in audit_results:
        grouped_results.setdefault(result.scope, []).append(result)

    for scope in ("Primary data files", "Cache files", "Dataset snapshots"):
        results = grouped_results.get(scope, [])
        if not results:
            continue

        report_lines.append(f"{scope}:")
        for result in results:
            report_lines.extend(_format_csv_audit_result(result))
            report_lines.append("")

    return "\n".join(report_lines).rstrip() + "\n"


def _resolve_report_output_path(config: dict, start: date, end: date, report_output: str | None) -> Path:
    if report_output:
        path = Path(report_output).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (Path(config["log_dir"]) / "reports" / f"crawler_report_{start:%Y%m%d}_{end:%Y%m%d}_{timestamp}.txt").resolve()


def _prompt_bool(prompt: str, *, default: bool) -> bool:
    default_label = "Y" if default else "N"
    while True:
        value = input(f"{prompt} [Y/N] (default {default_label}): ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes", "1"}:
            return True
        if value in {"n", "no", "0"}:
            return False
        print("Please enter Y or N.")


def backfill_xauusd_from_local_cache(
    *,
    xauusd_cache_path: str,
    start: date | None = None,
    end: date | None = None,
    max_file_age_hours: float = 24.0,
) -> BackfillStats:
    xau_path = _resolve_crawler_path(xauusd_cache_path)

    if start is None:
        start = date(2006, 1, 1)
    if end is None:
        end = date.today()
    if start > end:
        raise ValueError("start must be <= end")

    # Refresh/seed the cache file at the configured location.
    ug.load_xauusd_ohlc_cache(start, end, cache_path=str(xau_path), max_file_age_hours=max_file_age_hours)

    if not xau_path.exists():
        raise FileNotFoundError(f"Missing XAUUSD cache: {xau_path}")

    df = pd.read_csv(xau_path)
    if "Date" not in df.columns:
        raise ValueError(f"Missing 'Date' in {xau_path}. Columns={list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).copy().sort_values("Date")
    df = df.drop_duplicates(subset=["Date"], keep="last")

    if start is not None:
        df = df[df["Date"].dt.date >= start]
    if end is not None:
        df = df[df["Date"].dt.date <= end]

    non_null = int(df[[c for c in ["Open", "High", "Low", "Close"] if c in df.columns]].notna().sum().sum()) if not df.empty else 0
    return BackfillStats(
        start=start,
        end=end,
        filled_cells=non_null,
        missing_before=0,
        missing_after=0,
    )


def run_update(
    *,
    start: date,
    end: date,
    config: dict,
    forward_fill: bool,
    bfill_initial: bool,
    quiet: bool,
    sleep_seconds: float,
) -> dict:
    return ug.fill_missing_data(
        start,
        end,
        csv_path=str(config["csv_path"]),
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        backup_csv_path=str(config["backup_csv_path"]),
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        sleep_seconds=sleep_seconds,
        progress_every=int(config["progress_every"]),
        save_every_requests=int(config["checkpoint_every"]),
        verbose=not quiet,
    )


def _print_update_summary(title: str, stats: dict, csv_path: str) -> None:
    print(
        f"{title}: crawled={int(stats.get('crawled_requests', 0))}, "
        f"inserted={int(stats.get('inserted_rows', 0))}, "
        f"updated_rows={int(stats.get('updated_rows', 0))}, "
        f"crawl_filled_cells={int(stats.get('crawl_filled_cells', 0))}, "
        f"forward_fill_cells={int(stats.get('forward_fill_cells', 0))}, "
        f"total_filled={int(stats.get('filled_cells_total', 0))}"
    )
    _print_csv_summary(csv_path, label=title)


def build_pipeline_outputs(config: dict) -> list[Path]:
    paths = mo.MergePaths(
        root_dir=ROOT_DIR,
        gold_csv=_resolve_crawler_path(config["csv_path"]),
        xauusd_cache_csv=_resolve_crawler_path(config["xauusd_cache_path"]),
        usd_vnd_cache_csv=_resolve_crawler_path(config["usd_vnd_cache_path"]),
        final_uso_csv=_resolve_crawler_path(config["final_uso_csv"]),
        vn_gold_usd_oz_csv=_resolve_crawler_path(config["vn_gold_usd_oz_csv"]),
        final_uso_usd_with_vn_gold_usd_oz_csv=_resolve_crawler_path(config["final_uso_usd_with_vn_gold_usd_oz_csv"]),
        final_uso_usd_with_vn_gold_usd_oz_imputed_csv=_resolve_crawler_path(config["final_uso_usd_with_vn_gold_usd_oz_imputed_csv"]),
        final_uso_with_vn_gold_vnd_thousand_imputed_csv=_resolve_crawler_path(config["final_uso_with_vn_gold_vnd_thousand_imputed_csv"]),
    )
    outputs: list[Path] = []

    _emit_progress(84, "Building VN gold USD/OZ merge")
    outputs.append(Path(mo.build_vn_gold_usd_oz(paths)))
    print(f"Wrote: {outputs[-1]}")

    _emit_progress(90, "Building USD/OZ market merge")
    outputs.append(Path(mo.build_final_uso_usd_with_vn_gold_usd_oz(paths)))
    print(f"Wrote: {outputs[-1]}")

    _emit_progress(95, "Imputing merged market dataset")
    outputs.append(Path(mo.build_final_uso_usd_with_vn_gold_usd_oz_imputed(paths)))
    print(f"Wrote: {outputs[-1]}")

    _emit_progress(100, "Writing final VND-thousand market dataset")
    outputs.append(Path(mo.build_final_uso_with_vn_gold_vnd_thousand_imputed(paths)))
    print(f"Wrote: {outputs[-1]}")
    return outputs


def _run_vietnamese_gold_update(
    args: argparse.Namespace,
    config: dict,
    *,
    build_outputs: bool = True,
    emit_start_progress: bool = True,
    emit_completion_progress: bool = True,
) -> dict:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("update", args.start, config=config, default_start=str(config["default_start_date"]), start_mode=start_mode)
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    if emit_start_progress:
        _emit_progress(5, f"Starting Vietnamese gold update from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )

    _emit_progress(70, "Vietnamese gold update complete; refreshing XAUUSD cache")
    backfill_stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )

    outputs: list[Path] = []
    if build_outputs:
        _emit_progress(82, "XAUUSD cache refreshed; building merged outputs")
        outputs = build_pipeline_outputs(config)
        print("Market outputs:")
        for output in outputs:
            print(f"- {output}")

    if emit_completion_progress:
        _emit_progress(100, "Vietnamese gold update complete")
    print(
        "Vietnamese gold cache refreshed: "
        f"range={backfill_stats.start.strftime('%d/%m/%Y')}→{backfill_stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={backfill_stats.filled_cells}"
    )
    _print_update_summary("Update Vietnamese gold", stats, str(config["csv_path"]))
    return {"update": stats, "backfill": backfill_stats, "outputs": outputs}


def _run_world_gold_market_update(
    args: argparse.Namespace,
    config: dict,
    *,
    build_outputs: bool = True,
    emit_start_progress: bool = True,
    emit_completion_progress: bool = True,
) -> dict:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("backfill-xauusd", args.start, config=config, default_start=str(config["default_start_date"]), start_mode=start_mode) if args.start else None
    end = _parse_date(args.end, default=None) if args.end else None

    if emit_start_progress:
        if start is None and end is None:
            _emit_progress(5, "Refreshing world gold cache")
        else:
            start_text = start.strftime('%d/%m/%Y') if start else "full file"
            end_text = end.strftime('%d/%m/%Y') if end else "full file"
            _emit_progress(5, f"Refreshing world gold cache from {start_text} to {end_text}")

    stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )

    outputs: list[Path] = []
    if build_outputs:
        _emit_progress(82, "World gold cache refreshed; building market dataset outputs")
        outputs = build_pipeline_outputs(config)
        print("Market outputs:")
        for output in outputs:
            print(f"- {output}")

    if emit_completion_progress:
        _emit_progress(100, "World gold and market dataset complete")
    print(
        "World gold cache refreshed: "
        f"range={stats.start.strftime('%d/%m/%Y')}→{stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={stats.filled_cells}"
    )
    _print_csv_summary(str(config["xauusd_cache_path"]), label="XAUUSD cache")
    return {"backfill": stats, "outputs": outputs}


def cmd_paths(_args: argparse.Namespace, config: dict) -> None:
    _print_paths(config)


def cmd_config(_args: argparse.Namespace, config: dict) -> None:
    _print_config(config)


def cmd_update(args: argparse.Namespace, config: dict) -> dict:
    result = _run_vietnamese_gold_update(args, config, build_outputs=True)
    return result["update"]


def cmd_backfill_xauusd(args: argparse.Namespace, config: dict) -> BackfillStats:
    result = _run_world_gold_market_update(args, config, build_outputs=True)
    return result["backfill"]


def cmd_update_backfill(args: argparse.Namespace, config: dict) -> dict:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("update-backfill", args.start, config=config, default_start=str(config["default_start_date"]), start_mode=start_mode)
    end = date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    _emit_progress(5, f"Starting raw crawl from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )

    _emit_progress(75, "Raw crawl complete; refreshing XAUUSD cache")
    backfill_stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )
    _emit_progress(100, "Raw crawl and cache refresh complete")
    print(
        "Update + XAUUSD cache refresh done: "
        f"range={backfill_stats.start.strftime('%d/%m/%Y')}→{backfill_stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={backfill_stats.filled_cells}"
    )
    _print_update_summary("Update + Backfill", stats, str(config["csv_path"]))
    return stats


def cmd_pipeline(args: argparse.Namespace, config: dict) -> dict:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("pipeline", args.start, config=config, default_start=str(config["default_start_date"]), start_mode=start_mode)
    end = date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    _emit_progress(5, f"Starting pipeline crawl from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )

    _emit_progress(70, "Pipeline crawl complete; refreshing XAUUSD cache")
    backfill_stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )
    _emit_progress(82, "XAUUSD cache refreshed; building merged outputs")
    print(
        "Pipeline XAUUSD cache refresh done: "
        f"range={backfill_stats.start.strftime('%d/%m/%Y')}→{backfill_stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={backfill_stats.filled_cells}"
    )

    outputs = build_pipeline_outputs(config)
    print("Pipeline outputs:")
    for output in outputs:
        print(f"- {output}")

    _emit_progress(100, "Pipeline complete")
    _print_update_summary("Pipeline update", stats, str(config["csv_path"]))
    return {"update": stats, "backfill": backfill_stats, "outputs": outputs}


def cmd_report(args: argparse.Namespace, config: dict) -> Path:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    default_start = _find_report_start_date(config)
    start = _resolve_start_for_task("report", args.start, config=config, default_start=default_start.strftime("%d/%m/%Y"), start_mode=start_mode)
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    _emit_progress(5, f"Starting audit report from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    report_text = _build_dataset_report_text(config, start=start, end=end)
    report_path = _resolve_report_output_path(config, start, end, getattr(args, "report_output", None))
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report_path.write_text(report_text, encoding="utf-8")

    print(report_text.rstrip())
    print(f"Report file: {report_path}")
    _emit_progress(100, "Audit report complete")
    return report_path


def cmd_update_final_uso(args: argparse.Namespace, config: dict) -> None:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("final-uso", args.start, config=config, default_start="10/04/2006", start_mode=start_mode)
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    if start > end:
        raise ValueError("start must be <= end")

    _emit_progress(10, f"Building final_uso_usd.csv from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    uf.update_csv(start, end, output_path=str(config["final_uso_csv"]))
    _emit_progress(100, "final_uso_usd.csv complete")
    print(f"Updated final_uso_usd.csv: {start.strftime('%d/%m/%Y')} -> {end.strftime('%d/%m/%Y')}")


def cmd_final_dataset(args: argparse.Namespace, config: dict) -> None:
    start_mode = getattr(args, "start_mode", START_MODE_SELECTED)
    start = _resolve_start_for_task("final-dataset", args.start, config=config, default_start="01/01/2009", start_mode=start_mode)
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    if start > end:
        raise ValueError("start must be <= end")

    _emit_progress(5, f"Running full ML training dataset flow from {start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}")
    _run_vietnamese_gold_update(args, config, build_outputs=False, emit_start_progress=False, emit_completion_progress=False)
    _emit_progress(55, "Vietnamese gold update complete; refreshing world gold and market dataset")
    _run_world_gold_market_update(args, config, build_outputs=False, emit_start_progress=False, emit_completion_progress=False)
    _emit_progress(80, "World gold update complete; building market outputs")
    outputs = build_pipeline_outputs(config)
    print("Market outputs:")
    for output in outputs:
        print(f"- {output}")
    _emit_progress(95, "Building final_dataset.csv")
    output_path = fd.build_final_dataset(
        gold_csv_path=Path(str(config["csv_path"])),
        start_date=start,
        end_date=end,
    )
    _emit_progress(100, "final_dataset.csv complete")
    print(f"Built final_dataset.csv: {start.strftime('%d/%m/%Y')} -> {end.strftime('%d/%m/%Y')}")
    _print_csv_summary(str(output_path), label="final_dataset")


def interactive(config: dict) -> None:
    print("\nGold Updater CLI")
    _print_paths(config)
    print("Nhấn Ctrl+C bất kỳ lúc nào để dừng an toàn (có checkpoint/save).\n")

    start_prompt_defaults = {
        "1": "blank=từ dữ liệu sớm nhất",
        "2": str(config["default_start_date"]),
        "3": "blank=toàn bộ file",
        "7": "01/01/2009",
    }
    choices_with_end = {"1", "2", "3", "7"}

    while True:
        try:
            print("Chọn tác vụ:")
            for key, title, description in INTERACTIVE_TASK_MENU:
                print(f"  {key}) {title} - {description}")
            choice = input("Nhập lựa chọn: ").strip()

            if choice == "0":
                return
            if choice == "8":
                _print_config(config)
                continue
            if choice == "9":
                _print_paths(config)
                continue

            if choice in {"1", "2", "3", "7"}:
                default_start_text = start_prompt_defaults.get(choice, config["default_start_date"])
                start_text = input(f"Start date ({DATE_HINT}) (default {default_start_text}): ").strip()
                start_value = start_text if start_text else None
                end_value = None
                if choice in choices_with_end:
                    end_text = input(f"End date ({DATE_HINT}) (blank=today): ").strip()
                    end_value = end_text if end_text else None

            if choice == "1":
                args = argparse.Namespace(start=start_value, end=end_value)
                cmd_report(args, config)
                continue

            if choice == "7":
                forward_fill = _prompt_bool("Forward-fill các ngày trống?", default=bool(config["default_forward_fill"]))
                bfill_initial = _prompt_bool("Bfill đầu range (để fill ngày đầu nếu thiếu)?", default=bool(config["default_bfill_initial"]))
                quiet = _prompt_bool("Giảm log (ít in từng ngày)?", default=bool(config["quiet"]))
                sleep_text = input(f"Sleep giữa requests (seconds, default {config['default_sleep_seconds']}): ").strip()
                args = argparse.Namespace(
                    start=start_value,
                    end=end_value,
                    no_forward_fill=not forward_fill,
                    bfill_initial=bfill_initial,
                    sleep=float(sleep_text) if sleep_text else None,
                    quiet=quiet,
                )
                cmd_final_dataset(args, config)
                continue

            if choice == "2":
                forward_fill = _prompt_bool("Forward-fill các ngày trống?", default=bool(config["default_forward_fill"]))
                bfill_initial = _prompt_bool("Bfill đầu range (để fill ngày đầu nếu thiếu)?", default=bool(config["default_bfill_initial"]))
                quiet = _prompt_bool("Giảm log (ít in từng ngày)?", default=bool(config["quiet"]))
                sleep_text = input(f"Sleep giữa requests (seconds, default {config['default_sleep_seconds']}): ").strip()
                args = argparse.Namespace(
                    start=start_value,
                    end=end_value,
                    no_forward_fill=not forward_fill,
                    bfill_initial=bfill_initial,
                    sleep=float(sleep_text) if sleep_text else None,
                    quiet=quiet,
                )
                cmd_update(args, config)
                continue

            if choice == "3":
                args = argparse.Namespace(
                    start=start_value,
                    end=end_value,
                )
                cmd_backfill_xauusd(args, config)
                continue

            print("Lựa chọn không hợp lệ.")

        except KeyboardInterrupt:
            print("\nĐã dừng theo yêu cầu (Ctrl+C).\n")
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gold_cli",
        description="Generate dataset reports and run the composite gold/cache/market/final-dataset crawler flows.",
    )
    parser.add_argument("--config", default=None, help=f"Path to JSON config file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--log-file", default=None, help="Write crawler output to this log file instead of the daily shared log.")
    parser.add_argument(
        "--start-mode",
        default=START_MODE_SELECTED,
        choices=[START_MODE_SELECTED, START_MODE_NEAREST_DATA],
        help="How to interpret the provided start date.",
    )

    sub = parser.add_subparsers(dest="cmd")

    sp = sub.add_parser("paths", help="Print data file paths")
    sp.set_defaults(func=cmd_paths)

    sp = sub.add_parser("config", help="Print loaded config")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("update", help="Update Vietnamese gold data and downstream outputs")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.add_argument("--no-forward-fill", action="store_true", default=None, help="Disable forward-fill")
    sp.add_argument("--bfill-initial", action="store_true", default=None, help="Bfill initial values in range")
    sp.add_argument("--sleep", type=float, default=None, help="Sleep seconds between requests")
    sp.add_argument("--quiet", action="store_true", default=None, help="Less logging")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("backfill-xauusd", help="Update world gold data and market dataset outputs")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=full file")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=full file")
    sp.set_defaults(func=cmd_backfill_xauusd)

    sp = sub.add_parser("update-backfill", help="Update gold CSV then refresh XAUUSD cache")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--no-forward-fill", action="store_true", default=None, help="Disable forward-fill")
    sp.add_argument("--bfill-initial", action="store_true", default=None, help="Bfill initial values in range")
    sp.add_argument("--sleep", type=float, default=None, help="Sleep seconds between requests")
    sp.add_argument("--quiet", action="store_true", default=None, help="Less logging")
    sp.set_defaults(func=cmd_update_backfill)

    sp = sub.add_parser("pipeline", help="Update gold CSV, refresh XAUUSD cache, and build all merged outputs")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--no-forward-fill", action="store_true", default=None, help="Disable forward-fill")
    sp.add_argument("--bfill-initial", action="store_true", default=None, help="Bfill initial values in range")
    sp.add_argument("--sleep", type=float, default=None, help="Sleep seconds between requests")
    sp.add_argument("--quiet", action="store_true", default=None, help="Less logging")
    sp.set_defaults(func=cmd_pipeline)

    sp = sub.add_parser("report", help="Audit all CSV data files and caches with per-file range/status")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.add_argument("--report-output", default=None, help="Write the audit report artifact to this path")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("final-uso", help="Update the daily final_uso_usd.csv dataset")
    sp.add_argument("--start", default=None, help="Start date (default: 10/04/2006)")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.set_defaults(func=cmd_update_final_uso)

    sp = sub.add_parser("final-dataset", help="Run the full crawler chain and build backend/dataset/final_dataset.csv")
    sp.add_argument("--start", default=None, help="Start date (default: 01/01/2009)")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.set_defaults(func=cmd_final_dataset)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _load_config(getattr(args, "config", None))

    if getattr(args, "log_file", None):
        log_path = Path(args.log_file).expanduser()
    else:
        log_path = Path(config["log_dir"]) / f"run_{date.today():%Y%m%d}.log"

    try:
        with acquire_run_lock(str(config["lock_path"])), tee_output(str(log_path)):
            print(f"Run started: {datetime.now().isoformat(timespec='seconds')}")
            print(f"Config file: {config['config_path']}")
            print(f"Log file: {log_path}")

            if not getattr(args, "cmd", None):
                interactive(config)
            else:
                args.func(args, config)
        return 0
    except RuntimeError as exc:
        print(str(exc))
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C).\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
