from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.schemas.source import GoldSourceRead
from app.services.source_service import get_gold_source_by_identifier, list_gold_sources


router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/gold", response_model=list[GoldSourceRead])
def get_gold_sources(db: Session = Depends(get_db)):
    return [GoldSourceRead.model_validate(source) for source in list_gold_sources(db)]


@router.get("/gold/{identifier}", response_model=GoldSourceRead)
def get_gold_source(identifier: str, db: Session = Depends(get_db)):
    source = get_gold_source_by_identifier(db, identifier)
    if not source:
        raise NotFoundError("Gold source not found")
    return GoldSourceRead.model_validate(source)