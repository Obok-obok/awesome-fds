import hashlib

def assign_group(claim_id: str, salt: str, control_rate: float) -> str:
    key = f"{salt}:{claim_id}".encode("utf-8")
    h = hashlib.sha256(key).hexdigest()
    u = int(h[:8], 16) / 0xFFFFFFFF
    return "CONTROL" if u < control_rate else "TREATMENT"
