from pathlib import Path
import warnings

from app.ai.utils import load_feature_dataset_frame, load_feature_prediction_data
from app.core.config import settings
import tensorflow as tf
import keras
import numpy as np
import pandas as pd
import joblib
import json
from sklearn.preprocessing import MinMaxScaler

GRU_FEATURE_COLUMNS = [
    'Interest', 'CPI', 'Real_Yield_10Y', 'Gold_Close', 'Gold_High', 'Gold_Low', 'Gold_Volume',
    'USD_index_Close', 'Oil_Close', 'USD_VND_Close', 'GVZ_Close', 'VIX_Close', 'ETF_Holdings_Close',
    'MOVE_Index_Close', 'Gold_world_vnd', 'SJC_Premium', 'SJC_Premium_Percent', 'Shock_Index',
    'SJC_lag1', 'SJC_lag7', 'SJC_ma7', 'Gold_return', 'Gold_volume_rank', 'Gold_range',
    'Gold_volatility_7', 'Gold_momentum', 'Gold_Volume_Anomaly', 'PVT'
]

TREND_XGB_FEATURE_COLUMNS = [
    'Gold_return', 'SJC_Premium_Zscore', 'Bitcoin_return', 'Gold_Volume_Anomaly', 'Bitcoin_Close',
    'Gold_volume_rank', 'Gold_momentum', 'SP500_return', 'VNIndex_ETF_return', 'SJC_Premium_Percent',
    'Policy_Risk_Zone', 'Shock_Index', 'Real_Yield_10Y'
]


def _build_runtime_scaler(frame: pd.DataFrame, feature_columns: list[str]) -> MinMaxScaler:
    if not feature_columns:
        # Avoid scikit-learn crashing on empty feature sets during app startup.
        # Callers should generally treat an empty feature list as "no model".
        scaler = MinMaxScaler()
        scaler.fit(pd.DataFrame({"__dummy__": [0.0, 1.0]}))
        return scaler

    working = frame.copy()
    for column in feature_columns:
        if column not in working.columns:
            working[column] = 0.0

    scaler_frame = (
        working[feature_columns]
        .apply(pd.to_numeric, errors='coerce')
        .replace([np.inf, -np.inf], np.nan)
        .fillna(0.0)
    )

    scaler = MinMaxScaler()
    scaler.fit(scaler_frame)
    return scaler



_original_dense_init = keras.layers.Dense.__init__

def _patched_dense_init(self, *args, **kwargs):
    kwargs.pop('quantization_config', None)
    _original_dense_init(self, *args, **kwargs)

keras.layers.Dense.__init__ = _patched_dense_init

