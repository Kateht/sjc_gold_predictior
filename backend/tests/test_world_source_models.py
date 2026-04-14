from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.engine import forecast_price_path
from app.core.exceptions import NotFoundError
from app.db.base import Base
from app.db.models import MLModel
from app.schemas.models import PredictionKind
from app.services.model_service import list_models, resolve_prediction_model
from app.services.prediction_service import PredictionService


class ModelServiceWorldSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()

        now = datetime(2026, 4, 4, tzinfo=timezone.utc)
        self.db.add_all(
            [
                MLModel(
                    code="lstm-k10-price-v1",
                    name="LSTM K10 Price Model",
                    prediction_kind=PredictionKind.price.value,
                    provider="artifact",
                    artifact_path="app/models/lstm_k10.keras",
                    description="Sequence model trained on SJC history",
                    config_json={"lookback": 10, "source": "sjc"},
                    metrics_json={"mae": None, "rmse": None, "mape": None, "r2": None},
                    is_active=True,
                    is_default=True,
                    created_at=now,
                    updated_at=now,
                ),
                MLModel(
                    code="world-price-v1",
                    name="World Gold Price Model",
                    prediction_kind=PredictionKind.price.value,
                    provider="builtin",
                    artifact_path=None,
                    description="Built-in forecast for world gold price history",
                    config_json={"strategy": "momentum", "source": "world"},
                    metrics_json={"mae": None, "rmse": None, "mape": None, "r2": None},
                    is_active=True,
                    is_default=False,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_list_models_filters_by_source(self) -> None:
        models = list_models(self.db, prediction_kind=PredictionKind.price, active_only=True, source="world")

        self.assertEqual([model.code for model in models], ["world-price-v1"])

    def test_resolve_prediction_model_prefers_source_specific_model(self) -> None:
        selected_model = resolve_prediction_model(self.db, None, PredictionKind.price, source="world")

        self.assertEqual(selected_model.code, "world-price-v1")

    def test_resolve_prediction_model_rejects_cross_source_identifier(self) -> None:
        with self.assertRaises(NotFoundError):
            resolve_prediction_model(self.db, "lstm-k10-price-v1", PredictionKind.price, source="world")

    def test_resolve_prediction_model_keeps_sjc_default_fallback(self) -> None:
        selected_model = resolve_prediction_model(self.db, "missing-model", PredictionKind.price, source="sjc")

        self.assertEqual(selected_model.code, "lstm-k10-price-v1")


class PredictionServiceWorldSourceTest(unittest.TestCase):
    def test_resolve_model_or_fallback_passes_source(self) -> None:
        service = PredictionService(db=SimpleNamespace(), current_user=None)
        model = SimpleNamespace(
            id=42,
            code="world-price-v1",
            name="World Gold Price Model",
            prediction_kind=PredictionKind.price,
            provider="builtin",
            artifact_path=None,
            description="Built-in forecast for world gold price history",
            config_json={"strategy": "momentum", "source": "world"},
            metrics_json={"mae": None, "rmse": None, "mape": None, "r2": None},
            is_active=True,
            is_default=False,
            created_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
            updated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        )

        with patch("app.services.prediction_service.resolve_prediction_model", return_value=model) as resolve_model:
            selected_model, selected_model_read = service._resolve_model_or_fallback(
                "world-price-v1",
                PredictionKind.price,
                source="world",
            )

        self.assertEqual(resolve_model.call_args.kwargs["source"], "world")
        self.assertEqual(selected_model.code, "world-price-v1")
        self.assertEqual(selected_model_read.code, "world-price-v1")

    def test_world_builtin_forecast_does_not_fallback(self) -> None:
        predictions, used_fallback = forecast_price_path(
            [100.0, 101.0, 102.0],
            3,
            provider="builtin",
            model_code="world-price-v1",
            source="world",
        )

        self.assertEqual(len(predictions), 3)
        self.assertFalse(used_fallback)