import pandas as pd
from src.policy_registry import load_policy, update_policy

STAGES = [0.10, 0.05, 0.02, 0.00]
ROLLBACK_TO = 0.10

def next_stage(cur_rate: float):
    for r in STAGES:
        if r < cur_rate:
            return r
    return cur_rate

def main():
    d = pd.read_csv("out/guardrails_decision.csv").iloc[0]
    decision = str(d["decision"])
    reasons = str(d.get("reasons",""))

    cur = load_policy()["current"]
    cur_rate = float(cur["control_rate"])

    if decision == "GO":
        nr = next_stage(cur_rate)
        if nr != cur_rate:
            update_policy(nr, "EXPERIMENT", f"rollout GO -> {nr}. {reasons}")
            print(f"✅ rollout {cur_rate} -> {nr}")
        else:
            print("✅ already best stage")
    elif decision == "HOLD":
        update_policy(cur_rate, cur.get("mode","EXPERIMENT"), f"hold. {reasons}")
        print("🟨 hold")
    else:
        update_policy(ROLLBACK_TO, "EXPERIMENT", f"rollback. {reasons}")
        print(f"🛑 rollback {cur_rate} -> {ROLLBACK_TO}")

if __name__ == "__main__":
    main()
