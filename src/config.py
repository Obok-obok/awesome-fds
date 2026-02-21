from dataclasses import dataclass

@dataclass(frozen=True)
class CFG:
    # Data columns
    id_col: str = "claim_id"
    paid_col: str = "paid_amount"
    label_col: str = "label"   # optional

    # Experiment
    experiment_salt: str = "fraud-exp-v1"
    default_control_rate: float = 0.10

    # Review policy
    review_threshold: float = 0.85   # calibrated fraud probability
    max_daily_reviews: int = 500
    review_sla_hours: int = 72  # Ops SLA for review queue

    # Executive KPI targets (used for dashboard/charts)
    # These are *reporting* targets only; they don't affect model scoring.
    target_mtd_saving_krw: int = 200_000_000
    target_qtd_saving_krw: int = 600_000_000

    # Paths
    data_claims: str = "data/claims.csv"
    data_labels_feedback: str = "data/labels_feedback.csv"

    out_dir: str = "out"
    model_dir: str = "models"
