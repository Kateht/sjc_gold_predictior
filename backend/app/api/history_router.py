from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.schemas.history import PredictionHistoryRead
from app.services.prediction_export_service import build_prediction_export_query, export_prediction_history_csv
from app.db.models import PredictionRecord


router = APIRouter(prefix="/history", tags=["history"])


@router.get("/predictions", response_model=list[PredictionHistoryRead])
def get_my_prediction_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    records = (
        db.query(PredictionRecord)
        .filter(PredictionRecord.user_id == current_user.id)
        .order_by(PredictionRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [PredictionHistoryRead.model_validate(record) for record in records]


@router.get("/predictions/export")
def export_my_prediction_history_csv(
    prediction_kind: str | None = Query(default=None),
    source: str | None = Query(default=None),
    model: str | None = Query(default=None),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    used_fallback: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = build_prediction_export_query(
        db,
        user_id=current_user.id,
        prediction_kind=prediction_kind,
        source=source,
        model=model,
        from_date=from_date,
        to_date=to_date,
        used_fallback=used_fallback,
    )
    return export_prediction_history_csv(query, filename=f"prediction-history-user-{current_user.id}.csv")