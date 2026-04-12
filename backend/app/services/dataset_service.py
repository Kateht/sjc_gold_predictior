from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.db.models import DatasetSource
from app.schemas.source import DatasetSourceCreate, DatasetSourceUpdate


def _normalize_dataset_path(csv_path: str) -> str:
    path = Path(csv_path).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    return str(path.resolve())


def list_dataset_sources(db: Session, active_only: bool = False) -> list[DatasetSource]:
    query = db.query(DatasetSource)
    if active_only:
        query = query.filter(DatasetSource.is_active.is_(True))
    return query.order_by(DatasetSource.is_default.desc(), DatasetSource.id.asc()).all()


def get_dataset_source_by_identifier(db: Session, identifier: str | int, active_only: bool = False) -> DatasetSource | None:
    query = db.query(DatasetSource)
    if active_only:
        query = query.filter(DatasetSource.is_active.is_(True))

    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        found = query.filter(DatasetSource.id == int(identifier_text)).first()
        if found:
            return found
    return query.filter(DatasetSource.code == identifier_text).first()


def create_dataset_source(db: Session, payload: DatasetSourceCreate, created_by_id: int | None = None) -> DatasetSource:
    existing = db.query(DatasetSource).filter(DatasetSource.code == payload.code).first()
    if existing:
        raise ConflictError("Dataset source code already exists")

    if payload.is_default:
        db.query(DatasetSource).update({DatasetSource.is_default: False})

    source = DatasetSource(
        code=payload.code,
        name=payload.name,
        source_type=payload.source_type,
        csv_path=_normalize_dataset_path(payload.csv_path),
        source_url=payload.source_url,
        file_format=payload.file_format,
        description=payload.description,
        is_active=payload.is_active,
        is_default=payload.is_default,
        created_by_id=created_by_id,
    )
    db.add(source)
    db.flush()
    return source


def update_dataset_source(db: Session, source: DatasetSource, payload: DatasetSourceUpdate) -> DatasetSource:
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("csv_path"):
        updates["csv_path"] = _normalize_dataset_path(str(updates["csv_path"]))

    if updates.get("is_default"):
        db.query(DatasetSource).update({DatasetSource.is_default: False})

    for field_name, field_value in updates.items():
        setattr(source, field_name, field_value)

    db.flush()
    return source


def set_dataset_source_active(db: Session, source: DatasetSource, active: bool) -> DatasetSource:
    source.is_active = active
    db.flush()
    return source


def export_dataset_source_csv(source: DatasetSource) -> Path:
    path = Path(source.csv_path)
    if not path.exists():
        fallback_paths = {
            "sjc-history-csv": Path(settings.LOCAL_DATASET_PATH),
            "crawler-export-csv": Path(settings.CRAWLER_DATASET_PATH),
            "merged-market-csv": Path(settings.PROJECT_ROOT) / "app/crawler/GetVietNameseGoldPrice/final_uso_with_vn_gold_vnd_thousand_imputed.csv",
        }
        fallback_path = fallback_paths.get(source.code)
        if fallback_path and fallback_path.exists():
            path = fallback_path

    if not path.exists():
        raise NotFoundError(f"Dataset CSV not found: {path}")
    if path.suffix.lower() != ".csv":
        raise BadRequestError("Only CSV export is supported")
    return path