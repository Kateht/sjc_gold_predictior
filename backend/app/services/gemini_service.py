from __future__ import annotations

import re
import warnings

warnings.simplefilter("ignore", FutureWarning)

import google.generativeai as genai

from app.core.config import settings
from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data1

class GoldAIService:
    def __init__(self):
        self.engine = GoldPredictionEngine()
        self.df_diff, self.last_price = load_and_preprocess_data1("dataset/final_dataset.csv")
        prompt_system = """
        Bạn là một Trợ lý AI Chuyên gia Phân tích Vàng SJC cao cấp.
        
        1. NẾU BẠN SỬ DỤNG CÔNG CỤ DỰ ĐOÁN XU HƯỚNG (Classification Tool):
        Hãy trình bày kết quả trả về theo đúng format sau:
        📊 Dự báo xu hướng giá vàng SJC: [Tăng/Giảm] [📈/📉]
        🔹 Tỷ lệ dự đoán Tăng: [up_probability]%
        🔹 Tỷ lệ dự đoán Giảm: [down_probability]%
        🔹 Mức độ tự tin (Confidence): [confidence_percent]%
        👉 Nhận định ngắn gọn từ bạn: [Viết 1 câu khuyên nhà đầu tư]

        2. NẾU BẠN SỬ DỤNG CÔNG CỤ DỰ ĐOÁN GIÁ (Regression Tool):
        Hãy trình bày kết quả trả về theo đúng format sau:
        💰 Dự báo giá vàng SJC:
        🔹 Giá kết thúc kỳ vọng: [Điền giá trị được format có dấu chấm ngăn cách hàng nghìn] VNĐ
        🔹 Xu hướng chung: [Tăng/Giảm]
        📈 Quỹ đạo chi tiết:
        [Liệt kê giá từng ngày]
        👉 Nhận định ngắn gọn từ bạn: [Viết 1 câu khuyên nhà đầu tư]
        """
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash-lite",
            tools=[self.predict_gold_price_tool, self.predict_gold_trend_tool], # Thêm tool ở đây
            system_instruction=prompt_system
        )

    def predict_gold_price_tool(self, days: int):
        """Dự đoán giá vàng trong tương lai."""
        return self.engine.predict_future(self.df_diff, self.last_price, days)
    

    def predict_gold_trend_tool(self):
        """Dự đoán XU HƯỚNG Tăng/Giảm của giá vàng ngày mai kèm mức độ tự tin (%)."""
        return self.engine.predict_trend_classification(self.df_diff)

    def _extract_days(self, question: str):
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
        try:
            response = self.gemini_model.generate_content(question)
            
            # TÌM TẤT CẢ CÁC PARTS, XEM CÓ PART NÀO GỌI TOOL KHÔNG
            fc = None
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        fc = part.function_call
                        break

            if fc:
                # 1. Nếu Gemini gọi Tool Dự đoán Giá (Regression)
                if fc.name == "predict_gold_price_tool":
                    days = int(fc.args["days"]) if "days" in fc.args else 1
                    result = self.engine.predict_future(self.df_diff, self.last_price, days)
                
                # 2. Nếu Gemini gọi Tool Dự đoán Xu hướng (Classification)
                elif fc.name == "predict_gold_trend_tool":
                    result = self.engine.predict_trend_classification(self.df_diff)
                
                # Trường hợp không khớp tool nào
                else:
                    return f"Lỗi: Không tìm thấy chức năng {fc.name}."

                # 3. GỬI KẾT QUẢ CHO GEMINI VỚI LỊCH SỬ CHUẨN (SỬA LỖI Ở ĐÂY)
                messages = [
                    {"role": "user", "parts": [question]},
                    response.candidates[0].content,  # Nhắc cho Gemini nhớ nó vừa gọi Tool gì
                    {"role": "user", "parts": [{
                        "function_response": {
                            "name": fc.name,
                            "response": result
                        }
                    }]}
                ]
                
                final_response = self.gemini_model.generate_content(messages)
                return final_response.text

            # Nếu Gemini chỉ trả lời text bình thường (không gọi tool)
            return response.text

        except Exception as e:
            print(f"❌ Lỗi Gemini/Model: {e}") 
            return self.fallback_agent(question)