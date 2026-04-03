from unittest import result

import google.generativeai as genai
from app.core.config import settings
from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data

class GoldAIService:
    def __init__(self):
        self.engine = GoldPredictionEngine()
        self.df_diff, self.last_price = load_and_preprocess_data("dataset/final_dataset_new.csv")
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash", # Updated to stable version
            tools=[self.predict_gold_price_tool]
        )

    def predict_gold_price_tool(self, days: int):
        """Dự đoán giá vàng trong tương lai."""
        return self.engine.predict_future(self.df_diff, self.last_price, days)

    def fallback_agent(self, question: str):
        q = question.lower()

    # Parse số ngày từ câu hỏi
        days = 1
        if "30" in q or "tháng" in q or "month" in q:
            days = 30
        elif "14" in q or "2 tuần" in q:
            days = 14
        elif "7" in q or "tuần" in q or "week" in q:
            days = 7
        elif "3" in q:
            days = 3
        elif "5" in q:
            days = 5
        elif "10" in q:
            days = 10        
        result = self.engine.predict_future(self.df_diff, self.last_price, days)
        preds = result["predictions"]
        trend = result["trend"]
        answer = f"""📊 Dự đoán giá vàng {days} ngày tới:

    🔹 Xu hướng: {trend}
    🔹 Giá bắt đầu: {preds[0]:,.2f} triệu
    🔹 Giá kết thúc: {preds[-1]:,.2f} triệu

    📈 Chi tiết theo ngày:
    """
        for i, p in enumerate(preds, 1):
            answer += f"  Ngày {i}: {p:,.2f} triệu\n"

        answer += f"\n👉 Nhận định: Giá vàng có xu hướng {trend} trong {days} ngày tới."

        return answer.strip()

    async def get_answer(self, question: str):
        try:
            response = self.gemini_model.generate_content(question)
            if response.candidates[0].content.parts[0].function_call:
                fc = response.candidates[0].content.parts[0].function_call

                if fc.name == "predict_gold_price":
                    days = int(fc.args["days"])
                    result = self.engine.predict_future(self.df_diff, self.last_price,days)

                    # Gửi lại kết quả cho Gemini để nó trả lời đẹp
                    final_response = self.gemini_model.generate_content([
                        question,
                        {
                            "function_response": {
                                "name": "predict_gold_price",
                                "response": result
                            }
                        }
                    ])

                    return final_response.text
            return response.text
        except Exception:
            return self.fallback_agent(question)