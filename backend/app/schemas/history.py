from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class PredictionHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_id: int | None
    prediction_kind: str
    source: str
    days: int
    selected_model_key: str | None
    trend_label: str | None
    used_fallback: bool
    forecast_json: dict[str, Any]
    created_at: datetime