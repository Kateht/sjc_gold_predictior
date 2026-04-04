from __future__ import annotations

from pydantic import BaseModel

from app.schemas.models import ModelRead, PredictionKind


class PricePredictionResponse(BaseModel):
    future_dates: list[str]
    predictions: list[float]
    trend: str
    selected_model: ModelRead
    prediction_kind: PredictionKind = PredictionKind.price
    source: str
    used_fallback: bool


class TrendPredictionResponse(BaseModel):
    future_dates: list[str]
    trend_predictions: list[str]
    trend_scores: list[float]
    selected_model: ModelRead
    prediction_kind: PredictionKind = PredictionKind.trend
    source: str
    used_fallback: bool