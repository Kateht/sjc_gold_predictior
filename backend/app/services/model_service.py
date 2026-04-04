from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import MLModel
from app.schemas.models import ModelCreate, ModelUpdate, PredictionKind


def _kind_value(kind: PredictionKind | str | None) -> str | None:
    if kind is None:
        return None
    if isinstance(kind, PredictionKind):
        return kind.value
    return str(kind)


def list_models(db: Session, prediction_kind: PredictionKind | str | None = None, active_only: bool = False) -> list[MLModel]:
    query = db.query(MLModel)
    kind_value = _kind_value(prediction_kind)
    if kind_value:
        query = query.filter(MLModel.prediction_kind == kind_value)
    if active_only:
        query = query.filter(MLModel.is_active.is_(True))
    return query.order_by(MLModel.is_default.desc(), MLModel.id.asc()).all()


def get_model_by_identifier(
    db: Session,
    identifier: str | int | None,
    prediction_kind: PredictionKind | str | None = None,
    active_only: bool = False,
) -> MLModel | None:
    query = db.query(MLModel)
    kind_value = _kind_value(prediction_kind)
    if kind_value:
        query = query.filter(MLModel.prediction_kind == kind_value)
    if active_only:
        query = query.filter(MLModel.is_active.is_(True))

    if identifier is None or str(identifier).strip() == "":
        default_model = query.filter(MLModel.is_default.is_(True)).order_by(MLModel.id.asc()).first()
        if default_model:
            return default_model
        return query.order_by(MLModel.id.asc()).first()

    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        model = query.filter(MLModel.id == int(identifier_text)).first()
        if model:
            return model
    return query.filter(MLModel.code == identifier_text).first()


def get_default_model(db: Session, prediction_kind: PredictionKind | str) -> MLModel | None:
    return get_model_by_identifier(db, None, prediction_kind=prediction_kind, active_only=True)


def create_model(db: Session, payload: ModelCreate, created_by_id: int | None = None) -> MLModel:
    existing = db.query(MLModel).filter(MLModel.code == payload.code).first()
    if existing:
        raise ConflictError("Model code already exists")

    if payload.is_default:
        db.query(MLModel).filter(MLModel.prediction_kind == payload.prediction_kind.value).update({MLModel.is_default: False})

    model = MLModel(
        code=payload.code,
        name=payload.name,
        prediction_kind=payload.prediction_kind.value,
        provider=payload.provider.value,
        artifact_path=payload.artifact_path,
        description=payload.description,
        config_json=payload.config_json,
        metrics_json=payload.metrics_json,
        is_active=payload.is_active,
        is_default=payload.is_default,
        created_by_id=created_by_id,
    )
    db.add(model)
    db.flush()
    return model


def update_model(db: Session, model: MLModel, payload: ModelUpdate) -> MLModel:
    updates = payload.model_dump(exclude_unset=True)
    if "prediction_kind" in updates and updates["prediction_kind"] is not None:
        updates["prediction_kind"] = updates["prediction_kind"].value
    if "provider" in updates and updates["provider"] is not None:
        updates["provider"] = updates["provider"].value

    if updates.get("is_default"):
        db.query(MLModel).filter(MLModel.prediction_kind == model.prediction_kind).update({MLModel.is_default: False})

    for field_name, field_value in updates.items():
        setattr(model, field_name, field_value)

    db.flush()
    return model


def set_model_active(db: Session, model: MLModel, active: bool) -> MLModel:
    model.is_active = active
    db.flush()
    return model


def set_default_model(db: Session, model: MLModel) -> MLModel:
    db.query(MLModel).filter(MLModel.prediction_kind == model.prediction_kind).update({MLModel.is_default: False})
    model.is_default = True
    model.is_active = True
    db.flush()
    return model


def resolve_prediction_model(db: Session, identifier: str | int | None, prediction_kind: PredictionKind | str) -> MLModel:
    model = get_model_by_identifier(db, identifier, prediction_kind=prediction_kind, active_only=True)
    if model:
        return model

    fallback = get_default_model(db, prediction_kind)
    if fallback:
        return fallback

    raise NotFoundError(f"No active model found for {prediction_kind}")