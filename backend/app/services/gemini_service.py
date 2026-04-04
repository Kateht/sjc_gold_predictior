from unittest import result

import google.generativeai as genai
from app.core.config import settings
from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data

class GoldAIService:
    def __init__(self):
        self.engine = GoldPredictionEngine()
        self.df_diff, self.last_price = load_and_preprocess_data("dataset/final_dataset_new.csv")
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
            
            # Kiểm tra xem Gemini có muốn gọi Tool không
            if response.candidates[0].content.parts[0].function_call:
                fc = response.candidates[0].content.parts[0].function_call

                # 1. Nếu Gemini gọi Tool Dự đoán Giá (Regression)
                if fc.name == "predict_gold_price_tool":
                    days = int(fc.args["days"])
                    result = self.engine.predict_future(self.df_diff, self.last_price, days)
                
                # 2. Nếu Gemini gọi Tool Dự đoán Xu hướng (Classification)
                elif fc.name == "predict_gold_trend_tool":
                    result = self.engine.predict_trend_classification(self.df_diff)
                
                # Trường hợp không khớp tool nào
                else:
                    return f"Lỗi: Không tìm thấy chức năng {fc.name}."

                # 3. Gửi lại kết quả (JSON) của bất kỳ tool nào về cho Gemini
                final_response = self.gemini_model.generate_content([
                    question,
                    {
                        "function_response": {
                            "name": fc.name, # Dùng luôn fc.name để code tự động khớp tên Tool
                            "response": result
                        }
                    }
                ])

                return final_response.text

            # Nếu Gemini chỉ trả lời text bình thường (không gọi tool)
            return response.text

        except Exception as e:
            print(f"❌ Lỗi Gemini/Model: {e}") # In ra Terminal để bạn dễ debug
            return self.fallback_agent(question)