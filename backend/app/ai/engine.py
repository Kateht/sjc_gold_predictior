from app.ai.utils import load_feature_prediction_data
from app.core.config import settings
import tensorflow as tf
import keras
import numpy as np
import pandas as pd
import joblib
import json
# --- Patch để xử lý version mismatch khi load model .h5 ---
_original_dense_init = keras.layers.Dense.__init__

def _patched_dense_init(self, *args, **kwargs):
    kwargs.pop('quantization_config', None)
    _original_dense_init(self, *args, **kwargs)

keras.layers.Dense.__init__ = _patched_dense_init
# --- End patch ---

class GoldPredictionEngine:
    def __init__(self):
        # Load models & scalers từ weights/ LSTM
        self.scaler_X = joblib.load(f"{settings.MODEL_DIR}/scaler_X_lstm_k10.pkl")
        self.scaler_y = joblib.load(f"{settings.MODEL_DIR}/scaler_y_lstm_k10.pkl")
        self.meta = joblib.load(f"{settings.MODEL_DIR}/meta_lstm_k10.pkl")
        self.ml_model = keras.models.load_model(f"{settings.MODEL_DIR}/lstm_k10.keras")
        
        self.best_k = self.meta["best_k"]
        self.feature_cols = self.meta["feature_columns"]
        # 2. LOAD MODEL PHÂN LOẠI (DỰ ĐOÁN XU HƯỚNG)
        # ======================================
        self.scaler_X_clf = joblib.load(f"{settings.MODEL_DIR}/scaler_X_classification.pkl")

        # Load meta riêng cho classification
        self.meta_clf = joblib.load(f"{settings.MODEL_DIR}/meta_sjc_classification.pkl")
        scaler_feature_names = getattr(self.scaler_X_clf, "feature_names_in_", None)
        self.clf_features = list(scaler_feature_names) if scaler_feature_names is not None else self.meta_clf["features"]
        self.clf_time_steps = self.meta_clf["time_steps"] # Giá trị 15
        self.dl_model_clf = tf.keras.models.load_model(
            f"{settings.MODEL_DIR}/sjc_classification.h5", 
            compile=False
        )
        try:
            self.xgb_model = joblib.load(f"{settings.MODEL_DIR}/best_xgb_model.pkl")
            with open(f"{settings.MODEL_DIR}/best_xgb_enhanced_params.json", 'r', encoding='utf-8') as f:
                self.xgb_meta = json.load(f)
            
            # Đọc features và k riêng của XGBoost từ file JSON
            # (Nếu JSON không có thì fallback về dùng chung với LSTM)
            self.xgb_features = self.xgb_meta.get("feature_columns", self.feature_cols)
            self.xgb_k = self.xgb_meta.get("best_k", self.best_k)
            print("Loaded XGBoost model successfully.")
        except Exception as e:
            print(f"Warning: could not load XGBoost model: {e}")
            self.xgb_model = None

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
            
            # SỬA Ở ĐÂY: Thêm câu lệnh if kiểm tra SJC
            if "SJC" in self.feature_cols:
                target_idx = self.feature_cols.index("SJC")
                new_delta_row[target_idx] = np.ravel(pred_delta_scaled)[0]
                
            current_window_diff = np.vstack([current_window_diff[1:], new_delta_row])

        trend = "tăng 📈" if predictions[-1] > predictions[0] else "giảm 📉"
        return {"predictions": predictions, "trend": trend}
    

    def predict_trend_classification(self, df_diff):
        print("Predict classi")

        # Bảo hiểm: Nếu pipeline data ở ngoài lỡ quên cột nào thì điền 0
        for col in self.clf_features: # clf_features lúc này sẽ đọc ra 22 cột
            if col not in df_diff.columns:
                print(f"Warning: missing column '{col}'. Filling with 0.")
                df_diff[col] = 0.0

        # Lấy 21 ngày gần nhất (clf_time_steps = 21) của 22 cột
        latest_data_diff = df_diff[self.clf_features].tail(self.clf_time_steps)
        
        # Scale và dự đoán...
        X_input_scaled = self.scaler_X_clf.transform(latest_data_diff)
        X_input = X_input_scaled.reshape(1, self.clf_time_steps, len(self.clf_features))
        
        pred_prob = self.dl_model_clf.predict(X_input, verbose=0)
            
        # Xử lý output (Giả sử model của bạn xuất ra [Xác_suất_Giảm, Xác_suất_Tăng])
        # Nếu model dùng hàm kích hoạt Sigmoid (1 node) thì pred_prob có dạng [[0.8]]
        # Nếu dùng Softmax (2 nodes) thì có dạng [[0.2, 0.8]]
        
        prob = np.ravel(pred_prob)
        
        # Logic phân loại (tùy thuộc vào cấu trúc layer cuối của bạn)
        # Ở đây tôi ví dụ cấu trúc phổ biến nhất: 
        # Binary Classification (0: Giảm, 1: Tăng) hoặc Softmax index 1 là Tăng.
        if len(prob) == 1:
            # Dành cho Sigmoid
            up_prob = prob[0] * 100
            down_prob = 100 - up_prob
        else:
            # Dành cho Softmax
            down_prob = prob[0] * 100
            up_prob = prob[1] * 100

        trend_result = "Tăng" if up_prob > 50 else "Giảm"
        confidence = max(up_prob, down_prob)

        return {
            "predicted_trend": trend_result,
            "confidence_percent": round(float(confidence), 2),
            "up_probability": round(float(up_prob), 2),
            "down_probability": round(float(down_prob), 2)
        }


    # XGBoost predict 
    def predict_future_xgb(self, df_raw, days: int):
        print("Predict reg using XGBoost (34 Features Model)")
        if self.xgb_model is None:
            return {"error": "XGBoost model is missing."}

        import pandas as pd
        import numpy as np
        from sklearn.preprocessing import MinMaxScaler
        
        xgb_features = ['Interest', 'CPI', 'Real_Yield_10Y', 'Gold_Close', 'Gold_High', 'Gold_Low', 'Gold_Volume', 'USD_index_Close', 'Oil_Close', 'USD_VND_Close', 'GVZ_Close', 'VIX_Close', 'ETF_Holdings_Close', 'MOVE_Index_Close', 'Gold_world_vnd', 'SJC_Premium', 'SJC_Premium_Percent', 'Shock_Index', 'SJC_lag1', 'SJC_lag7', 'SJC_ma7', 'Gold_return', 'Gold_volume_rank', 'Gold_range', 'Gold_volatility_7', 'Gold_momentum', 'Gold_Volume_Anomaly', 'PVT', 'year', 'month', 'day', 'dayofweek', 'weekofyear', 'quarter']
        
        df_temp = df_raw.copy()
        
        # ==========================================
        # 🧹 BƯỚC SỬA LỖI: LÀM SẠCH DỮ LIỆU RÁC (INF/NAN)
        # ==========================================
        df_temp.replace([np.inf, -np.inf], np.nan, inplace=True)
        df_temp.ffill(inplace=True) # Lấp lỗ hổng bằng dữ liệu ngày hôm trước
        df_temp.bfill(inplace=True) # Lấp lỗ hổng bằng dữ liệu ngày hôm sau
        df_temp.fillna(0, inplace=True) # Đảm bảo an toàn 100% không còn NaN
        
        # Tạo 6 cột thời gian
        df_temp["year"] = df_temp.index.year
        df_temp["month"] = df_temp.index.month
        df_temp["day"] = df_temp.index.day
        df_temp["dayofweek"] = df_temp.index.dayofweek
        df_temp["weekofyear"] = df_temp.index.isocalendar().week.astype(int)
        df_temp["quarter"] = df_temp.index.quarter
        
        scaler_ml_X = MinMaxScaler()
        scaler_ml_X.fit(df_temp[xgb_features])
        
        last_date = df_temp.index[-1]
        current_row = df_temp.iloc[-1][xgb_features].copy()
        
        # Lấy lịch sử SJC từ mảng ĐÃ LÀM SẠCH
        sjc_history = df_temp['SJC'].tolist() 
        predictions = []
        
        for i in range(1, days + 1):
            next_date = last_date + pd.Timedelta(days=i)
            current_row['year'] = next_date.year
            current_row['month'] = next_date.month
            current_row['day'] = next_date.day
            current_row['dayofweek'] = next_date.dayofweek
            current_row['weekofyear'] = next_date.isocalendar().week
            current_row['quarter'] = next_date.quarter
            
            current_row['SJC_lag1'] = sjc_history[-1]
            current_row['SJC_lag7'] = sjc_history[-7] if len(sjc_history) >= 7 else sjc_history[-1]
            current_row['SJC_ma7'] = np.mean(sjc_history[-7:]) if len(sjc_history) >= 7 else sjc_history[-1]
            
            X_input = pd.DataFrame([current_row], columns=xgb_features)
            X_input_scaled = scaler_ml_X.transform(X_input)
            
            next_price = float(self.xgb_model.predict(X_input_scaled)[0])
            predictions.append(next_price)
            
            sjc_history.append(next_price)
            
        trend = "tăng 📈" if predictions[-1] > predictions[0] else "giảm 📉"
        return {
            "predictions": predictions, 
            "trend": trend,
            "model_used": "XGBoost 🚀"
        }


