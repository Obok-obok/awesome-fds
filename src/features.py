import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

def build_preprocessor(df: pd.DataFrame, id_col: str, paid_col: str, label_col: str):
    drop_cols = {id_col, paid_col}
    if label_col in df.columns:
        drop_cols.add(label_col)

    feat_cols = [c for c in df.columns if c not in drop_cols]
    X = df[feat_cols].copy() if feat_cols else pd.DataFrame(index=df.index)

    num_cols = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat_cols = [c for c in X.columns if c not in num_cols]

    num_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])
    cat_pipe = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("ohe", OneHotEncoder(handle_unknown="ignore")),
    ])

    pre = ColumnTransformer([
        ("num", num_pipe, num_cols),
        ("cat", cat_pipe, cat_cols),
    ], remainder="drop")

    return pre, feat_cols, num_cols, cat_cols
