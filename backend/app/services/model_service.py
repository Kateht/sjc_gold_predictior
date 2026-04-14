from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.utils import normalize_source
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import MLModel
from app.schemas.models import ModelCreate, ModelUpdate, PredictionKind


DEPRECATED_MODEL_CODES = {"best-xgb-price-v1"}


def _kind_value(kind: PredictionKind | str | None) -> str | None:
    if kind is None:
        return None
    if isinstance(kind, PredictionKind):
        return kind.value
    return str(kind)


def _normalized_source_value(source: str | None) -> str | None:
    if source is None:
        return None
    cleaned = str(source).strip()
    if not cleaned:
        return None
    return normalize_source(cleaned)


def _model_source(model: MLModel) -> str:
    config = model.config_json if isinstance(model.config_json, dict) else {}
    source_value = config.get("source") if isinstance(config, dict) else None
    if source_value is not None and str(source_value).strip():
        return normalize_source(str(source_value))
    return "sjc"


def _filter_models_by_source(models: list[MLModel], source: str | None) -> list[MLModel]:
    normalized_source = _normalized_source_value(source)
    if normalized_source is None:
        return models
    return [model for model in models if _model_source(model) == normalized_source]


def list_models(
    db: Session,
    prediction_kind: PredictionKind | str | None = None,
    active_only: bool = False,
    source: str | None = None,
) -> list[MLModel]:
    query = db.query(MLModel)
    kind_value = _kind_value(prediction_kind)
    if kind_value:
        query = query.filter(MLModel.prediction_kind == kind_value)
    if active_only:
        query = query.filter(MLModel.is_active.is_(True))
    query = query.filter(~MLModel.code.in_(DEPRECATED_MODEL_CODES))
    models = query.order_by(MLModel.is_default.desc(), MLModel.id.asc()).all()
    return _filter_models_by_source(models, source)


def get_model_by_identifier(
    db: Session,
    identifier: str | int | None,
    prediction_kind: PredictionKind | str | None = None,
    active_only: bool = False,
    source: str | None = None,
) -> MLModel | None:
    query = db.query(MLModel)
    kind_value = _kind_value(prediction_kind)
    if kind_value:
        query = query.filter(MLModel.prediction_kind == kind_value)
    if active_only:
        query = query.filter(MLModel.is_active.is_(True))
    query = query.filter(~MLModel.code.in_(DEPRECATED_MODEL_CODES))

    models = _filter_models_by_source(query.order_by(MLModel.is_default.desc(), MLModel.id.asc()).all(), source)
    if not models:
        return None

    if identifier is None or str(identifier).strip() == "":
        return models[0]

    identifier_text = str(identifier).strip()
    if identifier_text.isdigit():
        model_id = int(identifier_text)
        for model in models:
            if model.id == model_id:
                return model

    for model in models:
        if model.code == identifier_text:
            return model
    return None


def get_default_model(db: Session, prediction_kind: PredictionKind | str, source: str | None = None) -> MLModel | None:
    return get_model_by_identifier(db, None, prediction_kind=prediction_kind, active_only=True, source=source)


def create_model(db: Session, payload: ModelCreate, created_by_id: int | None = None) -> MLModel:
    if payload.code in DEPRECATED_MODEL_CODES:
        raise ConflictError("Model code is deprecated")

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


def resolve_prediction_model(
    db: Session,
    identifier: str | int | None,
    prediction_kind: PredictionKind | str,
    source: str | None = None,
) -> MLModel:
    model = get_model_by_identifier(db, identifier, prediction_kind=prediction_kind, active_only=True, source=source)
    if model:
        return model

    normalized_source = _normalized_source_value(source)
    if normalized_source == "world":
        raise NotFoundError(f"No active model found for {prediction_kind} and source {normalized_source}")

    fallback = get_default_model(db, prediction_kind)
    if fallback:
        return fallback

    raise NotFoundError(f"No active model found for {prediction_kind}")