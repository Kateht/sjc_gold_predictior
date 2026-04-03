import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_PATH = BASE_DIR / "dataset" / "final_dataset_new.csv"

# Hằng số quy đổi: 1 Ounce = 0.82945 Lượng
OZ_TO_TAEL = 0.82945

def get_exchange_rate():
    """Lấy tỷ giá USD/VND tự động từ yfinance, có fallback."""
    try:
        forex = yf.Ticker("VND=X")
        # Lấy dữ liệu 1 ngày gần nhất
        hist = forex.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        print(f"⚠️ Lỗi lấy tỷ giá từ yfinance: {e}")
    
    # Fallback tỷ giá mặc định nếu mất kết nối
    return 25000.0

def get_overview_data():
    usd_vnd_rate = get_exchange_rate()
    
    # ==========================================
    # 1. LẤY DỮ LIỆU SJC TRONG NƯỚC (TỪ DATASET)
    # ==========================================
    domestic_data = {}
    try:
        df = pd.read_csv(DATA_PATH)
        df["Date"] = pd.to_datetime(df["Date"])
        df.sort_values("Date", inplace=True)
        
        today_sjc = float(df["SJC"].iloc[-1])
        yesterday_sjc = float(df["SJC"].iloc[-2])
        change_sjc = today_sjc - yesterday_sjc
        change_pct_sjc = (change_sjc / yesterday_sjc) * 100
        trend_sjc = df["SJC"].tail(7).tolist()
        
        domestic_data = {
            "current_price_vnd": round(today_sjc, 2),
            "change_vnd": round(change_sjc, 2),
            "change_percent": round(change_pct_sjc, 2),
            "trend_7d_vnd": [round(x, 2) for x in trend_sjc],
            "unit": "Triệu VND/Lượng",
            "source": "Local Dataset",
            "status": "success"
        }
    except Exception as e:
        domestic_data = {"status": "error", "message": str(e)}
        today_sjc = 0 # Gán tạm để tránh lỗi biến chưa khai báo

    # ==========================================
    # 2. LẤY DỮ LIỆU VÀNG THẾ GIỚI (TỪ YFINANCE)
    # ==========================================
    world_data = {}
    converted_world_sjc = 0
    try:
        gold = yf.Ticker("GC=F")
        # Lấy 10 ngày để đảm bảo lọc ra đủ 7 ngày giao dịch thực tế (bỏ T7, CN)
        hist = gold.history(period="10d") 
        
        if hist.empty:
            raise Exception("No data from yfinance")
            
        today_usd = float(hist["Close"].iloc[-1])
        yesterday_usd = float(hist["Close"].iloc[-2])
        change_usd = today_usd - yesterday_usd
        change_pct_usd = (change_usd / yesterday_usd) * 100
        trend_usd = hist["Close"].tail(7).tolist()
        
        world_data = {
            "current_price_usd": round(today_usd, 2),
            "change_usd": round(change_usd, 2),
            "change_percent": round(change_pct_usd, 2),
            "trend_7d_usd": [round(x, 2) for x in trend_usd],
            "unit": "USD/Ounce",
            "source": "yfinance",
            "status": "success"
        }
        
        # Công thức quy đổi Giá TG ra VNĐ/Lượng để tính chênh lệch
        vnd_per_tael = (today_usd / OZ_TO_TAEL) * usd_vnd_rate
        converted_world_sjc = vnd_per_tael / 1000000  # Đổi ra Triệu VNĐ
        
    except Exception as e:
        world_data = {"status": "error", "message": str(e)}

    # ==========================================
    # 3. TÍNH CHÊNH LỆCH (ARBITRAGE GAP)
    # ==========================================
    arbitrage = {}
    if domestic_data.get("status") == "success" and world_data.get("status") == "success":
        gap = today_sjc - converted_world_sjc
        arbitrage = {
            "gap_vnd": round(gap, 2),
            "exchange_rate": round(usd_vnd_rate, 2),
            "converted_world_price_vnd": round(converted_world_sjc, 2),
            "description": "SJC so với giá thế giới quy đổi (Triệu VNĐ/Lượng)"
        }
    else:
        arbitrage = {"status": "unavailable", "message": "Thiếu dữ liệu để tính chênh lệch"}

    # ==========================================
    # 4. TRẢ VỀ KẾT QUẢ TỔNG HỢP
    # ==========================================
    return {
        "world_gold": world_data,
        "domestic_gold": domestic_data,
        "arbitrage": arbitrage,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }