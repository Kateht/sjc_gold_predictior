from __future__ import annotations

import re
import warnings

warnings.simplefilter("ignore", FutureWarning)

import google.generativeai as genai

from app.core.config import settings
from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data

class GoldAIService:
    def __init__(self):
        self.engine = GoldPredictionEngine()
        self.df_diff, self.last_price = load_and_preprocess_data(settings.LOCAL_DATASET_PATH)
        self.gemini_model = None

        if settings.ENABLE_GEMINI and settings.GEMINI_API_KEY:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self.gemini_model = genai.GenerativeModel(model_name=settings.GEMINI_MODEL_NAME)

    def _extract_days(self, question: str) -> int:
        q = question.lower()
        match = re.search(r"(\d+)\s*(ngày|day|days)", q)
        if match:
            return max(1, min(365, int(match.group(1))))

        if "30" in q or "tháng" in q or "month" in q:
            return 30
        if "14" in q or "2 tuần" in q:
            return 14
        if "7" in q or "tuần" in q or "week" in q:
            return 7
        if "5" in q:
            return 5
        if "3" in q:
            return 3
        return 1

    def fallback_agent(self, question: str):
        days = self._extract_days(question)
        result = self.engine.predict_future(self.df_diff, self.last_price, days)
        preds = result["predictions"]
        trend = result["trend"]
        answer = f"""Du doan gia vang {days} ngay toi:

    Xu huong: {trend}
    Gia bat dau: {preds[0]:,.2f} trieu
    Gia ket thuc: {preds[-1]:,.2f} trieu

    Chi tiet theo ngay:
    """
        for i, p in enumerate(preds, 1):
            answer += f"  Ngay {i}: {p:,.2f} trieu\n"

        answer += f"\nNhan dinh: Gia vang co xu huong {trend} trong {days} ngay toi."

        return answer.strip()

    async def get_answer(self, question: str):
        if self.gemini_model is None:
            return self.fallback_agent(question)

        try:
            prompt = (
                "Bạn là trợ lý dự báo giá vàng SJC. "
                "Nếu câu hỏi liên quan đến xu hướng hoặc số ngày dự báo, hãy trả lời ngắn gọn, rõ ràng, có thể nhắc tới model dự báo. "
                f"Câu hỏi: {question}"
            )
            response = self.gemini_model.generate_content(prompt)
            text = getattr(response, "text", None)
            if text:
                return text
        except Exception:
            pass

        return self.fallback_agent(question)