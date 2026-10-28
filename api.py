from typing import Dict

from detection_engine import detect_transaction
from utils import ensure_numeric, generate_transaction_id


def process_transaction_input(payload: Dict) -> Dict:
    transaction = {
        "transaction_id": payload.get("transaction_id") or generate_transaction_id(),
        "account_id": payload.get("account_id", "UNKNOWN"),
        "amount": ensure_numeric(payload.get("amount"), 0.0),
        "merchant": payload.get("merchant", "unknown_merchant"),
        "city": payload.get("city", "unknown_city"),
        "state": payload.get("state", "NA"),
    }
    detection = detect_transaction(transaction)
    return {"transaction": transaction, "detection": detection}
