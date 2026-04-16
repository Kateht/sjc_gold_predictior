import pandas as pd

df = pd.read_csv('dataset/final_dataset.csv', index_col=0, parse_dates=True)

# 2. Tạo 6 biến thời gian giống hệt Colab
df["year"] = df.index.year
df["month"] = df.index.month
df["day"] = df.index.day
df["dayofweek"] = df.index.dayofweek
df["weekofyear"] = df.index.isocalendar().week.astype(int)
df["quarter"] = df.index.quarter

X = df.drop(columns=["SJC"])

danh_sach_34_bien = X.columns.tolist()
print("\n=== ĐÂY LÀ 34 BIẾN ===")
print(danh_sach_34_bien)