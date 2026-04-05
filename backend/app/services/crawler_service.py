from __future__ import annotations

import logging
import subprocess
import sys
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
MAX_WORKERS = 2
logger = logging.getLogger(__name__)
_crawler_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="crawler-worker")


def list_crawler_runs(db: Session, limit: int = 20) -> list[CrawlerRun]:
    return db.query(CrawlerRun).order_by(CrawlerRun.created_at.desc()).limit(limit).all()


def get_crawler_run(db: Session, run_id: int) -> CrawlerRun | None:
    return db.get(CrawlerRun, run_id)


def _build_crawler_command(payload: CrawlerRunCreate) -> list[str]:
    command = [
        sys.executable,
        "-m",
        settings.GOLD_CLI_MODULE,
        "--config",
        settings.GOLD_CLI_CONFIG_PATH,
        payload.task.value,
    ]

    if payload.start:
        command.extend(["--start", payload.start.isoformat()])
    if payload.end:
        command.extend(["--end", payload.end.isoformat()])

    # gold_cli only supports these flags for update/update-backfill/pipeline.
    if payload.task.value in {"update", "update-backfill", "pipeline"}:
        if payload.no_forward_fill:
            command.append("--no-forward-fill")
        if payload.bfill_initial:
            command.append("--bfill-initial")
        if payload.sleep is not None:
            command.extend(["--sleep", str(payload.sleep)])
        if payload.quiet:
            command.append("--quiet")

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

        completed = subprocess.run(
            _build_crawler_command(payload),
            cwd=str(Path(settings.PROJECT_ROOT)),
            capture_output=True,
            text=True,
            check=False,
        )
        run.exit_code = completed.returncode
        run.output_text = (completed.stdout or "")[:MAX_OUTPUT_CHARS]
        run.error_text = (completed.stderr or "")[:MAX_OUTPUT_CHARS] or None
        run.status = "success" if completed.returncode == 0 else "failed"
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