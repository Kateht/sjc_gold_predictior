from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score

from app.ai.engine import XGB_FEATURE_COLUMNS, _get_engine, _prepare_xgb_feature_frame
from app.ai.utils import load_and_preprocess_data_for_gemini, load_feature_dataset_frame
from app.core.config import settings


logger = logging.getLogger(__name__)

DEFAULT_REGRESSION_METRICS: dict[str, float | None] = {
    "mae": None,
    "rmse": None,
    "mape": None,
    "r2": None,
}

PRICE_MODEL_CODES = (
    "best-xgb-price-v1",
    "lstm-k10-price-v1",
    "gru-price-v1",
)


def _clone_default_metrics() -> dict[str, float | None]:
    return dict(DEFAULT_REGRESSION_METRICS)


def _sanitize_metric_value(value: float | int | np.floating | None) -> float | None:
    if value is None:
        return None

    numeric_value = float(value)
    if not np.isfinite(numeric_value):
        return None
    return round(numeric_value, 4)


def _build_metric_payload(actual_values: list[float], predicted_values: list[float]) -> dict[str, float | None]:
    if len(actual_values) < 2 or len(predicted_values) < 2:
        return _clone_default_metrics()

    actual_array = np.asarray(actual_values, dtype=float)
    predicted_array = np.asarray(predicted_values, dtype=float)
    finite_mask = np.isfinite(actual_array) & np.isfinite(predicted_array)
    actual_array = actual_array[finite_mask]
    predicted_array = predicted_array[finite_mask]

    if actual_array.size < 2 or predicted_array.size < 2:
        return _clone_default_metrics()

    try:
        mae = mean_absolute_error(actual_array, predicted_array)
        rmse = float(np.sqrt(mean_squared_error(actual_array, predicted_array)))
        mape = mean_absolute_percentage_error(actual_array, predicted_array) * 100.0
        r2 = r2_score(actual_array, predicted_array)
    except ValueError as exc:
        logger.warning("Regression metric calculation failed: %s", exc)
        return _clone_default_metrics()

    return {
        "mae": _sanitize_metric_value(mae),
        "rmse": _sanitize_metric_value(rmse),
        "mape": _sanitize_metric_value(mape),
        "r2": _sanitize_metric_value(r2),
    }


