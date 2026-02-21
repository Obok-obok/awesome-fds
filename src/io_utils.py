import os
import pandas as pd

def ensure_dirs(*dirs: str):
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path)

def write_csv(df: pd.DataFrame, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    df.to_csv(path, index=False)

def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    return open(path, "r", encoding="utf-8").read()

def write_text(text: str, path: str):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
