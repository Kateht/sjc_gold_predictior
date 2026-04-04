from __future__ import annotations

from app.ai.utils import limit_history_frame, load_price_history_frame, normalize_source


def get_price_chart(range_value: str = "30d", source: str = "sjc") -> dict[str, list]:
    frame = load_price_history_frame(source)
    frame = limit_history_frame(frame, range_value)
    return {
        "dates": [timestamp.strftime("%Y-%m-%d") for timestamp in frame["date"]],
        "prices": [round(float(value), 4) for value in frame["price"]],
    }


def load_history_for_source(source: str = "sjc"):
    normalized_source = normalize_source(source)
    frame = load_price_history_frame(normalized_source)
    return frame, normalized_source