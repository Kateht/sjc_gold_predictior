from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoldSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    source_url: str
    source_type: str
    description: str | None = None
    region: str | None = None
    sort_order: int
    is_active: bool


class GoldSourceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=255)
    source_url: str = Field(min_length=5, max_length=500)
    source_type: str = Field(min_length=2, max_length=50)
    description: str | None = None
    region: str | None = None
    sort_order: int = 0
    is_active: bool = True


class GoldSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    source_url: str | None = Field(default=None, min_length=5, max_length=500)
    source_type: str | None = Field(default=None, min_length=2, max_length=50)
    description: str | None = None
    region: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class DatasetSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    source_type: str
    csv_path: str
    source_url: str | None = None
    file_format: str
    description: str | None = None
    is_active: bool
    is_default: bool
    last_synced_at: datetime | None = None


class DatasetSourceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=255)
    source_type: str = Field(min_length=2, max_length=50)
    csv_path: str = Field(min_length=1, max_length=500)
    source_url: str | None = None
    file_format: str = Field(default="csv", min_length=3, max_length=20)
    description: str | None = None
    is_active: bool = True
    is_default: bool = False


class DatasetSourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    source_type: str | None = Field(default=None, min_length=2, max_length=50)
    csv_path: str | None = Field(default=None, min_length=1, max_length=500)
    source_url: str | None = None
    file_format: str | None = Field(default=None, min_length=3, max_length=20)
    description: str | None = None
    is_active: bool | None = None
    is_default: bool | None = None