class GoldPredictionEngine:
    def __init__(self):
        feature_frame = load_feature_dataset_frame()

        
        self.meta = joblib.load(f"{settings.MODEL_DIR}/meta_lstm_k10.pkl")
        diff_frame, _, _ = load_feature_prediction_data(required_columns=set(self.meta["feature_columns"]) | {"SJC"})
        self.scaler_X = _build_runtime_scaler(diff_frame, list(self.meta["feature_columns"]))
        self.scaler_y = _build_runtime_scaler(diff_frame[["SJC"]].copy(), ["SJC"])
        self.ml_model = keras.models.load_model(f"{settings.MODEL_DIR}/lstm_k10.keras")
        try:
            self.gru_model = keras.models.load_model(f"{settings.MODEL_DIR}/best_gru.h5", compile=False)
            self.gru_feature_cols = list(GRU_FEATURE_COLUMNS)
            expected_gru_features = int(self.gru_model.input_shape[-1]) if getattr(self.gru_model, "input_shape", None) else len(self.gru_feature_cols)
            if len(self.gru_feature_cols) != expected_gru_features:
                print(
                    f"Warning: GRU feature count mismatch: expected {expected_gru_features}, got {len(self.gru_feature_cols)}."
                )
            else:
                print("Loaded GRU model successfully.")
        except Exception as e:
            print(f"Warning: could not load GRU model: {e}")
            self.gru_model = None
            self.gru_feature_cols = []
        
        self.best_k = self.meta["best_k"]
        self.feature_cols = self.meta["feature_columns"]
        #  LOAD MODEL PHÂN LOẠI (DỰ ĐOÁN XU HƯỚNG)
        self.trend_model_kind = "builtin"
        self.trend_model = None
        self.trend_scaler = None
        self.clf_features = list(TREND_XGB_FEATURE_COLUMNS)
        self.clf_time_steps = 1
        self.trend_meta = {}

        xgb_trend_model_path = Path(settings.MODEL_DIR) / "xgb_classifier_sjc.joblib"
        xgb_trend_meta_path = Path(settings.MODEL_DIR) / "xgb_metadata.json"
        legacy_trend_model_path = Path(settings.MODEL_DIR) / "sjc_classification.h5"

        if xgb_trend_model_path.exists():
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r".*If you are loading a serialized model.*",
                    category=UserWarning,
                )
                self.trend_model = joblib.load(xgb_trend_model_path)
            self.trend_model_kind = "xgb"
            if xgb_trend_meta_path.exists():
                with open(xgb_trend_meta_path, 'r', encoding='utf-8') as file_handle:
                    self.trend_meta = json.load(file_handle)
            feature_names_in = getattr(self.trend_model, "feature_names_in_", None)
            if feature_names_in is not None:
                feature_names_in = list(feature_names_in)
            self.clf_features = list(
                feature_names_in
                or self.trend_meta.get("features_list")
                or TREND_XGB_FEATURE_COLUMNS
            )
            self.clf_time_steps = 1
            self.trend_scaler = _build_runtime_scaler(feature_frame, self.clf_features)
            print("Loaded XGBoost classification model successfully.")
        elif legacy_trend_model_path.exists():
            self.meta_clf = joblib.load(f"{settings.MODEL_DIR}/meta.pkl")
            self.clf_features = list(self.meta_clf.get("features") or [])
            self.clf_time_steps = int(self.meta_clf.get("time_steps", 21))
            if not self.clf_features:
                print(
                    "Warning: legacy classification metadata has no features; "
                    "skipping legacy trend model and using fallback."
                )
                self.trend_model_kind = "builtin"
                self.trend_model = None
                self.trend_scaler = None
            else:
                self.trend_scaler = _build_runtime_scaler(feature_frame, self.clf_features)
                self.trend_model = tf.keras.models.load_model(legacy_trend_model_path, compile=False)
                self.trend_model_kind = "keras"
                print("Loaded legacy Keras classification model successfully.")
        else:
            print("Warning: could not load classification model; fallback will be used.")

    def predict_future_lstm(self, df_diff, last_actual_sjc_price, days: int):
        print("Predict lstm")
        latest_data_diff = df_diff.tail(self.best_k)[self.feature_cols]
        current_window_diff = self.scaler_X.transform(latest_data_diff)

        predictions = []
        current_absolute_price = last_actual_sjc_price
        
        is_dl_model = not hasattr(self.ml_model, "coef_") and not hasattr(self.ml_model, "support_")

        for _ in range(days):
            if not is_dl_model:
                X_input = current_window_diff.reshape(1, -1)
                pred_delta_scaled = self.ml_model.predict(X_input)
            else:
                X_input = current_window_diff.reshape(1, self.best_k, len(self.feature_cols))
                pred_delta_scaled = self.ml_model.predict(X_input, verbose=0)

            pred_delta_real = self.scaler_y.inverse_transform(pred_delta_scaled.reshape(-1, 1))[0][0]
            next_absolute_price = current_absolute_price + pred_delta_real
            predictions.append(float(next_absolute_price))
            
            current_absolute_price = next_absolute_price

            # TẠO DÒNG MỚI ĐỂ TRƯỢT CỬA SỔ
            new_delta_row = np.zeros(len(self.feature_cols))
            
            if "SJC" in self.feature_cols:
                target_idx = self.feature_cols.index("SJC")
                new_delta_row[target_idx] = np.ravel(pred_delta_scaled)[0]
                
            current_window_diff = np.vstack([current_window_diff[1:], new_delta_row])

        trend_predictions, trend_scores, trend = summarize_price_path(float(last_actual_sjc_price), predictions)
        trend_label = "tăng 📈" if trend == "up" else "giảm 📉" if trend == "down" else "đi ngang"
        return {
            "predictions": predictions,
            "base_price": float(last_actual_sjc_price),
            "trend": trend_label,
            "trend_predictions": trend_predictions,
            "trend_scores": trend_scores,
        }
    

    def predict_trend_classification(self, df_diff):
        print("Predict classi")
        model_kind = getattr(self, "trend_model_kind", "builtin")
        model_features = list(getattr(self, "clf_features", []))

        if model_kind == "xgb" and self.trend_model is not None:
            working = df_diff.copy()
            for col in model_features:
                if col not in working.columns:
                    print(f"Warning: missing column '{col}'. Filling with 0.")
                    working[col] = 0.0

            latest_row = (
                working[model_features]
                .tail(1)
                .apply(pd.to_numeric, errors='coerce')
                .replace([np.inf, -np.inf], np.nan)
                .fillna(0.0)
            )

            scaler = self.trend_scaler or _build_runtime_scaler(working, model_features)
            X_input_scaled = scaler.transform(latest_row)

            if hasattr(self.trend_model, "predict_proba"):
                pred_prob = self.trend_model.predict_proba(X_input_scaled)
            else:
                pred_prob = self.trend_model.predict(X_input_scaled)

            prob = np.ravel(pred_prob)
            if len(prob) == 1:
                up_prob = float(prob[0]) * 100.0
                down_prob = 100.0 - up_prob
            else:
                down_prob = float(prob[0]) * 100.0
                up_prob = float(prob[1]) * 100.0

            trend_result = "Tăng" if up_prob > 50 else "Giảm"
            confidence = max(up_prob, down_prob)

            return {
                "predicted_trend": trend_result,
                "confidence_percent": round(float(confidence), 2),
                "up_probability": round(float(up_prob), 2),
                "down_probability": round(float(down_prob), 2),
            }

        if model_kind == "keras" and self.trend_model is not None:
            for col in model_features:
                if col not in df_diff.columns:
                    print(f"Warning: missing column '{col}'. Filling with 0.")
                    df_diff[col] = 0.0

            latest_data_diff = df_diff[model_features].tail(self.clf_time_steps).copy()
            if len(latest_data_diff) < self.clf_time_steps:
                if latest_data_diff.empty:
                    latest_data_diff = pd.DataFrame(
                        np.zeros((self.clf_time_steps, len(model_features))),
                        columns=model_features,
                    )
                else:
                    pad_row = latest_data_diff.iloc[[0]].to_numpy()
                    pad_count = self.clf_time_steps - len(latest_data_diff)
                    padding = pd.DataFrame(np.repeat(pad_row, pad_count, axis=0), columns=model_features)
                    latest_data_diff = pd.concat([padding, latest_data_diff.reset_index(drop=True)], ignore_index=True)

            X_input_scaled = self.trend_scaler.transform(latest_data_diff)
            X_input = X_input_scaled.reshape(1, self.clf_time_steps, len(model_features))
            pred_prob = self.trend_model.predict(X_input, verbose=0)
            prob = np.ravel(pred_prob)

            if len(prob) == 1:
                up_prob = float(prob[0]) * 100.0
                down_prob = 100.0 - up_prob
            else:
                down_prob = float(prob[0]) * 100.0
                up_prob = float(prob[1]) * 100.0

            trend_result = "Tăng" if up_prob > 50 else "Giảm"
            confidence = max(up_prob, down_prob)

            return {
                "predicted_trend": trend_result,
                "confidence_percent": round(float(confidence), 2),
                "up_probability": round(float(up_prob), 2),
                "down_probability": round(float(down_prob), 2),
            }

        return {
            "predicted_trend": "Giảm",
            "confidence_percent": 0.0,
            "up_probability": 0.0,
            "down_probability": 100.0,
        }


