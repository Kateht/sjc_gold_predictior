import joblib
import numpy as np
from app.core.config import settings

class GoldPredictionEngine:
    def __init__(self):
        # Load models & scalers từ weights/
        self.scaler_X = joblib.load(f"{settings.MODEL_DIR}/scaler_X.pkl")
        self.scaler_y = joblib.load(f"{settings.MODEL_DIR}/scaler_y.pkl")
        self.meta = joblib.load(f"{settings.MODEL_DIR}/meta.pkl")
        self.ml_model = joblib.load(f"{settings.MODEL_DIR}/best_gold_model_k3.pkl")
        
        self.best_k = self.meta["best_k"]
        self.feature_cols = self.meta["feature_columns"]

    def predict_future(self, df_diff, last_actual_sjc_price, days: int):
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

            new_delta_row = np.zeros(len(self.feature_cols))
            target_idx = self.feature_cols.index("SJC")
            new_delta_row[target_idx] = np.ravel(pred_delta_scaled)[0]
            current_window_diff = np.vstack([current_window_diff[1:], new_delta_row])

        trend = "tăng 📈" if predictions[-1] > predictions[0] else "giảm 📉"
        return {"predictions": predictions, "trend": trend}