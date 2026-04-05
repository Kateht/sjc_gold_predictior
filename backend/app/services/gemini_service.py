from __future__ import annotations

import re
import warnings

warnings.simplefilter("ignore", FutureWarning)

import google.generativeai as genai

from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data_for_gemini
from app.core.config import settings
class GoldAIService:
    def __init__(self):
        self.engine = GoldPredictionEngine()
        self.dataset_path = "dataset/final_dataset.csv"
        self.df_raw = None
        self.df_diff = None
        self.last_price = None
        self._dataset_loaded = False
        self._load_dataset_if_available()
        prompt_system = """
        Bạn là một Trợ lý AI Chuyên gia Phân tích Vàng SJC cao cấp.
        CÁCH LỰA CHỌN CÔNG CỤ DỰ ĐOÁN GIÁ:
        - Nếu người dùng KHÔNG chỉ định rõ, hãy dùng `predict_gold_price_lstm_tool` (LSTM Model mặc định).
        - Nếu người dùng yêu cầu dùng "XGBoost", "Mô hình cây", hoặc "ML", hãy gọi `predict_gold_price_xgboost_tool`.
        - Nếu người dùng hỏi xu hướng, gọi `predict_gold_trend_tool`.
        
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
            tools=[self.predict_gold_price_lstm_tool, self.predict_gold_trend_tool, self.predict_gold_price_xgboost_tool], # Thêm tool ở đây
            system_instruction=prompt_system
        )

    def _load_dataset_if_available(self) -> bool:
        if self._dataset_loaded:
            return True

        try:
            self.df_raw, self.df_diff, self.last_price = load_and_preprocess_data_for_gemini(self.dataset_path)
            self._dataset_loaded = True
            return True
        except FileNotFoundError:
            self.df_raw = None
            self.df_diff = None
            self.last_price = None
            return False

    def predict_gold_price_lstm_tool(self, days: int):
        """Dự đoán giá vàng trong tương lai."""
        if not self._load_dataset_if_available():
            return {"error": f"Không tìm thấy dataset tại: {self.dataset_path}"}
        return self.engine.predict_future_lstm(self.df_diff, self.last_price, days)
    
    def predict_gold_price_xgboost_tool(self, days: int):
        """Dự đoán giá vàng trong tương lai bằng XGBoost."""
        if not self._load_dataset_if_available():
            return {"error": f"Không tìm thấy dataset tại: {self.dataset_path}"}
        return self.engine.predict_future_xgb(self.df_raw, days) # Đổi thành df_raw
    def predict_gold_trend_tool(self):
        """Dự đoán XU HƯỚNG Tăng/Giảm của giá vàng ngày mai kèm mức độ tự tin (%)."""
        if not self._load_dataset_if_available():
            return {"error": f"Không tìm thấy dataset tại: {self.dataset_path}"}
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

    def _normalize_text(self, question: str) -> str:
        return re.sub(r"\s+", " ", question.lower()).strip()

    def _matches_any_pattern(self, text: str, patterns: tuple[str, ...]) -> bool:
        return any(re.search(pattern, text) for pattern in patterns)

    def _is_identity_question(self, question: str) -> bool:
        return self._matches_any_pattern(self._normalize_text(question), IDENTITY_PATTERNS)

    def _is_capability_question(self, question: str) -> bool:
        return self._matches_any_pattern(self._normalize_text(question), CAPABILITY_PATTERNS)

    def _is_forecast_intent(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return any(keyword in normalized for keyword in FORECAST_INTENT_KEYWORDS)

    def _is_model_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return "model" in normalized or "mô hình" in normalized

    def _is_news_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return "news" in normalized or "tin tức" in normalized or "headline" in normalized

    def _is_history_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return "history" in normalized or "lịch sử" in normalized or "csv" in normalized or "export" in normalized

    def _identity_answer(self) -> str:
        return (
            "Tôi là trợ lý AI của ứng dụng dự báo giá vàng SJC.\n"
            "Tôi hỗ trợ các câu hỏi về biểu đồ giá, dự báo theo số ngày, so sánh model, tin tức, lịch sử và thao tác admin trong hệ thống này."
        )

    def _capability_answer(self) -> str:
        return (
            "Tôi có thể hỗ trợ các nhóm việc sau:\n"
            "- Phân tích nhanh xu hướng giá vàng SJC theo 7/14/30 ngày.\n"
            "- Gợi ý cách đọc chart, zoom, đổi range và xem theo tháng trong năm.\n"
            "- Trả lời về model dự báo, tin tức thị trường, lịch sử dự báo và xuất CSV.\n"
            "- Hướng dẫn thao tác trang admin như model active/default và crawler runs."
        )

    def _model_answer(self) -> str:
        return (
            "Bạn có thể xem toàn bộ model active ngay trên Dashboard và vào Predict để chạy từng model theo số ngày.\n"
            "Gợi ý nhanh:\n"
            "- Mô hình `price` để xem mức giá dự báo.\n"
            "- Mô hình `trend` để xem hướng đi lên/đi xuống.\n"
            "Nếu muốn, hãy hỏi tôi: 'So sánh model cho dự báo 7 ngày'."
        )

    def _news_answer(self) -> str:
        return (
            "Bạn có thể mở trang News để lọc theo nhóm chủ đề và theo dõi bài featured trước.\n"
            "Tôi có thể giúp tóm tắt tác động của tin tức lên giá vàng nếu bạn nêu cụ thể 1 headline hoặc 1 nhóm tin."
        )

    def _history_answer(self) -> str:
        return (
            "Trang History cho phép xem các lần dự báo trước đó và xuất CSV.\n"
            "Nếu bạn muốn truy xuất theo khoảng thời gian, tôi có thể gợi ý cách lọc dữ liệu trước khi export."
        )

    def _is_relevant_question(self, question: str) -> bool:
        normalized = self._normalize_text(question)
        return (
            any(keyword in normalized for keyword in ALLOWED_TOPIC_KEYWORDS)
            or self._is_identity_question(question)
            or self._is_capability_question(question)
        )

    def _format_answer(self, days: int, result: dict[str, object], summary: str | None = None) -> str:
        predictions = [float(value) for value in (result.get("predictions") or [])]  # type: ignore[arg-type]
        trend_predictions = [str(value) for value in (result.get("trend_predictions") or [])]  # type: ignore[arg-type]
        trend_scores = [float(value) for value in (result.get("trend_scores") or [])]  # type: ignore[arg-type]
        trend = str(result.get("trend", "flat"))

        if not predictions:
            return "Tôi chưa lấy được chuỗi dự báo hợp lệ cho câu hỏi này."

        first_price = predictions[0]
        last_price = predictions[-1]
        min_price = min(predictions)
        max_price = max(predictions)
        summary_text = summary or f"Dự báo {days} ngày tới đang cho thấy xu hướng {trend}."

        lines = [
            "Tóm tắt:",
            f"- {summary_text}",
            f"- Mức đầu: {first_price:,.2f} triệu VND/lượng.",
            f"- Mức cuối: {last_price:,.2f} triệu VND/lượng.",
            "",
            "Diễn biến dự báo:",
        ]

        preview_count = min(len(predictions), 5)
        for index in range(preview_count):
            trend_label = trend_predictions[index] if index < len(trend_predictions) else trend
            score = trend_scores[index] if index < len(trend_scores) else 0.0
            lines.append(
                f"- Ngày {index + 1}: {predictions[index]:,.2f} triệu VND/lượng ({trend_label}, độ tin cậy {score:.0%})"
            )

        if len(predictions) > preview_count:
            lines.append(f"- ... còn {len(predictions) - preview_count} mốc nữa trong chuỗi dự báo.")

        lines.extend([
            "",
            "Điểm cần theo dõi:",
            f"- Khoảng giá ước tính: {min_price:,.2f} đến {max_price:,.2f} triệu VND/lượng.",
            "- Tôi có thể so sánh thêm với giá thế giới, model đang chọn, hoặc lịch sử gần nhất nếu bạn muốn.",
        ])

        return "\n".join(lines)

    def fallback_agent(self, question: str):
        days = self._extract_days(question)
        # Sửa lỗi: Gọi đúng tên hàm predict_future_lstm
        if not self._load_dataset_if_available():
            return f"Không tìm thấy dataset tại: {self.dataset_path}. Chưa thể tạo dự báo."
        result = self.engine.predict_future_lstm(self.df_diff, self.last_price, days)
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
                # 1. Nếu Gemini gọi LSTM (Sửa lại đúng tên)
                if fc.name == "predict_gold_price_lstm_tool":
                    days = int(fc.args["days"]) if "days" in fc.args else 1
                    result = self.engine.predict_future_lstm(self.df_diff, self.last_price, days)
                
                # 2. Nếu Gemini gọi XGBoost (Thêm nhánh bị thiếu này vào)
                elif fc.name == "predict_gold_price_xgboost_tool":
                    days = int(fc.args["days"]) if "days" in fc.args else 1
                    # Truyền df_raw và KHÔNG cần truyền self.last_price
                    result = self.engine.predict_future_xgb(self.df_raw, days)

                # 3. Nếu Gemini gọi Tool Dự đoán Xu hướng
                elif fc.name == "predict_gold_trend_tool":
                    result = self.engine.predict_trend_classification(self.df_diff)
                
                # Trường hợp không khớp tool nào
                else:
                    return f"Lỗi: Không tìm thấy chức năng {fc.name}."

                # 3. GỬI KẾT QUẢ CHO GEMINI VỚI LỊCH SỬ CHUẨN
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

            # Nếu Gemini chỉ trả lời text bình thường
            return response.text

        except Exception as e:
            print(f"❌ Lỗi Gemini/Model: {e}") 
            return self.fallback_agent(question)