import csv
import os
import random
import uuid
from typing import Dict, List


SAMPLE_DATA_PATH = "sample_data.csv"


def generate_transaction_id() -> str:
    return str(uuid.uuid4())[:8]


def ensure_numeric(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalized_key(original: str) -> str:
    lowered = original.lower()
    if lowered in {"transaction_id", "trans_num", "tx_id"}:
        return "transaction_id"
    if lowered in {"amt", "amount", "transaction_amount"}:
        return "amount"
    if lowered in {"merchant", "merchant_name"}:
        return "merchant"
    if lowered in {"city", "location"}:
        return "city"
    if lowered in {"state", "region"}:
        return "state"
    if lowered in {"account_id", "account", "cc_num", "customer_id"}:
        return "account_id"
    return original


def normalize_rows(rows: List[Dict]) -> List[Dict]:
    normalized: List[Dict] = []
    for row in rows:
        mapped = {}
        for key, value in row.items():
            mapped[_normalized_key(key)] = value
        normalized.append(
            {
                "transaction_id": mapped.get("transaction_id") or generate_transaction_id(),
                "account_id": str(mapped.get("account_id", f"AS{random.randint(10000000, 99999999)}")),
                "amount": ensure_numeric(mapped.get("amount"), 0.0),
                "merchant": str(mapped.get("merchant", "unknown_merchant")),
                "city": str(mapped.get("city", "unknown_city")),
                "state": str(mapped.get("state", "NA")),
            }
        )
    return normalized


def create_sample_dataset(path: str = SAMPLE_DATA_PATH, rows: int = 20) -> List[Dict]:
    random.seed(42)
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "UnknownTown"]
    states = ["NY", "CA", "IL", "TX", "AZ", "NA"]
    merchants = ["grocery", "electronics", "fuel", "fashion", "travel", "gaming"]
    generated_rows: List[Dict] = []
    for _ in range(rows):
        generated_rows.append(
            {
                "transaction_id": generate_transaction_id(),
                "account_id": f"AS{random.randint(10000000, 99999999)}",
                "amount": round(random.lognormvariate(4.5, 1.1), 2),
                "merchant": random.choice(merchants),
                "city": random.choice(cities),
                "state": random.choice(states),
            }
        )

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "transaction_id",
                "account_id",
                "amount",
                "merchant",
                "city",
                "state",
            ],
        )
        writer.writeheader()
        writer.writerows(generated_rows)

    return generated_rows


def read_csv_rows(path: str) -> List[Dict]:
    with open(path, "r", newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return [dict(row) for row in reader]


def write_csv_rows(path: str, rows: List[Dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "transaction_id",
                "account_id",
                "amount",
                "merchant",
                "city",
                "state",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def load_dataset_from_available_sources() -> List[Dict]:
    candidates: List[str] = ["fraudTrain.csv", "fraudTest.csv", SAMPLE_DATA_PATH]
    for file_path in candidates:
        if os.path.exists(file_path):
            rows = read_csv_rows(file_path)
            return normalize_rows(rows)
    return normalize_rows(create_sample_dataset())
