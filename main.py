import json
import random
import uuid
from typing import Dict, List

import os

from flask import Flask, Response, jsonify, render_template, request, send_from_directory

from api import process_transaction_input
from clean_dataset import clean_dataset
from database import (
    create_alert,
    escalate_alert,
    get_alerts,
    get_flagged_transactions,
    get_settings,
    get_str_status_map,
    init_db,
    resolve_alert,
    save_flagged_transaction,
    save_settings,
    upsert_str_report,
)
from utils import load_dataset_from_available_sources


app = Flask(__name__)
TRANSACTION_CACHE: List[Dict] = []
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")


def _build_monitoring_record(result: Dict) -> Dict:
    transaction = result["transaction"]
    detection = result["detection"]
    return {
        "transaction_id": transaction["transaction_id"],
        "account_id": transaction.get("account_id", "UNKNOWN"),
        "amount": round(transaction["amount"], 2),
        "location": f"{transaction['city']}, {transaction['state']}",
        "risk_score": detection["risk_score"],
        "composite_score": int(round(detection["risk_score"] * 100)),
        "risk_level": detection["risk_level"],
        "suspicious": detection["is_suspicious"],
        "reasons": detection["reasons"],
        "alert_status": "SENT" if detection["is_suspicious"] else "CLEAR",
    }


def _summaries(records: List[Dict]) -> Dict:
    if not records:
        return {
            "total": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "suspicious": 0,
            "avg_risk_score": 0.0,
        }

    high = sum(1 for r in records if r["risk_level"] == "HIGH")
    medium = sum(1 for r in records if r["risk_level"] == "MEDIUM")
    low = sum(1 for r in records if r["risk_level"] == "LOW")
    suspicious = sum(1 for r in records if r["suspicious"])
    avg_risk = sum(r["risk_score"] for r in records) / len(records)
    return {
        "total": len(records),
        "high": high,
        "medium": medium,
        "low": low,
        "suspicious": suspicious,
        "avg_risk_score": round(avg_risk, 4),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/reports")
def reports_page():
    return render_template("reports.html")


@app.route("/transactions")
def transactions_page():
    return render_template("transactions.html")


@app.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


@app.route("/alerts")
def alerts_page():
    return render_template("alerts.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/module")
@app.route("/module/")
def module_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/module/<path:path>")
def module_assets(path: str):
    file_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(file_path):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/load-dataset", methods=["GET"])
def load_dataset():
    clean_dataset()
    rows = load_dataset_from_available_sources()[:100]
    response = []
    TRANSACTION_CACHE.clear()
    for row in rows:
        payload = {
            "transaction_id": row["transaction_id"],
            "account_id": row.get("account_id", "UNKNOWN"),
            "amount": float(row["amount"]),
            "merchant": row["merchant"],
            "city": row["city"],
            "state": row["state"],
        }
        result = process_transaction_input(payload)
        save_flagged_transaction(result["transaction"], result["detection"])
        record = _build_monitoring_record(result)
        TRANSACTION_CACHE.append(record)
        response.append(record)
        if record["risk_level"] in {"MEDIUM", "HIGH"}:
            if record["risk_level"] == "HIGH":
                severity = "CRITICAL" if record["risk_score"] > 0.9 else "HIGH"
            else:
                severity = "MEDIUM"
            create_alert(record["transaction_id"], severity)
    return jsonify({"transactions": response, "summary": _summaries(response)})


@app.route("/process-transaction", methods=["POST"])
def process_transaction():
    payload = request.get_json(silent=True) or {}
    result = process_transaction_input(payload)
    save_flagged_transaction(result["transaction"], result["detection"])
    record = _build_monitoring_record(result)
    TRANSACTION_CACHE.insert(0, record)
    if len(TRANSACTION_CACHE) > 250:
        TRANSACTION_CACHE.pop()
    if record["risk_level"] in {"MEDIUM", "HIGH"}:
        if record["risk_level"] == "HIGH":
            severity = "CRITICAL" if record["risk_score"] > 0.9 else "HIGH"
        else:
            severity = "MEDIUM"
        create_alert(record["transaction_id"], severity)
    return jsonify(
        {
            "transaction_id": result["transaction"]["transaction_id"],
            "account_id": result["transaction"].get("account_id", "UNKNOWN"),
            "risk_score": result["detection"]["risk_score"],
            "risk_level": result["detection"]["risk_level"],
            "is_suspicious": result["detection"]["is_suspicious"],
            "reasons": result["detection"]["reasons"],
            "location": f"{result['transaction']['city']}, {result['transaction']['state']}",
            "composite_score": int(round(result["detection"]["risk_score"] * 100)),
            "alert_status": "SENT" if result["detection"]["is_suspicious"] else "CLEAR",
        }
    )


def _simulate_live_transaction() -> Dict:
    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "UnknownTown"]
    states = ["NY", "CA", "IL", "TX", "AZ", "NA"]
    # Bias some transactions to be high-risk so alerts/features are observable.
    force_high = random.random() < 0.25
    force_medium = (not force_high) and (random.random() < 0.35)
    amount = round(random.lognormvariate(4.6, 1.1), 2)
    city = random.choice(cities)
    state = random.choice(states)
    if force_high:
        amount = round(random.uniform(2500, 6500), 2)
        city = "UnknownTown"
        state = "NA"
    elif force_medium:
        amount = round(random.uniform(800, 1800), 2)

    payload = {
        "transaction_id": f"LIVE-{uuid.uuid4().hex[:8]}",
        "account_id": f"USR-{random.randint(100, 999)}",
        "amount": amount,
        "merchant": random.choice(["grocery", "electronics", "fuel", "fashion", "travel", "gaming"]),
        "city": city,
        "state": state,
    }
    result = process_transaction_input(payload)
    record = _build_monitoring_record(result)
    TRANSACTION_CACHE.insert(0, record)
    if len(TRANSACTION_CACHE) > 250:
        TRANSACTION_CACHE.pop()
    if record["risk_level"] in {"MEDIUM", "HIGH"}:
        if record["risk_level"] == "HIGH":
            severity = "CRITICAL" if record["risk_score"] > 0.9 else "HIGH"
        else:
            severity = "MEDIUM"
        create_alert(record["transaction_id"], severity)
    return record


