from __future__ import annotations

import re
import warnings

warnings.simplefilter("ignore", FutureWarning)

import google.generativeai as genai

from app.ai.engine import GoldPredictionEngine
from app.ai.utils import load_and_preprocess_data
from app.core.config import settings


ALLOWED_TOPIC_KEYWORDS = (
    "gold",
    "vàng",
    "sjc",
    "pnj",
    "giá",
    "price",
    "forecast",
    "dự báo",
    "dự đoán",
    "trend",
    "xu hướng",
    "model",
    "mô hình",
    "news",
    "tin tức",
    "history",
    "lịch sử",
    "export",
    "csv",
    "admin",
    "đăng nhập",
    "đăng ký",
    "login",
    "register",
    "spread",
    "arbitrage",
    "usd",
    "vnd",
    "biểu đồ",
    "chart",
)

IDENTITY_PATTERNS = (
    r"\bbạn là ai\b",
    r"\bem là ai\b",
    r"\bwho are you\b",
    r"\bwhat are you\b",
)

CAPABILITY_PATTERNS = (
    r"\bbạn có thể\b",
    r"\bhỗ trợ\b",
    r"\bhelp\b",
    r"\bwhat can you do\b",
    r"\bhướng dẫn\b",
)

FORECAST_INTENT_KEYWORDS = (
    "dự báo",
    "dự đoán",
    "forecast",
    "trend",
    "xu hướng",
    "ngày",
    "day",
    "week",
    "tuần",
    "month",
    "tháng",
)


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
        result = self.engine.predict_future(self.df_diff, self.last_price, days)
        return self._format_answer(days, result)

    def _summarize_with_gemini(self, question: str, days: int, result: dict[str, object]) -> str | None:
        if self.gemini_model is None:
            return None

        predictions = [float(value) for value in (result.get("predictions") or [])]  # type: ignore[arg-type]
        if not predictions:
            return None

        prompt = (
            "Bạn là trợ lý chuyên về giá vàng, dự báo, mô hình, tin tức, lịch sử và quản trị ứng dụng. "
            "Chỉ trả lời các chủ đề liên quan đến giá vàng. Nếu câu hỏi không liên quan, hãy từ chối ngắn gọn. "
            "Hãy viết một đoạn tóm tắt ngắn, rõ ràng, bằng tiếng Việt, tối đa 3 câu, không lan man. "
            f"Câu hỏi: {question}\n"
            f"Số ngày dự báo: {days}\n"
            f"Xu hướng: {result.get('trend', 'flat')}\n"
            f"Mức đầu: {predictions[0]:,.2f} triệu VND/lượng\n"
            f"Mức cuối: {predictions[-1]:,.2f} triệu VND/lượng\n"
        )

        try:
            response = self.gemini_model.generate_content(prompt)
            text = getattr(response, "text", None)
            if not text:
                return None
            cleaned = str(text).strip()
            lowered = cleaned.lower()
            if not any(keyword in lowered for keyword in ALLOWED_TOPIC_KEYWORDS):
                return None
            return cleaned
        except Exception:
            return None

    async def get_answer(self, question: str):
        if self._is_identity_question(question):
            return self._identity_answer()

        if self._is_capability_question(question):
            return self._capability_answer()

        if not self._is_relevant_question(question):
            return (
                "Tôi chỉ hỗ trợ các chủ đề liên quan đến giá vàng, dự báo, mô hình, tin tức, lịch sử, "
                "xuất CSV, đăng nhập và admin của ứng dụng này. Hãy hỏi về SJC, biểu đồ, model hoặc tin tức thị trường."
            )

        if self._is_model_question(question) and not self._is_forecast_intent(question):
            return self._model_answer()

        if self._is_news_question(question) and not self._is_forecast_intent(question):
            return self._news_answer()

        if self._is_history_question(question) and not self._is_forecast_intent(question):
            return self._history_answer()

        days = self._extract_days(question)
        result = self.engine.predict_future(self.df_diff, self.last_price, days)

        if self.gemini_model is None:
            return self._format_answer(days, result)

        summary = self._summarize_with_gemini(question, days, result)
        return self._format_answer(days, result, summary=summary)