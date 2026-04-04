import pandas as pd

CSV_PATH = "gia_vang_pnj_sjc.csv"


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    date_col = "Date" if "Date" in df.columns else ("Ngày" if "Ngày" in df.columns else None)
    if date_col is None:
        raise SystemExit(f"No date column found in {CSV_PATH}. Columns={list(df.columns)}")

    df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)

    dates = df[date_col].drop_duplicates().sort_values()
    print("date_col:", date_col)
    print("range:", dates.min().date(), "->", dates.max().date(), "n_dates:", len(dates), "rows:", len(df))

    # Overall gaps
    gaps = dates.diff().dt.days
    gap_idx = gaps[gaps > 1].index
    print("n_gaps:", len(gap_idx))
    if len(gap_idx):
        print("first 20 gaps (prev -> next, days):")
        for i in list(gap_idx)[:20]:
            curr = dates.loc[i]
            prev = dates.shift(1).loc[i]
            print(prev.date(), "->", curr.date(), ":", int(gaps.loc[i]))

    # Focus segment: Sep 2011..Jan 2013
    start = pd.Timestamp("2011-09-01")
    end = pd.Timestamp("2013-01-31")
    seg = dates[(dates >= start) & (dates <= end)]
    all_days = pd.date_range(start, end, freq="D")
    missing = all_days.difference(seg)
    print("segment:", start.date(), "->", end.date(), "present:", len(seg), "missing:", len(missing))
    if len(missing):
        print("first_missing:", [d.strftime("%Y-%m-%d") for d in missing[:30]])
        print("last_missing:", [d.strftime("%Y-%m-%d") for d in missing[-30:]])


if __name__ == "__main__":
    main()
