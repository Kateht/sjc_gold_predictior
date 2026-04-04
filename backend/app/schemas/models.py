from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PredictionKind(str, Enum):
    price = "price"
    trend = "trend"


class ModelProvider(str, Enum):
    builtin = "builtin"
    artifact = "artifact"
    ai = "ai"


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    prediction_kind: PredictionKind
    provider: ModelProvider
    artifact_path: str | None = None
    description: str | None = None
    config_json: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    is_active: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ModelCreate(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=255)
    prediction_kind: PredictionKind
    provider: ModelProvider = ModelProvider.builtin
    artifact_path: str | None = None
    description: str | None = None
    config_json: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    is_active: bool = True
    is_default: bool = False


class ModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    prediction_kind: PredictionKind | None = None
    provider: ModelProvider | None = None
    artifact_path: str | None = None
    description: str | None = None
    config_json: dict[str, Any] | None = None
    metrics_json: dict[str, Any] | None = None
    is_active: bool | None = None
    is_default: bool | None = None


class ModelSelectResponse(BaseModel):
    models: list[ModelRead]