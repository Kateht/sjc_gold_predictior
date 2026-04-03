from pydantic import BaseModel
from typing import List, Optional

# ==========================================
# 1. Sub-models (Model con)
# ==========================================

class WorldGoldData(BaseModel):
    status: str
    message: Optional[str] = None  # Chỉ có nếu status="error"
    current_price_usd: Optional[float] = None
    change_usd: Optional[float] = None
    change_percent: Optional[float] = None
    trend_7d_usd: Optional[List[float]] = None
    unit: Optional[str] = None
    source: Optional[str] = None

class DomesticGoldData(BaseModel):
    status: str
    message: Optional[str] = None
    current_price_vnd: Optional[float] = None
    change_vnd: Optional[float] = None
    change_percent: Optional[float] = None
    trend_7d_vnd: Optional[List[float]] = None
    unit: Optional[str] = None
    source: Optional[str] = None

class ArbitrageData(BaseModel):
    status: Optional[str] = None
    message: Optional[str] = None
    gap_vnd: Optional[float] = None
    exchange_rate: Optional[float] = None
    converted_world_price_vnd: Optional[float] = None
    description: Optional[str] = None

# ==========================================
# 2. Main Response Model (Model chính)
# ==========================================

class OverviewResponse(BaseModel):
    world_gold: WorldGoldData
    domestic_gold: DomesticGoldData
    arbitrage: ArbitrageData
    last_updated: str