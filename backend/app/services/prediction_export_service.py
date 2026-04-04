from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
from io import StringIO
from typing import Any

from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.models import MLModel, PredictionRecord, User


CSV_HEADERS = [
    "record_id",
    "created_at",
    "user_id",
    "user_email",
    "prediction_kind",
    "source",
    "model_id",
    "model_code",
    "model_name",
    "days",
    "input_range",
    "trend_label",
    "used_fallback",
    "future_start_date",
    "future_end_date",
    "predictions_count",
    "first_prediction",
    "last_prediction",
    "min_prediction",
    "max_prediction",
    "trend_predictions",
    "trend_scores",
    "strategy",
]


def _datetime_start(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _datetime_end(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _as_float_list(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []

    result: list[float] = []
    for item in values:
        try:
            result.append(float(item))
        except (TypeError, ValueError):
            continue
    return result


def _join_values(values: Any) -> str:
    if isinstance(values, list):
        return "|".join(str(item) for item in values)
    if values is None:
        return ""
    return str(values)


def build_prediction_export_query(
    db: Session,
    *,
    user_id: int | None = None,
    prediction_kind: str | None = None,
    source: str | None = None,
    model: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    used_fallback: bool | None = None,
):
    query = (
        db.query(PredictionRecord, User, MLModel)
        .outerjoin(User, PredictionRecord.user_id == User.id)
        .outerjoin(MLModel, PredictionRecord.model_id == MLModel.id)
    )

    if user_id is not None:
        query = query.filter(PredictionRecord.user_id == user_id)
    if prediction_kind:
        query = query.filter(PredictionRecord.prediction_kind == str(prediction_kind))
    if source:
        query = query.filter(PredictionRecord.source == source)
    if model:
        model_text = str(model).strip()
        filters = [PredictionRecord.selected_model_key == model_text, MLModel.code == model_text]
        if model_text.isdigit():
            filters.append(MLModel.id == int(model_text))
        query = query.filter(or_(*filters))
    if from_date is not None:
        query = query.filter(PredictionRecord.created_at >= _datetime_start(from_date))
    if to_date is not None:
        query = query.filter(PredictionRecord.created_at <= _datetime_end(to_date))
    if used_fallback is not None:
        query = query.filter(PredictionRecord.used_fallback.is_(used_fallback))

    return query.order_by(PredictionRecord.created_at.desc(), PredictionRecord.id.desc()).execution_options(stream_results=True)


def _row_from_record(record: PredictionRecord, user: User | None, model: MLModel | None) -> dict[str, Any]:
    payload = record.forecast_json or {}
    predictions = _as_float_list(payload.get("predictions") or payload.get("predicted_prices") or [])
    trend_predictions = payload.get("trend_predictions") or []
    trend_scores = payload.get("trend_scores") or []
    strategy = payload.get("strategy") or ""

    return {
        "record_id": record.id,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "user_id": record.user_id or "",
        "user_email": getattr(user, "email", "") or "",
        "prediction_kind": record.prediction_kind,
        "source": record.source,
        "model_id": record.model_id or "",
        "model_code": getattr(model, "code", "") or record.selected_model_key or "",
        "model_name": getattr(model, "name", "") or "",
        "days": record.days,
        "input_range": record.input_range or "",
        "trend_label": record.trend_label or "",
        "used_fallback": bool(record.used_fallback),
        "future_start_date": (payload.get("future_dates") or [""])[0] if payload.get("future_dates") else "",
        "future_end_date": (payload.get("future_dates") or [""])[-1] if payload.get("future_dates") else "",
        "predictions_count": len(predictions),
        "first_prediction": predictions[0] if predictions else "",
        "last_prediction": predictions[-1] if predictions else "",
        "min_prediction": min(predictions) if predictions else "",
        "max_prediction": max(predictions) if predictions else "",
        "trend_predictions": _join_values(trend_predictions),
        "trend_scores": _join_values(trend_scores),
        "strategy": strategy,
    }


def build_prediction_history_rows(query) -> list[dict[str, Any]]:
    return list(iter_prediction_history_rows(query))


def iter_prediction_history_rows(query, *, chunk_size: int = 500):
    for record, user, model in query.yield_per(chunk_size):
        yield _row_from_record(record, user, model)


def export_prediction_history_csv(query, *, filename: str) -> StreamingResponse:
    def generate_csv():
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
        writer.writeheader()
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for row in iter_prediction_history_rows(query):
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(generate_csv(), media_type="text/csv; charset=utf-8", headers=headers)