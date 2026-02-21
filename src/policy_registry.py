import json, os
from datetime import datetime

PATH = "models/policy_registry.json"

def ensure_policy_registry(default_control_rate: float = 0.10):
    os.makedirs("models", exist_ok=True)
    if not os.path.exists(PATH):
        reg = {
            "current": {"policy_version":"P0","control_rate":float(default_control_rate),"mode":"EXPERIMENT","created_at":"INIT","notes":"auto-created"},
            "history": []
        }
        json.dump(reg, open(PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def load_policy():
    ensure_policy_registry()
    return json.load(open(PATH,"r",encoding="utf-8"))

def update_policy(control_rate: float, mode: str, notes: str):
    reg = load_policy()
    reg["history"].append(reg["current"])
    reg["current"] = {
        "policy_version": f"P{len(reg['history'])}",
        "control_rate": float(control_rate),
        "mode": mode,
        "created_at": datetime.utcnow().isoformat()+"Z",
        "notes": notes
    }
    json.dump(reg, open(PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    return reg["current"]
