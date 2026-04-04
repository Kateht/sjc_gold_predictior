from app.core.config import settings
import tensorflow as tf
import keras
import numpy as np
import pandas as pd
import joblib

# --- Patch để xử lý version mismatch khi load model .h5 ---
_original_dense_init = keras.layers.Dense.__init__

def _patched_dense_init(self, *args, **kwargs):
    kwargs.pop('quantization_config', None)
    _original_dense_init(self, *args, **kwargs)

keras.layers.Dense.__init__ = _patched_dense_init
# --- End patch ---

class GoldPredictionEngine:
    def __init__(self):
        # Load models & scalers từ weights/
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
        self.clf_features = self.meta_clf["features"] 
        self.clf_time_steps = self.meta_clf["time_steps"] # Giá trị 15
        self.dl_model_clf = tf.keras.models.load_model(
            f"{settings.MODEL_DIR}/sjc_classification.h5", 
            compile=False
        )

    def predict_future(self, df_diff, last_actual_sjc_price, days: int):
        print("Predict reg")
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
                print(f"⚠️ Warning: Thiếu cột '{col}'. Tự động điền 0.")
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