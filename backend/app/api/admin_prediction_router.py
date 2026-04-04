from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.services.prediction_export_service import build_prediction_export_query, export_prediction_history_csv


router = APIRouter(prefix="/admin/predictions", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/export")
def export_all_prediction_history_csv(
    user_id: int | None = Query(default=None),
    prediction_kind: str | None = Query(default=None),
    source: str | None = Query(default=None),
    model: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    used_fallback: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = build_prediction_export_query(
        db,
        user_id=user_id,
        prediction_kind=prediction_kind,
        source=source,
        model=model,
        from_date=from_date,
        to_date=to_date,
        used_fallback=used_fallback,
    )
    filename = "prediction-history-admin.csv" if user_id is None else f"prediction-history-user-{user_id}.csv"
    return export_prediction_history_csv(query, filename=filename)