# Global engine instance for backward compatibility
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = GoldPredictionEngine()
    return _engine


def forecast_price_path(history_prices, days, strategy="default"):

    if not history_prices:
        return []
    
    import pandas as pd
    df = pd.DataFrame({"price": history_prices})
    df["date"] = pd.date_range(end=pd.Timestamp.now(), periods=len(history_prices), freq="D")
    
    engine = _get_engine()
    result = engine.predict_future(df, history_prices[-1], days)
    return result["predictions"]


def classify_price_path(last_price, predicted_prices):
    return summarize_price_path(last_price, predicted_prices)


PRICE_ARTIFACT_MODEL_CODES = {"lstm-k10-price-v1", "meta-lstm-k10-price-v1"}
GRU_ARTIFACT_MODEL_CODES = {"gru-price-v1"}
TREND_ARTIFACT_MODEL_CODES = {"sjc-classification-v1"}


def _prepare_feature_window(self, df_diff, feature_columns, window_size):
    working = df_diff.copy()
    for column in feature_columns:
        if column not in working.columns:
            working[column] = 0.0

    selected = working[feature_columns].copy()
    selected = selected.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if selected.empty:
        selected = pd.DataFrame(np.zeros((1, len(feature_columns))), columns=feature_columns)

    window = selected.tail(window_size).reset_index(drop=True)
    if len(window) < window_size:
        pad_row = window.iloc[[0]].to_numpy()
        pad_count = window_size - len(window)
        padding = pd.DataFrame(np.repeat(pad_row, pad_count, axis=0), columns=feature_columns)
        window = pd.concat([padding, window], ignore_index=True)

    return window


