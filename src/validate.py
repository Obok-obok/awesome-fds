import pandas as pd
from src.config import CFG
from src.io_utils import read_csv

def main():
    df = read_csv(CFG.data_claims)
    if df.empty:
        raise SystemExit(f"Missing dataset: {CFG.data_claims}")

    required = [CFG.id_col, CFG.paid_col]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing required columns in {CFG.data_claims}: {missing}")

    # paid should be numeric
    df[CFG.paid_col] = pd.to_numeric(df[CFG.paid_col], errors="coerce")
    if df[CFG.paid_col].isna().mean() > 0.2:
        raise SystemExit("Too many non-numeric paid_amount values")

    print("✅ validate OK:", df.shape)

if __name__ == "__main__":
    main()
