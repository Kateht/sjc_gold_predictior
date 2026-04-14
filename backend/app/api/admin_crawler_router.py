from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from pathlib import Path

from app.core.config import settings
from app.core.deps import require_admin
from app.core.exceptions import NotFoundError
from app.db.models import User
from app.db.session import get_db
from app.schemas.crawler import CrawlerRunCreate, CrawlerRunRead
from app.services.crawler_service import enqueue_crawler_task, get_crawler_run, list_crawler_runs


router = APIRouter(prefix="/admin/crawler", tags=["crawler"], dependencies=[Depends(require_admin)])


@router.get("/runs", response_model=list[CrawlerRunRead])
def admin_list_crawler_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return [CrawlerRunRead.model_validate(run) for run in list_crawler_runs(db, limit=limit)]


@router.get("/runs/{run_id}", response_model=CrawlerRunRead)
def admin_get_crawler_run(run_id: int, db: Session = Depends(get_db)):
    run = get_crawler_run(db, run_id)
    if not run:
        raise NotFoundError("Crawler run not found")
    return CrawlerRunRead.model_validate(run)


@router.get("/runs/{run_id}/report")
def admin_download_crawler_report(run_id: int, db: Session = Depends(get_db)):
    run = get_crawler_run(db, run_id)
    if not run:
        raise NotFoundError("Crawler run not found")
    if run.task != "report" or run.status != "success":
        raise NotFoundError("Crawler report is not available for this run")

    report_path_text = None
    if isinstance(run.params_json, dict):
        report_path_text = run.params_json.get("report_output_path")

    if report_path_text:
        report_path = Path(str(report_path_text)).expanduser()
    else:
        log_path = Path(run.log_path).expanduser() if run.log_path else Path(settings.PROJECT_ROOT)
        report_path = log_path / "reports" / f"crawler_report_run_{run.id}.txt"

    if not report_path.is_absolute():
        report_path = (Path(settings.PROJECT_ROOT) / report_path).resolve()

    if not report_path.exists():
        raise NotFoundError("Crawler report file not found")

    return FileResponse(path=str(report_path), media_type="text/plain", filename=report_path.name)


@router.post("/runs", response_model=CrawlerRunRead, status_code=status.HTTP_202_ACCEPTED)
def admin_trigger_crawler_run(
    payload: CrawlerRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    run = enqueue_crawler_task(db, payload, current_user=current_user)
    return CrawlerRunRead.model_validate(run)