@app.route("/api/reports", methods=["GET", "POST"])
def api_reports():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        transaction_id = str(payload.get("transaction_id", "")).strip()
        if not transaction_id:
            return jsonify({"error": "transaction_id is required"}), 400
        report = {
            "transaction_id": transaction_id,
            "generated_at": "now",
            "notes": "STR report generated by ASTR",
        }
        upsert_str_report(transaction_id, "Submitted", json.dumps(report))
        return jsonify({"ok": True, "status": "Submitted"})

    user_id = (request.args.get("user_id") or "").strip().lower()
    min_risk = request.args.get("min_risk")
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    rows = get_flagged_transactions(500)
    # suspicious = HIGH only
    rows = [r for r in rows if r["risk_level"] == "HIGH"]

    if user_id:
        rows = [r for r in rows if str(r["account_id"]).lower().find(user_id) >= 0]
    if min_risk:
        try:
            m = float(min_risk)
            rows = [r for r in rows if float(r["risk_score"]) * 100 >= m]
        except ValueError:
            pass
    if from_date:
        rows = [r for r in rows if str(r["created_at"]) >= from_date]
    if to_date:
        rows = [r for r in rows if str(r["created_at"]) <= to_date]

    ids = [r["transaction_id"] for r in rows]
    status_map = get_str_status_map(ids)
    out = []
    for r in rows[:200]:
        out.append(
            {
                "transaction_id": r["transaction_id"],
                "user_id": r["account_id"],
                "amount": r["amount"],
                "risk_score": int(round(float(r["risk_score"]) * 100)),
                "status": status_map.get(r["transaction_id"], "Pending"),
                "date": r["created_at"],
            }
        )
    return jsonify({"reports": out})


@app.route("/api/reports/<transaction_id>/download", methods=["GET"])
def api_report_download(transaction_id: str):
    # Simulated PDF download
    content = f"ASTR STR REPORT\\nTransaction: {transaction_id}\\nGenerated: now\\n"
    return Response(
        content,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={transaction_id}_STR.pdf"},
    )