def _resolve_holdout_size(total_rows: int, requested_days: int | None = None) -> int:
    if total_rows <= 2:
        return 0

    if requested_days is None:
        requested_days = min(120, max(30, total_rows // 20))

    return max(1, min(requested_days, total_rows - 1))


def _evaluate_lstm_metrics(engine, raw_frame: pd.DataFrame, diff_frame: pd.DataFrame, holdout_days: int) -> dict[str, float | None]:
    if not getattr(engine, "feature_cols", None) or getattr(engine, "best_k", 0) <= 0:
        return _clone_default_metrics()

    total_rows = len(raw_frame)
    start_index = max(engine.best_k, total_rows - holdout_days - 1)
    if start_index >= total_rows - 1:
        return _clone_default_metrics()

    actual_values: list[float] = []
    predicted_values: list[float] = []
    is_dl_model = not hasattr(engine.ml_model, "coef_") and not hasattr(engine.ml_model, "support_")

    for cutoff_index in range(start_index, total_rows - 1):
        window = engine._prepare_feature_window(diff_frame.iloc[:cutoff_index], engine.feature_cols, engine.best_k)
        current_window_diff = engine.scaler_X.transform(window)

        if not is_dl_model:
            x_input = current_window_diff.reshape(1, -1)
            predicted_delta_scaled = engine.ml_model.predict(x_input)
        else:
            x_input = current_window_diff.reshape(1, engine.best_k, len(engine.feature_cols))
            predicted_delta_scaled = engine.ml_model.predict(x_input, verbose=0)

        predicted_delta_real = engine.scaler_y.inverse_transform(np.asarray(predicted_delta_scaled).reshape(-1, 1))[0][0]
        current_price = float(raw_frame["SJC"].iloc[cutoff_index])
        actual_price = float(raw_frame["SJC"].iloc[cutoff_index + 1])

        actual_values.append(actual_price)
        predicted_values.append(float(current_price + float(predicted_delta_real)))

    return _build_metric_payload(actual_values, predicted_values)


def _evaluate_gru_metrics(engine, feature_frame: pd.DataFrame, holdout_days: int) -> dict[str, float | None]:
    gru_model = getattr(engine, "gru_model", None)
    feature_columns = list(getattr(engine, "gru_feature_cols", None) or [])
    if gru_model is None or not feature_columns:
        return _clone_default_metrics()

    working = feature_frame.sort_values("date").reset_index(drop=True)
    total_rows = len(working)
    start_index = max(7, total_rows - holdout_days - 1)
    if start_index >= total_rows - 1:
        return _clone_default_metrics()

    actual_values: list[float] = []
    predicted_values: list[float] = []

    for cutoff_index in range(start_index, total_rows - 1):
        current_row = working.iloc[cutoff_index].copy()
        for column in feature_columns:
            if column not in current_row.index:
                current_row[column] = 0.0

        input_values = (
            pd.to_numeric(current_row[feature_columns], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
            .to_numpy(dtype=float)
            .reshape(1, 1, len(feature_columns))
        )

        predicted_delta = float(np.ravel(gru_model.predict(input_values, verbose=0))[0])
        current_price = float(working["SJC"].iloc[cutoff_index])
        actual_price = float(working["SJC"].iloc[cutoff_index + 1])

        actual_values.append(actual_price)
        predicted_values.append(current_price + predicted_delta)

    return _build_metric_payload(actual_values, predicted_values)


def _evaluate_xgb_metrics(engine, raw_frame: pd.DataFrame, holdout_days: int) -> dict[str, float | None]:
    xgb_model = getattr(engine, "xgb_model", None)
    feature_columns = list(getattr(engine, "xgb_features", None) or XGB_FEATURE_COLUMNS)
    if xgb_model is None:
        return _clone_default_metrics()

    prepared_frame = _prepare_xgb_feature_frame(raw_frame)
    total_rows = len(prepared_frame)
    start_index = max(7, total_rows - holdout_days - 1)
    if start_index >= total_rows - 1:
        return _clone_default_metrics()

    scaler = None
    try:
        from sklearn.preprocessing import MinMaxScaler

        scaler = MinMaxScaler()
        scaler.fit(prepared_frame[feature_columns])
    except Exception as exc:
        logger.warning("Could not fit the XGBoost scaler for metrics: %s", exc)
        return _clone_default_metrics()

    actual_values: list[float] = []
    predicted_values: list[float] = []

    for cutoff_index in range(start_index, total_rows - 1):
        current_row = prepared_frame.iloc[cutoff_index][feature_columns].copy()
        input_frame = pd.DataFrame([current_row], columns=feature_columns)
        input_scaled = scaler.transform(input_frame)

        predicted_delta = float(xgb_model.predict(input_scaled)[0])
        current_price = float(prepared_frame["SJC"].iloc[cutoff_index])
        actual_price = float(prepared_frame["SJC"].iloc[cutoff_index + 1])

        actual_values.append(actual_price)
        predicted_values.append(current_price + predicted_delta)

    return _build_metric_payload(actual_values, predicted_values)


def get_price_model_metrics(holdout_days: int | None = None) -> dict[str, dict[str, float | None]]:
    engine = _get_engine()
    raw_frame, diff_frame, _ = load_and_preprocess_data_for_gemini(settings.LOCAL_DATASET_PATH)
    feature_frame = load_feature_dataset_frame(settings.LOCAL_DATASET_PATH)
    resolved_holdout_days = _resolve_holdout_size(len(raw_frame), requested_days=holdout_days)

    metrics_by_model: dict[str, dict[str, float | None]] = {}
    for code in PRICE_MODEL_CODES:
        metrics_by_model[code] = _clone_default_metrics()

    try:
        metrics_by_model["best-xgb-price-v1"] = _evaluate_xgb_metrics(engine, raw_frame, resolved_holdout_days)
    except Exception as exc:
        logger.warning("Failed to compute XGBoost regression metrics: %s", exc)

    try:
        metrics_by_model["lstm-k10-price-v1"] = _evaluate_lstm_metrics(engine, raw_frame, diff_frame, resolved_holdout_days)
    except Exception as exc:
        logger.warning("Failed to compute LSTM regression metrics: %s", exc)

    try:
        metrics_by_model["gru-price-v1"] = _evaluate_gru_metrics(engine, feature_frame, resolved_holdout_days)
    except Exception as exc:
        logger.warning("Failed to compute GRU regression metrics: %s", exc)

    return metrics_by_model
