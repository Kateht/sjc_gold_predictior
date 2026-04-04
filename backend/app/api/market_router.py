from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas.market import PriceChartResponse
from app.services.market_service import get_price_chart


router = APIRouter(tags=["market"])


@router.get("/price-chart", response_model=PriceChartResponse)
def price_chart(
    range: str = Query(default="30d", description="Supported values: 7d, 30d, 90d, 180d, 1y, all"),
    source: str = Query(default="sjc", description="sjc or world"),
):
    return get_price_chart(range_value=range, source=source)