def _predict_future(self, df_diff, last_actual_sjc_price, days: int):
    latest_data_diff = self._prepare_feature_window(df_diff, self.feature_cols, self.best_k)
    current_window_diff = self.scaler_X.transform(latest_data_diff)

    predictions = []
    current_absolute_price = float(last_actual_sjc_price)
    is_dl_model = not hasattr(self.ml_model, "coef_") and not hasattr(self.ml_model, "support_")
    target_idx = self.feature_cols.index("SJC") if "SJC" in self.feature_cols else None

    for _ in range(days):
        if not is_dl_model:
            X_input = current_window_diff.reshape(1, -1)
            pred_delta_scaled = self.ml_model.predict(X_input)
        else:
            X_input = current_window_diff.reshape(1, self.best_k, len(self.feature_cols))
            pred_delta_scaled = self.ml_model.predict(X_input, verbose=0)

        pred_delta_scaled = np.asarray(pred_delta_scaled).reshape(-1, 1)
        pred_delta_real = float(self.scaler_y.inverse_transform(pred_delta_scaled)[0][0])
        next_absolute_price = current_absolute_price + pred_delta_real
        predictions.append(float(next_absolute_price))
        current_absolute_price = next_absolute_price

        new_feature_row = current_window_diff[-1].copy()
        if target_idx is not None:
            new_feature_row[target_idx] = float(pred_delta_scaled.ravel()[0])
        current_window_diff = np.vstack([current_window_diff[1:], new_feature_row])

    trend = _overall_trend(float(last_actual_sjc_price), predictions)
    return {"predictions": predictions, "base_price": float(last_actual_sjc_price), "trend": trend}


