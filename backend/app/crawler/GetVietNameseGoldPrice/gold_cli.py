from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

import app.crawler.GetVietNameseGoldPrice.Update_gia_vang as ug
import app.crawler.GetVietNameseGoldPrice.Update_final_uso_usd as uf
import app.crawler.GetVietNameseGoldPrice.merge_outputs as mo


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "gold_cli.json"
DATE_HINT = "dd/mm/YYYY (vd: 26/03/2026) hoặc YYYY-mm-dd hoặc 'today'"

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


@dataclass(frozen=True)
class BackfillStats:
    start: date
    end: date
    filled_cells: int
    missing_before: int
    missing_after: int


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


def _load_config(config_path: str | None) -> dict:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = dict(DEFAULT_CONFIG)

    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Config file must contain a JSON object: {path}")
        config.update(raw)

    base_dir = path.parent if path.exists() else ROOT_DIR
    for key in ("csv_path", "xauusd_cache_path", "backup_csv_path", "log_dir", "lock_path"):
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
        self._primary.flush()
        self._mirror.flush()

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
        dates = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce").dropna()
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
    xau_path = Path(xauusd_cache_path)

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
        gold_csv=Path(str(config["csv_path"])),
        xauusd_cache_csv=Path(str(config["xauusd_cache_path"])),
        usd_vnd_cache_csv=Path(str(config["usd_vnd_cache_path"])),
        final_uso_csv=Path(str(config["final_uso_csv"])),
        vn_gold_usd_oz_csv=Path(str(config["vn_gold_usd_oz_csv"])),
        final_uso_usd_with_vn_gold_usd_oz_csv=Path(str(config["final_uso_usd_with_vn_gold_usd_oz_csv"])),
        final_uso_usd_with_vn_gold_usd_oz_imputed_csv=Path(str(config["final_uso_usd_with_vn_gold_usd_oz_imputed_csv"])),
        final_uso_with_vn_gold_vnd_thousand_imputed_csv=Path(str(config["final_uso_with_vn_gold_vnd_thousand_imputed_csv"])),
    )
    outputs = mo.build_all(paths)
    for output in outputs:
        print(f"Wrote: {output}")
    return outputs


def cmd_paths(_args: argparse.Namespace, config: dict) -> None:
    _print_paths(config)


def cmd_config(_args: argparse.Namespace, config: dict) -> None:
    _print_config(config)


def cmd_update(args: argparse.Namespace, config: dict) -> dict:
    start = _parse_date(args.start, default=_parse_date(str(config["default_start_date"])))
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )
    _print_update_summary("Update complete", stats, str(config["csv_path"]))
    return stats


def cmd_backfill_xauusd(args: argparse.Namespace, config: dict) -> BackfillStats:
    start = _parse_date(args.start, default=None) if args.start else None
    end = _parse_date(args.end, default=None) if args.end else None
    stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )
    print(
        "XAUUSD cache refreshed: "
        f"range={stats.start.strftime('%d/%m/%Y')}→{stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={stats.filled_cells}"
    )
    _print_csv_summary(str(config["xauusd_cache_path"]), label="XAUUSD cache")
    return stats


def cmd_update_backfill(args: argparse.Namespace, config: dict) -> dict:
    start = _parse_date(args.start, default=_parse_date(str(config["default_start_date"])))
    end = date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )

    backfill_stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )
    print(
        "Update + XAUUSD cache refresh done: "
        f"range={backfill_stats.start.strftime('%d/%m/%Y')}→{backfill_stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={backfill_stats.filled_cells}"
    )
    _print_update_summary("Update + Backfill", stats, str(config["csv_path"]))
    return stats


def cmd_pipeline(args: argparse.Namespace, config: dict) -> dict:
    start = _parse_date(args.start, default=_parse_date(str(config["default_start_date"])))
    end = date.today()
    forward_fill = _resolve_flag(args.no_forward_fill, bool(config["default_forward_fill"]), invert=True)
    bfill_initial = _resolve_flag(args.bfill_initial, bool(config["default_bfill_initial"]))
    quiet = _resolve_flag(args.quiet, bool(config["quiet"]))
    sleep_seconds = float(config["default_sleep_seconds"]) if args.sleep is None else float(args.sleep)

    stats = run_update(
        start=start,
        end=end,
        config=config,
        forward_fill=forward_fill,
        bfill_initial=bfill_initial,
        quiet=quiet,
        sleep_seconds=sleep_seconds,
    )

    backfill_stats = backfill_xauusd_from_local_cache(
        xauusd_cache_path=str(config["xauusd_cache_path"]),
        start=start,
        end=end,
    )
    print(
        "Pipeline XAUUSD cache refresh done: "
        f"range={backfill_stats.start.strftime('%d/%m/%Y')}→{backfill_stats.end.strftime('%d/%m/%Y')}, "
        f"rows_or_cells={backfill_stats.filled_cells}"
    )

    outputs = build_pipeline_outputs(config)
    print("Pipeline outputs:")
    for output in outputs:
        print(f"- {output}")

    _print_update_summary("Pipeline update", stats, str(config["csv_path"]))
    return {"update": stats, "backfill": backfill_stats, "outputs": outputs}


def cmd_report(args: argparse.Namespace, config: dict) -> None:
    start = _parse_date(args.start, default=_parse_date(str(config["default_start_date"])))
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    ug.report_missing_dates(start, end, csv_path=str(config["csv_path"]), cols=ug.ALL_COLS)


def cmd_update_final_uso(args: argparse.Namespace, config: dict) -> None:
    start = _parse_date(args.start, default=date(2006, 4, 10))
    end = _parse_date(args.end, default=date.today()) if args.end else date.today()
    if start > end:
        raise ValueError("start must be <= end")

    uf.update_csv(start, end, output_path=str(config["final_uso_csv"]))
    print(f"Updated final_uso_usd.csv: {start.strftime('%d/%m/%Y')} -> {end.strftime('%d/%m/%Y')}")


def interactive(config: dict) -> None:
    print("\nGold Updater CLI")
    _print_paths(config)
    print("Nhấn Ctrl+C bất kỳ lúc nào để dừng an toàn (có checkpoint/save).\n")

    while True:
        try:
            print("Chọn tác vụ:")
            print("  1) Update (crawl) theo khoảng ngày")
            print("  2) Refresh XAUUSD cache trong stooq_cache")
            print("  3) Update + refresh XAUUSD cache đến hôm nay")
            print("  4) Pipeline đầy đủ (update + refresh + merge)")
            print("  5) Update final_uso_usd.csv")
            print("  6) Report missing trong khoảng ngày")
            print("  7) In config hiện tại")
            print("  8) In lại đường dẫn file")
            print("  0) Thoát")
            choice = input("Nhập lựa chọn: ").strip()

            if choice == "0":
                return
            if choice == "7":
                _print_config(config)
                continue
            if choice == "8":
                _print_paths(config)
                continue

            if choice in {"1", "2", "3", "4", "5", "6"}:
                start_text = input(f"Start date ({DATE_HINT}) (default {config['default_start_date']}): ").strip()
                start_value = start_text if start_text else None
                end_value = None
                if choice in {"1", "2", "6"}:
                    end_text = input(f"End date ({DATE_HINT}) (blank=today): ").strip()
                    end_value = end_text if end_text else None

            if choice == "1":
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

            if choice == "2":
                start_text = input(f"Backfill start ({DATE_HINT}) (blank=toàn bộ file): ").strip()
                end_text = input(f"Backfill end ({DATE_HINT}) (blank=toàn bộ file): ").strip()
                args = argparse.Namespace(
                    start=start_text if start_text else None,
                    end=end_text if end_text else None,
                )
                cmd_backfill_xauusd(args, config)
                continue

            if choice == "3":
                forward_fill = _prompt_bool("Forward-fill các ngày trống?", default=bool(config["default_forward_fill"]))
                bfill_initial = _prompt_bool("Bfill đầu range (để fill ngày đầu nếu thiếu)?", default=bool(config["default_bfill_initial"]))
                quiet = _prompt_bool("Giảm log (ít in từng ngày)?", default=bool(config["quiet"]))
                sleep_text = input(f"Sleep giữa requests (seconds, default {config['default_sleep_seconds']}): ").strip()
                args = argparse.Namespace(
                    start=start_value,
                    no_forward_fill=not forward_fill,
                    bfill_initial=bfill_initial,
                    sleep=float(sleep_text) if sleep_text else None,
                    quiet=quiet,
                )
                cmd_update_backfill(args, config)
                continue

            if choice == "4":
                forward_fill = _prompt_bool("Forward-fill các ngày trống?", default=bool(config["default_forward_fill"]))
                bfill_initial = _prompt_bool("Bfill đầu range (để fill ngày đầu nếu thiếu)?", default=bool(config["default_bfill_initial"]))
                quiet = _prompt_bool("Giảm log (ít in từng ngày)?", default=bool(config["quiet"]))
                sleep_text = input(f"Sleep giữa requests (seconds, default {config['default_sleep_seconds']}): ").strip()
                args = argparse.Namespace(
                    start=start_value,
                    no_forward_fill=not forward_fill,
                    bfill_initial=bfill_initial,
                    sleep=float(sleep_text) if sleep_text else None,
                    quiet=quiet,
                )
                cmd_pipeline(args, config)
                continue

            if choice == "5":
                args = argparse.Namespace(start=start_value, end=end_value)
                cmd_update_final_uso(args, config)
                continue

            if choice == "6":
                args = argparse.Namespace(start=start_value, end=end_value)
                cmd_report(args, config)
                continue

            print("Lựa chọn không hợp lệ.")

        except KeyboardInterrupt:
            print("\nĐã dừng theo yêu cầu (Ctrl+C).\n")
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gold_cli",
        description="Update/backfill VN gold CSV (PNJ/SJC) + XAUUSD cache.",
    )
    parser.add_argument("--config", default=None, help=f"Path to JSON config file (default: {DEFAULT_CONFIG_PATH})")

    sub = parser.add_subparsers(dest="cmd")

    sp = sub.add_parser("paths", help="Print data file paths")
    sp.set_defaults(func=cmd_paths)

    sp = sub.add_parser("config", help="Print loaded config")
    sp.set_defaults(func=cmd_config)

    sp = sub.add_parser("update", help="Crawl/update VN gold CSV for a date range")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.add_argument("--no-forward-fill", action="store_true", default=None, help="Disable forward-fill")
    sp.add_argument("--bfill-initial", action="store_true", default=None, help="Bfill initial values in range")
    sp.add_argument("--sleep", type=float, default=None, help="Sleep seconds between requests")
    sp.add_argument("--quiet", action="store_true", default=None, help="Less logging")
    sp.set_defaults(func=cmd_update)

    sp = sub.add_parser("backfill-xauusd", help="Refresh the XAUUSD cache in stooq_cache")
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

    sp = sub.add_parser("report", help="Report missing dates/values for a date range")
    sp.add_argument("--start", default=None, help=f"Start date ({DATE_HINT}); default=config")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("final-uso", help="Update the daily final_uso_usd.csv dataset")
    sp.add_argument("--start", default=None, help="Start date (default: 10/04/2006)")
    sp.add_argument("--end", default=None, help=f"End date ({DATE_HINT}); default=today")
    sp.set_defaults(func=cmd_update_final_uso)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    config = _load_config(getattr(args, "config", None))

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
