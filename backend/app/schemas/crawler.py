from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class CrawlerTask(str, Enum):
    update = "update"
    backfill_xauusd = "backfill-xauusd"
    update_backfill = "update-backfill"
    pipeline = "pipeline"
    report = "report"
    final_uso = "final-uso"


class CrawlerStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"


class CrawlerRunCreate(BaseModel):
    task: CrawlerTask
    start: date | None = None
    end: date | None = None
    no_forward_fill: bool = False
    bfill_initial: bool = False
    sleep: float | None = None
    quiet: bool = False


class CrawlerRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task: str
    status: str
    trigger_source: str
    params_json: dict[str, Any] | None = None
    exit_code: int | None = None
    output_text: str | None = None
    error_text: str | None = None
    log_path: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime