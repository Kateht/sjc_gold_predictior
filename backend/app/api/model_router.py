from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.schemas.models import ModelRead, PredictionKind
from app.services.model_service import get_model_by_identifier, list_models


router = APIRouter(tags=["models"])


@router.get("/models", response_model=list[ModelRead])
def get_active_models(
    prediction_kind: PredictionKind | None = Query(default=None),
    source: str | None = Query(default=None, description="Optional source tag such as sjc or world"),
    db: Session = Depends(get_db),
):
    return [ModelRead.model_validate(model) for model in list_models(db, prediction_kind=prediction_kind, active_only=True, source=source)]


@router.get("/models/{identifier}", response_model=ModelRead)
def get_model_detail(identifier: str, db: Session = Depends(get_db)):
    model = get_model_by_identifier(db, identifier, active_only=True)
    if not model:
        raise NotFoundError("Model not found")
    return ModelRead.model_validate(model)