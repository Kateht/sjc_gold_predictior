import pandas as pd

def load_and_preprocess_data(csv_path: str):
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    
    csv_path = BASE_DIR / "dataset" / "final_dataset.csv"
    
    
    if not csv_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file dataset tại: {csv_path}")

    df_raw = pd.read_csv(csv_path)
    df_raw["Date"] = pd.to_datetime(df_raw["Date"])
    df_raw.set_index("Date", inplace=True)
    df_raw.sort_index(inplace=True)
    
    last_actual_sjc_price = float(df_raw["SJC"].iloc[-1])
    df_diff = df_raw.diff().dropna()
    
    return df_diff, last_actual_sjc_price