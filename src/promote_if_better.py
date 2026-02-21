import os
import pandas as pd
from src.io_utils import read_csv
from src.registry import promote

def main():
    df = read_csv("out/cc_metrics.csv")
    if df.empty or df["model"].nunique() < 2:
        print("🟨 promote: no challenger metrics")
        return
    champ = df[df["model"]=="champion"].iloc[0]
    chall = df[df["model"]=="challenger"].iloc[0]
    # standard: prioritize avg_precision, then roc_auc
    if float(chall["avg_precision"]) >= float(champ["avg_precision"]):
        promote()
        print("✅ promoted challenger -> champion")
    else:
        print("🟨 not promoted")

if __name__ == "__main__":
    main()
