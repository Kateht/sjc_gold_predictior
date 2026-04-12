from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_optional_current_user
from app.db.session import get_db
from app.models.gold import GoldQuery, GoldResponse
from app.schemas.prediction import PricePredictionResponse, TrendPredictionResponse
from app.services.gemini_service import GoldAIService
from app.services.prediction_service import PredictionService


router = APIRouter(tags=["prediction"])
ai_service = GoldAIService()


@router.get("/predict", response_model=PricePredictionResponse)
def predict_price(
    days: int = Query(default=7, ge=1, le=365),
    model: str | None = Query(default=None, description="Model id or code"),
    source: str = Query(default="sjc", description="sjc or world"),
    range: str | None = Query(default=None, description="Optional input range tag, counted backward from the current date"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_current_user),
):
    service = PredictionService(db, current_user=current_user)
    return service.predict_price(days=days, model_identifier=model, source=source, range_value=range)


@router.get("/predict/trend", response_model=TrendPredictionResponse)
def predict_trend(
    days: int = Query(default=7, ge=1, le=365),
    model: str | None = Query(default=None, description="Model id or code"),
    source: str = Query(default="sjc", description="sjc or world"),
    range: str | None = Query(default=None, description="Optional input range tag, counted backward from the current date"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_current_user),
):
    service = PredictionService(db, current_user=current_user)
    return service.predict_trend(days=days, model_identifier=model, source=source, range_value=range)


@router.post("/assistant/queries", response_model=GoldResponse)
async def create_assistant_query(query: GoldQuery):
    answer = await ai_service.get_answer(query.question)
    return {"answer": answer}


@router.post("/ask", response_model=GoldResponse, include_in_schema=False)
async def ask_gold(query: GoldQuery):
    return await create_assistant_query(query)