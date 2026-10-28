from typing import Dict


class FraudModel:
    def __init__(self) -> None:
        self.high_risk_locations = {"unknowntown", "unknown_city", "na"}

    def predict_proba(self, transaction: Dict) -> float:
        amount = float(transaction.get("amount", 0.0))
        city = str(transaction.get("city", "")).strip().lower()
        state = str(transaction.get("state", "")).strip().lower()

        score = 0.05

        if amount > 3000:
            score += 0.65
        elif amount > 1200:
            score += 0.45
        elif amount > 500:
            score += 0.25
        elif amount > 200:
            score += 0.10

        if city in self.high_risk_locations or state in self.high_risk_locations:
            score += 0.20

        if amount < 1:
            score += 0.05

        return max(0.0, min(score, 1.0))


_MODEL = None


def load_model() -> FraudModel:
    global _MODEL
    if _MODEL is None:
        _MODEL = FraudModel()
    return _MODEL
