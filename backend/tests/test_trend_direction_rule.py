from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from app.ai.engine import summarize_price_path
from app.schemas.models import ModelRead, ModelProvider, PredictionKind
from app.services.prediction_service import PredictionService


class TrendDirectionRuleTest(unittest.TestCase):
    def test_summarize_price_path_uses_first_point_for_overall_trend(self) -> None:
        labels, scores, trend = summarize_price_path(100.0, [110.0, 90.0, 105.0])

        self.assertEqual(labels, ["up", "down", "up"])
        self.assertEqual(scores, [0.99, 0.99, 0.99])
        self.assertEqual(trend, "up")

    def test_predict_trend_records_first_step_label(self) -> None:
        now = datetime(2026, 4, 14, tzinfo=timezone.utc)
        model = ModelRead(
            id=1,
            code="trend-model",
            name="Trend Model",
            prediction_kind=PredictionKind.trend,
            provider=ModelProvider.builtin,
            artifact_path=None,
            description=None,
            config_json={"strategy": "linear"},
            metrics_json={"accuracy": 0.9},
            is_active=True,
            is_default=True,
            created_at=now,
            updated_at=now,
        )
        history_frame = pd.DataFrame({"date": [pd.Timestamp("2026-04-10")], "price": [100.0]})
        db = SimpleNamespace(add=lambda *_: None, commit=lambda *_: None, rollback=lambda *_: None)
        current_user = SimpleNamespace(id=7)
        service = PredictionService(db, current_user=current_user)

        with patch("app.services.prediction_service.load_history_for_source", return_value=(history_frame, "sjc")), patch(
            "app.services.prediction_service.limit_history_frame",
            return_value=history_frame,
        ), patch.object(service, "_resolve_model_or_fallback", return_value=(model, model)), patch(
            "app.services.prediction_service.predict_trend_path",
            return_value=(["up", "down"], [0.7, 0.4], False),
        ), patch("app.services.prediction_service.build_future_dates", return_value=["2026-04-11", "2026-04-12"]), patch.object(
            service,
            "_record_prediction",
        ) as record_mock:
            response = service.predict_trend(days=2, model_identifier="trend-model", source="sjc", range_value="30d")

        self.assertEqual(response.trend_predictions, ["up", "down"])
        record_mock.assert_called_once()
        self.assertEqual(record_mock.call_args.kwargs["trend_label"], "up")


if __name__ == "__main__":
    unittest.main()
