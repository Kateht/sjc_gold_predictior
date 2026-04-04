from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

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


@router.post("/runs", response_model=CrawlerRunRead, status_code=status.HTTP_202_ACCEPTED)
def admin_trigger_crawler_run(
    payload: CrawlerRunCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    run = enqueue_crawler_task(db, payload, current_user=current_user)
    return CrawlerRunRead.model_validate(run)