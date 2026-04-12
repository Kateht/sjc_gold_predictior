from __future__ import annotations

from datetime import datetime, timezone
import logging

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.ai.engine import classify_price_path, forecast_price_path, predict_trend_path
from app.ai.utils import build_future_dates, limit_history_frame
from app.db.models import PredictionRecord, User
from app.schemas.models import ModelRead, PredictionKind
from app.schemas.prediction import PricePredictionResponse, TrendPredictionResponse
from app.services.market_service import load_history_for_source
from app.services.model_service import resolve_prediction_model


logger = logging.getLogger(__name__)


class PredictionService:
    def __init__(self, db: Session, current_user: User | None = None):
        self.db = db
        self.current_user = current_user

    def _fallback_metrics_json(self, prediction_kind: PredictionKind) -> dict[str, object]:
        if prediction_kind == PredictionKind.price:
            return {"mae": None, "rmse": None, "mape": None, "r2": None}
        return {"accuracy": None}

    def _fallback_strategy(self, prediction_kind: PredictionKind | str, model_identifier: str | None) -> str:
        identifier = (model_identifier or "").strip().lower()
        if prediction_kind == PredictionKind.trend or str(prediction_kind) == PredictionKind.trend.value:
            return "slope"
        if "gru" in identifier:
            return "gru"
        if "momentum" in identifier:
            return "momentum"
        if "mean-reversion" in identifier or "mean_reversion" in identifier:
            return "mean_reversion"
        return "linear"

    def _fallback_provider(self, model_identifier: str | None) -> str:
        identifier = (model_identifier or "").strip().lower()
        artifact_codes = {
            "meta-lstm-k10-price-v1",
            "lstm-k10-price-v1",
            "gru-price-v1",
            "sjc-classification-v1",
        }
        if identifier in artifact_codes:
            return "artifact"
        return "builtin"

    def _build_fallback_model_read(self, prediction_kind: PredictionKind, model_identifier: str | None) -> ModelRead:
        code = (model_identifier or "").strip() or (
            "linear-price-v1" if prediction_kind == PredictionKind.price else "trend-slope-v1"
        )
        now = datetime.now(timezone.utc)
        return ModelRead(
            id=0,
            code=code,
            name=code,
            prediction_kind=prediction_kind,
            provider=self._fallback_provider(code),
            artifact_path=None,
            description="Fallback model metadata used because the model registry could not be read.",
            config_json={"strategy": self._fallback_strategy(prediction_kind, code)},
            metrics_json=self._fallback_metrics_json(prediction_kind),
            is_active=True,
            is_default=False,
            created_at=now,
            updated_at=now,
        )

    def _resolve_model_or_fallback(self, identifier: str | None, prediction_kind: PredictionKind):
        try:
            model = resolve_prediction_model(self.db, identifier, prediction_kind)
            return model, ModelRead.model_validate(model)
        except SQLAlchemyError as exc:
            fallback_model = self._build_fallback_model_read(prediction_kind, identifier)
            logger.warning("Model registry lookup failed; using fallback model metadata: %s", exc)
            return fallback_model, fallback_model

    def _model_strategy(self, model) -> str:
        config = model.config_json or {}
        strategy = config.get("strategy") or "linear"
        return str(strategy)

    def _record_prediction(
        self,
        *,
        model,
        prediction_kind: str,
        source: str,
        days: int,
        range_value: str | None,
        payload: dict[str, object],
        trend_label: str | None,
        used_fallback: bool,
    ) -> None:
        record = PredictionRecord(
            user_id=self.current_user.id if self.current_user else None,
            model_id=getattr(model, "id", None) or None,
            prediction_kind=prediction_kind,
            source=source,
            input_range=range_value,
            days=days,
            selected_model_key=model.code,
            forecast_json=payload,
            trend_label=trend_label,
            used_fallback=used_fallback,
        )
        try:
            self.db.add(record)
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.warning("Prediction result returned, but saving prediction history failed: %s", exc)

    def predict_price(self, *, days: int, model_identifier: str | None = None, source: str = "sjc", range_value: str | None = None) -> PricePredictionResponse:
        history_frame, normalized_source = load_history_for_source(source)
        history_frame = limit_history_frame(history_frame, range_value)
        selected_model, selected_model_read = self._resolve_model_or_fallback(model_identifier, PredictionKind.price)
        strategy = self._model_strategy(selected_model)
        history_prices = history_frame["price"].tolist()
        predictions, used_fallback = forecast_price_path(
            history_prices,
            days,
            strategy=strategy,
            provider=selected_model.provider,
            model_code=selected_model.code,
            source=normalized_source,
            range_value=range_value,
        )
        trend_predictions, trend_scores, trend = classify_price_path(history_prices[-1], predictions)
        future_dates = build_future_dates(history_frame["date"].iloc[-1], days)

        payload = {
            "future_dates": future_dates,
            "predictions": predictions,
            "trend_predictions": trend_predictions,
            "trend_scores": trend_scores,
            "trend": trend,
            "source": normalized_source,
            "strategy": strategy,
        }
        self._record_prediction(
            model=selected_model,
            prediction_kind="price",
            source=normalized_source,
            days=days,
            range_value=range_value,
            payload=payload,
            trend_label=trend,
            used_fallback=used_fallback,
        )

        return PricePredictionResponse(
            future_dates=future_dates,
            predictions=predictions,
            trend=trend,
            selected_model=selected_model_read,
            source=normalized_source,
            used_fallback=used_fallback,
        )

    def predict_trend(self, *, days: int, model_identifier: str | None = None, source: str = "sjc", range_value: str | None = None) -> TrendPredictionResponse:
        history_frame, normalized_source = load_history_for_source(source)
        history_frame = limit_history_frame(history_frame, range_value)
        selected_model, selected_model_read = self._resolve_model_or_fallback(model_identifier, PredictionKind.trend)
        strategy = self._model_strategy(selected_model)
        history_prices = history_frame["price"].tolist()
        trend_predictions, trend_scores, used_fallback = predict_trend_path(
            history_prices,
            days,
            strategy=strategy,
            provider=selected_model.provider,
            model_code=selected_model.code,
            source=normalized_source,
            range_value=range_value,
        )
        future_dates = build_future_dates(history_frame["date"].iloc[-1], days)

        payload = {
            "future_dates": future_dates,
            "trend_predictions": trend_predictions,
            "trend_scores": trend_scores,
            "source": normalized_source,
            "strategy": strategy,
        }
        self._record_prediction(
            model=selected_model,
            prediction_kind="trend",
            source=normalized_source,
            days=days,
            range_value=range_value,
            payload=payload,
            trend_label=trend_predictions[-1] if trend_predictions else "flat",
            used_fallback=used_fallback,
        )

        return TrendPredictionResponse(
            future_dates=future_dates,
            trend_predictions=trend_predictions,
            trend_scores=trend_scores,
            selected_model=selected_model_read,
            source=normalized_source,
            used_fallback=used_fallback,
        )
