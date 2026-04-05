import pandas as pd

# 1. Đọc file CSV y hệt như trên Colab
df = pd.read_csv('dataset/final_dataset_new.csv', index_col=0, parse_dates=True)

# 2. Tạo 6 biến thời gian giống hệt Colab
df["year"] = df.index.year
df["month"] = df.index.month
df["day"] = df.index.day
df["dayofweek"] = df.index.dayofweek
df["weekofyear"] = df.index.isocalendar().week.astype(int)
df["quarter"] = df.index.quarter

# 3. Loại bỏ cột mục tiêu SJC
X = df.drop(columns=["SJC"])

# 4. In ra danh sách 34 biến
danh_sach_34_bien = X.columns.tolist()
print("\n=== ĐÂY LÀ 34 BIẾN CỦA BẠN ===")
print(danh_sach_34_bien)