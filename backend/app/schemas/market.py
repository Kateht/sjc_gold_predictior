from __future__ import annotations

from pydantic import BaseModel


class PriceChartResponse(BaseModel):
    dates: list[str]
    prices: list[float]


class TrendLabelResponse(BaseModel):
    label: str
    score: float | None = None