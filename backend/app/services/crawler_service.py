from __future__ import annotations

import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import CrawlerExecutionError
from app.db.models import CrawlerRun, User
from app.db.session import SessionLocal
from app.schemas.crawler import CrawlerRunCreate


MAX_OUTPUT_CHARS = 20000
LOG_POLL_INTERVAL_SECONDS = 0.75
MAX_WORKERS = 2
logger = logging.getLogger(__name__)
_crawler_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="crawler-worker")
TASKS_WITH_END_DATE = {"update", "backfill-xauusd", "report", "final-uso", "final-dataset"}


def list_crawler_runs(db: Session, limit: int = 20) -> list[CrawlerRun]:
    return db.query(CrawlerRun).order_by(CrawlerRun.created_at.desc()).limit(limit).all()


def get_crawler_run(db: Session, run_id: int) -> CrawlerRun | None:
    return db.get(CrawlerRun, run_id)


def _build_report_output_path(run_id: int) -> Path:
    reports_dir = Path(settings.GOLD_CLI_CONFIG_PATH).resolve().parent / "logs" / "reports"
    return (reports_dir / f"crawler_report_run_{run_id}.txt").resolve()


def _build_run_log_path(run_id: int) -> Path:
    logs_dir = Path(settings.GOLD_CLI_CONFIG_PATH).resolve().parent / "logs" / "crawler-runs"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return (logs_dir / f"crawler_run_{run_id}_{timestamp}.log").resolve()


def _read_log_tail(log_path: Path) -> str:
    if not log_path.exists():
        return ""

    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

    if len(content) > MAX_OUTPUT_CHARS:
        return content[-MAX_OUTPUT_CHARS:]
    return content


def _refresh_run_output(db: Session, run: CrawlerRun, log_path: Path) -> bool:
    snapshot = _read_log_tail(log_path)
    if not snapshot or snapshot == (run.output_text or ""):
        return False

    run.output_text = snapshot
    db.commit()
    return True


def _build_crawler_command(
    payload: CrawlerRunCreate,
    *,
    report_output_path: str | None = None,
    log_file_path: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        settings.GOLD_CLI_MODULE,
        "--config",
        settings.GOLD_CLI_CONFIG_PATH,
    ]

    if log_file_path:
        command.extend(["--log-file", log_file_path])

    if payload.start_mode:
        command.extend(["--start-mode", payload.start_mode.value])

    command.append(payload.task.value)

    if payload.start:
        command.extend(["--start", payload.start.isoformat()])
    if payload.end and payload.task.value in TASKS_WITH_END_DATE:
        command.extend(["--end", payload.end.isoformat()])

    # gold_cli only supports these runtime flags for update/update-backfill/pipeline.
    # End dates are forwarded only for tasks that explicitly accept them.
    if payload.task.value in {"update", "update-backfill", "pipeline"}:
        if payload.no_forward_fill:
            command.append("--no-forward-fill")
        if payload.bfill_initial:
            command.append("--bfill-initial")
        if payload.sleep is not None:
            command.extend(["--sleep", str(payload.sleep)])
        if payload.quiet:
            command.append("--quiet")
    elif payload.task.value == "report" and report_output_path:
        command.extend(["--report-output", report_output_path])

    return command


def _serialize_payload(payload: CrawlerRunCreate) -> dict[str, Any]:
    return payload.model_dump(mode="json", exclude_none=True)


def _run_crawler_task_in_background(run_id: int, payload_data: dict[str, Any]) -> None:
    db = SessionLocal()
    run = None
    try:
        run = db.get(CrawlerRun, run_id)
        if not run:
            return

        payload = CrawlerRunCreate.model_validate(payload_data)
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        command_payload = _serialize_payload(payload)
        log_file_path = _build_run_log_path(run.id)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        command_payload["log_file_path"] = str(log_file_path)
        report_output_path: Path | None = None
        if payload.task.value == "report":
            report_output_path = _build_report_output_path(run.id)
            command_payload["report_output_path"] = str(report_output_path)

        run.params_json = command_payload
        db.commit()

        process = subprocess.Popen(
            _build_crawler_command(
                payload,
                report_output_path=str(report_output_path) if report_output_path else None,
                log_file_path=str(log_file_path),
            ),
            cwd=str(Path(settings.PROJECT_ROOT)),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        while True:
            _refresh_run_output(db, run, log_file_path)
            return_code = process.poll()
            if return_code is not None:
                break
            time.sleep(LOG_POLL_INTERVAL_SECONDS)

        _refresh_run_output(db, run, log_file_path)
        run.exit_code = return_code
        run.status = "success" if return_code == 0 else "failed"
        if return_code != 0 and not run.error_text:
            run.error_text = run.output_text or f"Crawler process exited with code {return_code}."
    except Exception as exc:
        logger.exception("Crawler task %s failed", run_id)
        if run is not None:
            run.status = "failed"
            run.exit_code = 1
            run.error_text = str(exc)
        else:
            raise CrawlerExecutionError(str(exc)) from exc
    finally:
        if run is not None:
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        db.close()


def enqueue_crawler_task(db: Session, payload: CrawlerRunCreate, current_user: User | None = None) -> CrawlerRun:
    run = CrawlerRun(
        task=payload.task.value,
        status="pending",
        trigger_source="admin_web",
        params_json=_serialize_payload(payload),
        created_by_id=current_user.id if current_user else None,
        log_path=str((Path(settings.GOLD_CLI_CONFIG_PATH).parent / "logs").resolve()),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        _crawler_executor.submit(_run_crawler_task_in_background, run.id, _serialize_payload(payload))
    except Exception as exc:
        run.status = "failed"
        run.exit_code = 1
        run.error_text = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(run)
        raise CrawlerExecutionError(str(exc)) from exc

    return run