def _predict_future_gru(self, last_actual_sjc_price, days: int, range_value: str | None = None):
    if getattr(self, "gru_model", None) is None:
        df_diff, _, _ = load_feature_prediction_data(required_columns=set(self.feature_cols) | {"SJC"}, range_value=range_value)
        return self.predict_future(df_diff, last_actual_sjc_price, days)

    feature_frame = load_feature_dataset_frame(range_value=range_value)
    feature_columns = list(
        getattr(self, "gru_feature_cols", None)
        or [column for column in feature_frame.columns if column not in {"date", "SJC", "SJC_Premium_Zscore", "Policy_Risk_Zone"}]
    )
    if not feature_columns:
        return {"predictions": [], "trend": "flat"}

    working = feature_frame.sort_values("date").reset_index(drop=True)
    current_row = working[feature_columns].tail(1).iloc[0].copy()
    price_history = working["SJC"].astype(float).tolist() if "SJC" in working.columns else [float(last_actual_sjc_price)]
    premium_history = working["SJC_Premium"].astype(float).tolist() if "SJC_Premium" in working.columns else []
    current_price = float(last_actual_sjc_price)
    world_price = float(current_row.get("Gold_world_vnd", current_price)) or float(current_price)
    policy_risk_zone = float(current_row.get("Policy_Risk_Zone", 0.0))
    predictions = []

    for _ in range(days):
        current_row["SJC_lag1"] = price_history[-1]
        current_row["SJC_lag7"] = price_history[-7] if len(price_history) >= 7 else price_history[-1]
        current_row["SJC_ma7"] = float(np.mean(price_history[-7:])) if len(price_history) >= 7 else price_history[-1]

        premium = current_price - world_price
        current_row["SJC_Premium"] = premium
        current_row["SJC_Premium_Percent"] = (premium / world_price * 100.0) if world_price else 0.0
        premium_history.append(premium)
        trailing_premium = np.asarray(premium_history[-30:], dtype=float)
        if trailing_premium.size >= 2:
            premium_std = float(np.std(trailing_premium))
            current_row["SJC_Premium_Zscore"] = float((premium - float(np.mean(trailing_premium))) / premium_std) if premium_std else 0.0
        else:
            current_row["SJC_Premium_Zscore"] = 0.0
        current_row["Policy_Risk_Zone"] = policy_risk_zone

        input_values = pd.to_numeric(current_row[feature_columns], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy(dtype=float).reshape(1, 1, len(feature_columns))
        predicted_delta = float(np.ravel(self.gru_model.predict(input_values, verbose=0))[0])
        next_price = current_price + predicted_delta
        predictions.append(float(next_price))

        current_price = next_price
        price_history.append(next_price)

    trend = _overall_trend(float(last_actual_sjc_price), predictions)
    return {"predictions": predictions, "base_price": float(last_actual_sjc_price), "trend": trend}


def _predict_trend_classification(self, df_diff):
    model_features = list(getattr(self, "clf_features", []))
    if not model_features:
        return {
            "predicted_trend": "Giảm",
            "confidence_percent": 0.0,
            "up_probability": 0.0,
            "down_probability": 100.0,
        }

    if getattr(self, "trend_model_kind", "builtin") == "xgb" and getattr(self, "trend_model", None) is not None:
        working = df_diff.copy()
        for column in model_features:
            if column not in working.columns:
                working[column] = 0.0

        latest_row = (
            working[model_features]
            .tail(1)
            .apply(pd.to_numeric, errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0.0)
        )

        trend_scaler = getattr(self, "trend_scaler", None) or _build_runtime_scaler(working, model_features)
        X_input_scaled = trend_scaler.transform(latest_row)
        if hasattr(self.trend_model, "predict_proba"):
            pred_prob = self.trend_model.predict_proba(X_input_scaled)
        else:
            pred_prob = self.trend_model.predict(X_input_scaled)

        prob = np.ravel(pred_prob)
        if len(prob) == 1:
            up_prob = float(prob[0]) * 100.0
            down_prob = 100.0 - up_prob
        else:
            down_prob = float(prob[0]) * 100.0
            up_prob = float(prob[1]) * 100.0

        trend_result = "Tăng" if up_prob > 50 else "Giảm"
        confidence = max(up_prob, down_prob)

        return {
            "predicted_trend": trend_result,
            "confidence_percent": round(float(confidence), 2),
            "up_probability": round(float(up_prob), 2),
            "down_probability": round(float(down_prob), 2),
        }

    latest_data_diff = self._prepare_feature_window(df_diff, model_features, self.clf_time_steps)

    scaler_frame = df_diff.copy()
    for column in model_features:
        if column not in scaler_frame.columns:
            scaler_frame[column] = 0.0

    scaler_frame = scaler_frame[model_features].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    trend_scaler = MinMaxScaler()
    trend_scaler.fit(scaler_frame)
    X_input_scaled = trend_scaler.transform(latest_data_diff)

    X_input = X_input_scaled.reshape(1, self.clf_time_steps, len(model_features))

    pred_prob = self.trend_model.predict(X_input, verbose=0)
    prob = np.ravel(pred_prob)

    if len(prob) == 1:
        up_prob = float(prob[0]) * 100.0
        down_prob = 100.0 - up_prob
    else:
        down_prob = float(prob[0]) * 100.0
        up_prob = float(prob[1]) * 100.0

    trend_result = "Tăng" if up_prob > 50 else "Giảm"
    confidence = max(up_prob, down_prob)

    return {
        "predicted_trend": trend_result,
        "confidence_percent": round(float(confidence), 2),
        "up_probability": round(float(up_prob), 2),
        "down_probability": round(float(down_prob), 2),
    }


GoldPredictionEngine._prepare_feature_window = _prepare_feature_window
GoldPredictionEngine.predict_future = _predict_future
GoldPredictionEngine.predict_future_gru = _predict_future_gru
GoldPredictionEngine.predict_trend_classification = _predict_trend_classification


def _coerce_history_prices(history_prices):
    prices = []
    for value in history_prices or []:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(numeric):
            prices.append(numeric)
    return prices


def _sanitize_price(value, fallback):
    if not np.isfinite(value):
        return float(fallback)
    return max(0.0, float(value))


def _trend_label(delta, reference):
    tolerance = max(0.01, abs(reference) * 0.0005)
    if abs(delta) <= tolerance:
        return "flat"
    return "up" if delta > 0 else "down"


def _trend_score(delta, reference, label):
    if label == "flat":
        return 0.5
    magnitude = abs(delta) / max(abs(reference), 1.0)
    return round(min(0.99, 0.5 + magnitude * 15.0), 4)


def _overall_trend(last_price, predicted_prices):
    if not predicted_prices:
        return "flat"
    return _trend_label(float(predicted_prices[0]) - float(last_price), float(last_price))


def _forecast_builtin_price_path(history_prices, days, strategy="default"):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return []

    if len(history) == 1:
        return [float(history[-1])] * days

    window = np.asarray(history[-min(len(history), 30):], dtype=float)
    deltas = np.diff(window)
    normalized_strategy = (strategy or "linear").strip().lower()
    predictions = []

    if normalized_strategy == "momentum":
        momentum = float(np.mean(deltas[-min(len(deltas), 7):])) if len(deltas) else 0.0
        current = float(window[-1])
        for _ in range(days):
            current = _sanitize_price(current + momentum, current)
            predictions.append(current)
            momentum *= 0.96
        return predictions

    if normalized_strategy == "mean_reversion":
        anchor = float(np.mean(window))
        drift = float(np.mean(deltas[-min(len(deltas), 5):])) if len(deltas) else 0.0
        current = float(window[-1])
        for _ in range(days):
            pull = (anchor - current) * 0.2
            current = _sanitize_price(current + drift * 0.35 + pull, current)
            predictions.append(current)
            drift *= 0.9
        return predictions

    x_values = np.arange(len(window), dtype=float)
    slope, intercept = np.polyfit(x_values, window, 1)
    future_x = np.arange(len(window), len(window) + days, dtype=float)
    return [_sanitize_price(float(intercept + slope * index), window[-1]) for index in future_x]


def summarize_price_path(last_price, predicted_prices):
    predictions = _coerce_history_prices(predicted_prices)
    if not predictions:
        return [], [], "flat"

    trend_predictions = []
    trend_scores = []
    previous_price = float(last_price)

    for price in predictions:
        delta = float(price) - previous_price
        label = _trend_label(delta, previous_price)
        trend_predictions.append(label)
        trend_scores.append(_trend_score(delta, previous_price, label))
        previous_price = float(price)

    return trend_predictions, trend_scores, _overall_trend(float(last_price), predictions)


def _normalize_artifact_trend_label(label):
    normalized = str(label or "").strip().lower()
    if "tang" in normalized or "tăng" in normalized or "up" in normalized:
        return "up"
    if "giam" in normalized or "giảm" in normalized or "down" in normalized:
        return "down"
    return "flat"


def _forecast_trend_bias_path(history_prices, days, direction, confidence_percent):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return []

    recent_window = np.asarray(history[-min(len(history), 30):], dtype=float)
    last_price = float(recent_window[-1])
    anchor_price = float(np.mean(recent_window)) if recent_window.size else last_price
    if recent_window.size > 1:
        recent_change = float(np.mean(np.diff(recent_window)))
    else:
        recent_change = 0.0

    if not np.isfinite(recent_change) or abs(recent_change) < 1e-6:
        recent_change = max(abs(last_price) * 0.002, 0.1)

    confidence_ratio = max(0.05, min(0.95, float(confidence_percent) / 100.0))
    base_step = max(abs(recent_change), max(abs(last_price) * 0.0015, 0.1))
    drift = base_step * (0.65 + confidence_ratio)
    oscillation = drift * (1.65 - confidence_ratio)

    current_price = last_price
    predicted_prices: list[float] = []
    for index in range(days):
        decay = 0.94 ** index
        swing = np.sin(index + 1.0) * oscillation * (1.0 - confidence_ratio)
        pull = (anchor_price - current_price) * 0.75
        step = direction * drift * decay + swing + pull

        current_price = max(0.01, current_price + step)
        predicted_prices.append(float(current_price))

    return predicted_prices


def forecast_price_path(history_prices, days, strategy="default", provider="builtin", model_code=None, source="sjc", range_value: str | None = None):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return [], False

    if provider == "artifact" and source == "sjc" and model_code in GRU_ARTIFACT_MODEL_CODES:
        engine = _get_engine()
        result = engine.predict_future_gru(history[-1], days, range_value=range_value)
        return result["predictions"], False

    if provider == "artifact" and source == "sjc" and model_code in PRICE_ARTIFACT_MODEL_CODES:
        engine = _get_engine()
        df_diff, last_actual_price, _ = load_feature_prediction_data(
            required_columns=set(engine.feature_cols) | {"SJC"},
            range_value=range_value,
        )
        result = engine.predict_future(df_diff, last_actual_price, days)
        return result["predictions"], False

    predictions = _forecast_builtin_price_path(history, days, strategy=strategy)
    used_fallback = provider == "artifact"
    return predictions, used_fallback


def predict_trend_path(history_prices, days, strategy="default", provider="builtin", model_code=None, source="sjc", range_value: str | None = None):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return [], [], False

    if provider == "artifact" and source == "sjc" and model_code in TREND_ARTIFACT_MODEL_CODES:
        engine = _get_engine()
        if getattr(engine, "trend_model", None) is None:
            reference_strategy = "momentum" if (strategy or "").strip().lower() in {"", "default", "slope"} else strategy
            predicted_prices = _forecast_builtin_price_path(history, days, strategy=reference_strategy)
            trend_predictions, trend_scores, _ = summarize_price_path(history[-1], predicted_prices)
            return trend_predictions, trend_scores, True

        df_diff, _, _ = load_feature_prediction_data(
            required_columns=set(engine.clf_features) | {"SJC"},
            range_value=range_value,
        )
        result = engine.predict_trend_classification(df_diff)
        label = _normalize_artifact_trend_label(result.get("predicted_trend"))
        if label == "flat":
            reference_strategy = "momentum" if (strategy or "").strip().lower() in {"", "default", "slope"} else strategy
            predicted_prices = _forecast_builtin_price_path(history, days, strategy=reference_strategy)
            trend_predictions, trend_scores, _ = summarize_price_path(history[-1], predicted_prices)
            return trend_predictions, trend_scores, False

        direction = 1 if label == "up" else -1
        confidence_percent = float(result.get("confidence_percent", 50.0))
        predicted_prices = _forecast_trend_bias_path(history, days, direction, confidence_percent)
        trend_predictions, trend_scores, _ = summarize_price_path(history[-1], predicted_prices)
        return trend_predictions, trend_scores, False

    reference_strategy = "momentum" if (strategy or "").strip().lower() in {"", "default", "slope"} else strategy
    predicted_prices = _forecast_builtin_price_path(history, days, strategy=reference_strategy)
    trend_predictions, trend_scores, _ = summarize_price_path(history[-1], predicted_prices)
    used_fallback = provider == "artifact"
    return trend_predictions, trend_scores, used_fallback


def classify_price_path(last_price, predicted_prices):
    return summarize_price_path(last_price, predicted_prices)
