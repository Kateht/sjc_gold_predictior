from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.engine import classify_price_path, forecast_price_path
from app.ai.utils import build_future_dates
from app.db.models import PredictionRecord, User
from app.schemas.models import ModelRead, PredictionKind
from app.schemas.prediction import PricePredictionResponse, TrendPredictionResponse
from app.services.market_service import load_history_for_source
from app.services.model_service import resolve_prediction_model


class PredictionService:
    def __init__(self, db: Session, current_user: User | None = None):
        self.db = db
        self.current_user = current_user

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
            model_id=model.id,
            prediction_kind=prediction_kind,
            source=source,
            input_range=range_value,
            days=days,
            selected_model_key=model.code,
            forecast_json=payload,
            trend_label=trend_label,
            used_fallback=used_fallback,
        )
        self.db.add(record)
        self.db.commit()

    def predict_price(self, *, days: int, model_identifier: str | None = None, source: str = "sjc", range_value: str | None = None) -> PricePredictionResponse:
        history_frame, normalized_source = load_history_for_source(source)
        selected_model = resolve_prediction_model(self.db, model_identifier, PredictionKind.price)
        strategy = self._model_strategy(selected_model)
        history_prices = history_frame["price"].tolist()
        predictions = forecast_price_path(history_prices, days, strategy=strategy)
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
            used_fallback=selected_model.provider == "artifact",
        )

        return PricePredictionResponse(
            future_dates=future_dates,
            predictions=predictions,
            trend=trend,
            selected_model=ModelRead.model_validate(selected_model),
            source=normalized_source,
            used_fallback=selected_model.provider == "artifact",
        )

    def predict_trend(self, *, days: int, model_identifier: str | None = None, source: str = "sjc", range_value: str | None = None) -> TrendPredictionResponse:
        history_frame, normalized_source = load_history_for_source(source)
        selected_model = resolve_prediction_model(self.db, model_identifier, PredictionKind.trend)
        strategy = self._model_strategy(selected_model)
        history_prices = history_frame["price"].tolist()
        predicted_prices = forecast_price_path(history_prices, days, strategy=strategy)
        trend_predictions, trend_scores, _ = classify_price_path(history_prices[-1], predicted_prices)
        future_dates = build_future_dates(history_frame["date"].iloc[-1], days)

        payload = {
            "future_dates": future_dates,
            "trend_predictions": trend_predictions,
            "trend_scores": trend_scores,
            "predicted_prices": predicted_prices,
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
            used_fallback=selected_model.provider == "artifact",
        )

        return TrendPredictionResponse(
            future_dates=future_dates,
            trend_predictions=trend_predictions,
            trend_scores=trend_scores,
            selected_model=ModelRead.model_validate(selected_model),
            source=normalized_source,
            used_fallback=selected_model.provider == "artifact",
        )