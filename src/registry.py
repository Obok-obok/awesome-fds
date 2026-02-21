import os, json, shutil
from joblib import load
from src.io_utils import ensure_dirs

CHAMPION = "models/champion.joblib"
CHALLENGER = "models/challenger.joblib"
META_CHAMP = "models/meta_champion.json"
META_CHALL = "models/meta_challenger.json"

def init_champion_if_missing():
    ensure_dirs("models")
    if not os.path.exists(CHAMPION):
        # bootstrap from fraud_lr if exists
        src = "models/fraud_lr.joblib"
        meta = "models/meta.json"
        if os.path.exists(src):
            shutil.copy(src, CHAMPION)
            if os.path.exists(meta):
                shutil.copy(meta, META_CHAMP)
        else:
            raise RuntimeError("No base model to init champion")
    print("✅ champion ready")

def set_challenger(model_path: str, meta_path: str):
    shutil.copy(model_path, CHALLENGER)
    shutil.copy(meta_path, META_CHALL)

def promote():
    shutil.copy(CHALLENGER, CHAMPION)
    shutil.copy(META_CHALL, META_CHAMP)

