from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from app.ai.utils import build_recent_prices_from_diffs


def _clean_price_history(history_prices: Iterable[float]) -> list[float]:
    cleaned: list[float] = []
    for value in history_prices:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(number):
            cleaned.append(number)
    return cleaned


def forecast_price_path(history_prices: Iterable[float], days: int, strategy: str = "linear") -> list[float]:
    prices = _clean_price_history(history_prices)
    if not prices:
        return [0.0 for _ in range(days)]

    if len(prices) == 1:
        return [round(float(prices[-1]), 4) for _ in range(days)]

    normalized_strategy = (strategy or "linear").strip().lower()

    if normalized_strategy == "momentum":
        deltas = np.diff(prices)
        recent_window = deltas[-min(len(deltas), 7):]
        mean_delta = float(np.mean(recent_window)) if len(recent_window) else 0.0
        current = prices[-1]
        predictions: list[float] = []
        for _ in range(days):
            current = max(0.0, current + mean_delta)
            predictions.append(round(float(current), 4))
        return predictions

    if normalized_strategy == "mean_reversion":
        anchor = float(np.mean(prices[-min(len(prices), 14):]))
        current = prices[-1]
        predictions: list[float] = []
        for _ in range(days):
            current = current + 0.35 * (anchor - current)
            predictions.append(round(max(0.0, float(current)), 4))
        return predictions

    x = np.arange(len(prices), dtype=float)
    y = np.asarray(prices, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    future_x = np.arange(len(prices), len(prices) + days, dtype=float)
    predictions = slope * future_x + intercept
    return [round(max(0.0, float(value)), 4) for value in predictions]


def classify_price_path(anchor_price: float, predicted_prices: Iterable[float]) -> tuple[list[str], list[float], str]:
    predictions = _clean_price_history(predicted_prices)
    if not predictions:
        return [], [], "flat"

    labels: list[str] = []
    scores: list[float] = []
    previous = float(anchor_price)
    for value in predictions:
        delta = float(value) - previous
        threshold = max(0.05, abs(previous) * 0.001)
        if delta > threshold:
            label = "up"
        elif delta < -threshold:
            label = "down"
        else:
            label = "flat"
        labels.append(label)
        scores.append(round(abs(delta) / max(abs(previous), 1.0), 4))
        previous = float(value)

    overall = labels[-1]
    return labels, scores, overall


def forecast_from_diffs(df_diff: pd.DataFrame | pd.Series | Iterable[float], last_actual_price: float, days: int, strategy: str = "linear") -> dict[str, object]:
    history_prices = build_recent_prices_from_diffs(df_diff, last_actual_price)
    predicted_prices = forecast_price_path(history_prices, days, strategy=strategy)
    trend_predictions, trend_scores, trend = classify_price_path(history_prices[-1], predicted_prices)
    return {
        "predictions": predicted_prices,
        "trend_predictions": trend_predictions,
        "trend_scores": trend_scores,
        "trend": trend,
        "used_fallback": True,
        "strategy": strategy,
        "history_prices": history_prices,
    }


class GoldPredictionEngine:
    def __init__(self, default_strategy: str = "linear") -> None:
        self.default_strategy = default_strategy

    def predict_future(self, df_diff, last_actual_sjc_price, days: int, strategy: str | None = None):
        return forecast_from_diffs(df_diff, last_actual_sjc_price, days, strategy or self.default_strategy)

    def predict_trend(self, df_diff, last_actual_sjc_price, days: int, strategy: str | None = None):
        result = self.predict_future(df_diff, last_actual_sjc_price, days, strategy=strategy)
        return {
            "trend_predictions": result["trend_predictions"],
            "trend_scores": result["trend_scores"],
            "trend": result["trend"],
            "used_fallback": result["used_fallback"],
        }