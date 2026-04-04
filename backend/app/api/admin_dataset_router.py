from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.exceptions import NotFoundError
from app.db.models import User
from app.db.session import get_db
from app.schemas.source import DatasetSourceCreate, DatasetSourceRead, DatasetSourceUpdate
from app.services.dataset_service import (
    create_dataset_source,
    export_dataset_source_csv,
    get_dataset_source_by_identifier,
    list_dataset_sources,
    set_dataset_source_active,
    update_dataset_source,
)


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/datasets", response_model=list[DatasetSourceRead])
def admin_list_datasets(
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return [DatasetSourceRead.model_validate(source) for source in list_dataset_sources(db, active_only=active_only)]


@router.get("/datasets/{identifier}", response_model=DatasetSourceRead)
def admin_get_dataset(identifier: str, db: Session = Depends(get_db)):
    source = get_dataset_source_by_identifier(db, identifier, active_only=False)
    if not source:
        raise NotFoundError("Dataset source not found")
    return DatasetSourceRead.model_validate(source)


@router.post("/datasets", response_model=DatasetSourceRead, status_code=status.HTTP_201_CREATED)
def admin_create_dataset(
    payload: DatasetSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    source = create_dataset_source(db, payload, created_by_id=current_user.id)
    db.commit()
    return DatasetSourceRead.model_validate(source)


@router.patch("/datasets/{identifier}", response_model=DatasetSourceRead)
def admin_update_dataset(identifier: str, payload: DatasetSourceUpdate, db: Session = Depends(get_db)):
    source = get_dataset_source_by_identifier(db, identifier, active_only=False)
    if not source:
        raise NotFoundError("Dataset source not found")
    updated = update_dataset_source(db, source, payload)
    db.commit()
    return DatasetSourceRead.model_validate(updated)


@router.post("/datasets/{identifier}/activate", response_model=DatasetSourceRead)
def admin_activate_dataset(identifier: str, db: Session = Depends(get_db)):
    source = get_dataset_source_by_identifier(db, identifier, active_only=False)
    if not source:
        raise NotFoundError("Dataset source not found")
    updated = set_dataset_source_active(db, source, True)
    db.commit()
    return DatasetSourceRead.model_validate(updated)


@router.post("/datasets/{identifier}/deactivate", response_model=DatasetSourceRead)
def admin_deactivate_dataset(identifier: str, db: Session = Depends(get_db)):
    source = get_dataset_source_by_identifier(db, identifier, active_only=False)
    if not source:
        raise NotFoundError("Dataset source not found")
    updated = set_dataset_source_active(db, source, False)
    db.commit()
    return DatasetSourceRead.model_validate(updated)


@router.get("/datasets/{identifier}/export")
def admin_export_dataset(identifier: str, db: Session = Depends(get_db)):
    source = get_dataset_source_by_identifier(db, identifier, active_only=False)
    if not source:
        raise NotFoundError("Dataset source not found")

    csv_path = export_dataset_source_csv(source)

    return FileResponse(path=str(csv_path), media_type="text/csv", filename=f"{source.code}.csv")