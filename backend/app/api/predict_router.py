from fastapi import APIRouter
from app.models.gold import GoldQuery, GoldResponse
from app.services.gemini_service import GoldAIService

router = APIRouter()
ai_service = GoldAIService()

@router.post("/ask", response_model=GoldResponse)
async def ask_gold(query: GoldQuery):
    answer = await ai_service.get_answer(query.question)
    return {"answer": answer}