# Global engine instance for backward compatibility
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = GoldPredictionEngine()
    return _engine


def forecast_price_path(history_prices, days, strategy="default"):
    """Forecast price path using the prediction engine."""
    # Convert history_prices to the format expected by the engine
    # Assuming history_prices is a list of prices
    if not history_prices:
        return []
    
    # Create a simple dataframe from history prices
    import pandas as pd
    df = pd.DataFrame({"price": history_prices})
    df["date"] = pd.date_range(end=pd.Timestamp.now(), periods=len(history_prices), freq="D")
    
    # Use the engine to predict
    engine = _get_engine()
    result = engine.predict_future(df, history_prices[-1], days)
    return result["predictions"]


def classify_price_path(last_price, predicted_prices):
    """Classify price trend using the prediction engine."""
    # Create a simple dataframe for trend classification
    import pandas as pd
    # Need some historical data for classification
    # For now, create dummy data - this might need adjustment based on actual requirements
    dummy_history = [last_price] * 15  # Assume we need at least 15 data points
    df = pd.DataFrame({"price": dummy_history})
    df["date"] = pd.date_range(end=pd.Timestamp.now(), periods=len(dummy_history), freq="D")
    
    engine = _get_engine()
    result = engine.predict_trend_classification(df)
    
    # Return format expected by prediction_service: (trend_predictions, trend_scores, trend)
    trend = result["predicted_trend"]
    confidence = result["confidence_percent"]
    
    # Create dummy trend predictions and scores based on the result
    trend_predictions = [trend] * len(predicted_prices) if predicted_prices else [trend]
    trend_scores = [confidence] * len(trend_predictions)
    
    return trend_predictions, trend_scores, trend