@app.route("/api/transactions", methods=["GET"])
def api_transactions():
    # simulate new item each poll
    _simulate_live_transaction()
    q = (request.args.get("q") or "").strip().lower()
    min_risk = request.args.get("min_risk")
    tier = (request.args.get("tier") or "").strip().upper()

    items = list(TRANSACTION_CACHE)
    if q:
        items = [
            t
            for t in items
            if q in str(t["transaction_id"]).lower()
            or q in str(t["account_id"]).lower()
            or q in str(t["location"]).lower()
        ]
    if min_risk:
        try:
            m = float(min_risk)
            items = [t for t in items if float(t["composite_score"]) >= m]
        except ValueError:
            pass
    if tier in {"LOW", "MEDIUM", "HIGH"}:
        items = [t for t in items if t["risk_level"] == tier]

    out = [
        {
            "txn_id": t["transaction_id"],
            "user_id": t["account_id"],
            "amount": t["amount"],
            "location": t["location"],
            "timestamp": t.get("created_at") or "",
            "risk_score": t["composite_score"],
        }
        for t in items[:100]
    ]
    return jsonify({"transactions": out})


@app.route("/api/analytics", methods=["GET"])
def api_analytics():
    items = list(TRANSACTION_CACHE)
    total = len(items)
    high = sum(1 for t in items if t["risk_level"] == "HIGH")
    suspicious_percent = int(round((high / total) * 100)) if total else 0

    # simple time buckets by index (mock "over time")
    trend = []
    for i in range(12):
        slice_ = items[i * 10 : (i + 1) * 10]
        trend.append(
            {
                "period": f"Bucket {i + 1}",
                "transactions": len(slice_),
                "suspicious": sum(1 for t in slice_ if t["risk_level"] == "HIGH"),
            }
        )

    dist = [
        {"name": "Low", "value": sum(1 for t in items if t["risk_level"] == "LOW")},
        {"name": "Medium", "value": sum(1 for t in items if t["risk_level"] == "MEDIUM")},
        {"name": "High", "value": high},
    ]
    return jsonify(
        {
            "total_transactions": total,
            "suspicious_percent": suspicious_percent,
            "high_risk_count": high,
            "trend": trend,
            "risk_distribution": dist,
        }
    )


@app.route("/api/alerts", methods=["GET", "POST"])
def api_alerts():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "")).strip().lower()
        alert_id = str(payload.get("alert_id", "")).strip()
        if not alert_id:
            return jsonify({"error": "alert_id is required"}), 400
        if action == "resolve":
            resolve_alert(alert_id)
        elif action == "escalate":
            escalate_alert(alert_id)
        else:
            return jsonify({"error": "invalid action"}), 400
        return jsonify({"ok": True})
    return jsonify({"alerts": get_alerts(100)})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        saved = save_settings(
            {
                "risk_threshold": payload.get("risk_threshold", 70),
                "large_transaction_detection": payload.get("large_transaction_detection", True),
                "location_anomaly_detection": payload.get("location_anomaly_detection", True),
                "rapid_transaction_detection": payload.get("rapid_transaction_detection", False),
            }
        )
        return jsonify({"settings": saved})
    return jsonify({"settings": get_settings()})


@app.route("/dashboard-data", methods=["GET"])
def dashboard_data():
    return jsonify(
        {
            "transactions": TRANSACTION_CACHE,
            "summary": _summaries(TRANSACTION_CACHE),
            "flagged_transactions": get_flagged_transactions(50),
        }
    )


@app.route("/flagged-transactions", methods=["GET"])
def flagged_transactions():
    return jsonify({"transactions": get_flagged_transactions(100)})


@app.route("/export-report", methods=["GET"])
def export_report():
    body = json.dumps(
        {"summary": _summaries(TRANSACTION_CACHE), "transactions": TRANSACTION_CACHE},
        indent=2,
    )
    return Response(
        body,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=astr_report.json"},
    )


def _bootstrap_cache() -> None:
    """Populate the in-memory cache on startup so all pages have data immediately."""
    clean_dataset()
    rows = load_dataset_from_available_sources()[:100]
    TRANSACTION_CACHE.clear()
    for row in rows:
        payload = {
            "transaction_id": row["transaction_id"],
            "account_id": row.get("account_id", "UNKNOWN"),
            "amount": float(row["amount"]),
            "merchant": row["merchant"],
            "city": row["city"],
            "state": row["state"],
        }
        result = process_transaction_input(payload)
        save_flagged_transaction(result["transaction"], result["detection"])
        record = _build_monitoring_record(result)
        TRANSACTION_CACHE.append(record)
        if record["risk_level"] in {"MEDIUM", "HIGH"}:
            severity = "CRITICAL" if record["risk_score"] > 0.9 else record["risk_level"]
            create_alert(record["transaction_id"], severity)


if __name__ == "__main__":
    init_db()
    _bootstrap_cache()
    app.run(host="127.0.0.1", port=5000, debug=True)
