from typing import Dict, List

from ml_model import load_model


def classify_risk_level(risk_score: float) -> str:
    if risk_score < 0.4:
        return "LOW"
    if risk_score <= 0.7:
        return "MEDIUM"
    return "HIGH"


def detect_transaction(transaction: Dict) -> Dict:
    model = load_model()
    risk_score = round(model.predict_proba(transaction), 4)
    risk_level = classify_risk_level(risk_score)
    is_suspicious = risk_level == "HIGH"

    reasons: List[str] = []
    amount = float(transaction.get("amount", 0.0))
    city = str(transaction.get("city", ""))
    state = str(transaction.get("state", ""))

    if amount > 1200:
        reasons.append("High transaction amount")
    if city.lower() in {"unknowntown", "unknown_city"} or state.lower() == "na":
        reasons.append("Unusual or unknown location")
    if not reasons:
        reasons.append("No strong fraud indicators")

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "is_suspicious": is_suspicious,
        "reasons": reasons,
    }