PRICE_ARTIFACT_MODEL_CODES = {"lstm-k10-price-v1", "meta-lstm-k10-price-v1"}
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
    return {"predictions": predictions, "trend": trend}


def _predict_trend_classification(self, df_diff):
    latest_data_diff = self._prepare_feature_window(df_diff, self.clf_features, self.clf_time_steps)
    X_input_scaled = self.scaler_X_clf.transform(latest_data_diff)
    X_input = X_input_scaled.reshape(1, self.clf_time_steps, len(self.clf_features))

    pred_prob = self.dl_model_clf.predict(X_input, verbose=0)
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
    return _trend_label(float(predicted_prices[-1]) - float(last_price), float(last_price))


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


def forecast_price_path(history_prices, days, strategy="default", provider="builtin", model_code=None, source="sjc"):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return [], False

    if provider == "artifact" and source == "sjc" and model_code in PRICE_ARTIFACT_MODEL_CODES:
        engine = _get_engine()
        df_diff, last_actual_price, _ = load_feature_prediction_data(required_columns=set(engine.feature_cols) | {"SJC"})
        result = engine.predict_future(df_diff, last_actual_price, days)
        return result["predictions"], False

    predictions = _forecast_builtin_price_path(history, days, strategy=strategy)
    used_fallback = provider == "artifact"
    return predictions, used_fallback


def predict_trend_path(history_prices, days, strategy="default", provider="builtin", model_code=None, source="sjc"):
    history = _coerce_history_prices(history_prices)
    if not history or days <= 0:
        return [], [], False

    if provider == "artifact" and source == "sjc" and model_code in TREND_ARTIFACT_MODEL_CODES:
        engine = _get_engine()
        df_diff, _, _ = load_feature_prediction_data(required_columns=set(engine.clf_features) | {"SJC"})
        result = engine.predict_trend_classification(df_diff)
        label = _normalize_artifact_trend_label(result.get("predicted_trend"))
        score = round(float(result.get("confidence_percent", 50.0)) / 100.0, 4)
        return [label] * days, [score] * days, False

    reference_strategy = "momentum" if (strategy or "").strip().lower() in {"", "default", "slope"} else strategy
    predicted_prices = _forecast_builtin_price_path(history, days, strategy=reference_strategy)
    trend_predictions, trend_scores, _ = summarize_price_path(history[-1], predicted_prices)
    used_fallback = provider == "artifact"
    return trend_predictions, trend_scores, used_fallback


def classify_price_path(last_price, predicted_prices):
    return summarize_price_path(last_price, predicted_prices)
