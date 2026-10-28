import sqlite3
import uuid
from typing import Dict, List


DB_PATH = "fraud_detection.db"


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(flagged_transactions)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    required_columns = {
        "id",
        "transaction_id",
        "account_id",
        "amount",
        "location",
        "risk_score",
        "risk_level",
        "is_suspicious",
        "reasons",
        "created_at",
    }
    if existing_columns and not required_columns.issubset(existing_columns):
        cursor.execute("DROP TABLE IF EXISTS flagged_transactions")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS flagged_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            amount REAL NOT NULL,
            location TEXT NOT NULL,
            risk_score REAL NOT NULL,
            risk_level TEXT NOT NULL,
            is_suspicious INTEGER NOT NULL,
            reasons TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS str_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            report_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id TEXT NOT NULL UNIQUE,
            transaction_id TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            risk_threshold INTEGER NOT NULL,
            large_tx_detection INTEGER NOT NULL,
            location_anomaly_detection INTEGER NOT NULL,
            rapid_tx_detection INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO app_settings (
            id, risk_threshold, large_tx_detection, location_anomaly_detection, rapid_tx_detection, updated_at
        ) VALUES (1, 70, 1, 1, 0, datetime('now'))
        """
    )
    conn.commit()
    conn.close()


def save_flagged_transaction(transaction: Dict, detection: Dict) -> None:
    if detection["risk_level"] not in {"MEDIUM", "HIGH"}:
        return

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO flagged_transactions (
            transaction_id, account_id, amount, location, risk_score, risk_level, is_suspicious, reasons, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            str(transaction.get("transaction_id", "")),
            str(transaction.get("account_id", "UNKNOWN")),
            float(transaction.get("amount", 0.0)),
            f"{transaction.get('city', 'unknown_city')}, {transaction.get('state', 'NA')}",
            float(detection["risk_score"]),
            detection["risk_level"],
            int(bool(detection["is_suspicious"])),
            "; ".join(detection["reasons"]),
        ),
    )
    conn.commit()
    conn.close()


def get_flagged_transactions(limit: int = 100) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT transaction_id, account_id, amount, location, risk_score, risk_level, is_suspicious, reasons, created_at
        FROM flagged_transactions
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "transaction_id": row[0],
            "account_id": row[1],
            "amount": row[2],
            "location": row[3],
            "risk_score": row[4],
            "risk_level": row[5],
            "is_suspicious": bool(row[6]),
            "reasons": row[7].split("; "),
            "created_at": row[8],
        }
        for row in rows
    ]


def get_settings() -> Dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT risk_threshold, large_tx_detection, location_anomaly_detection, rapid_tx_detection, updated_at
        FROM app_settings
        WHERE id = 1
        """
    )
    row = cursor.fetchone()
    conn.close()
    return {
        "risk_threshold": int(row[0]),
        "large_transaction_detection": bool(row[1]),
        "location_anomaly_detection": bool(row[2]),
        "rapid_transaction_detection": bool(row[3]),
        "updated_at": row[4],
    }


def save_settings(settings: Dict) -> Dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE app_settings
        SET risk_threshold = ?, large_tx_detection = ?, location_anomaly_detection = ?, rapid_tx_detection = ?,
            updated_at = datetime('now')
        WHERE id = 1
        """,
        (
            int(settings.get("risk_threshold", 70)),
            1 if bool(settings.get("large_transaction_detection", True)) else 0,
            1 if bool(settings.get("location_anomaly_detection", True)) else 0,
            1 if bool(settings.get("rapid_transaction_detection", False)) else 0,
        ),
    )
    conn.commit()
    conn.close()
    return get_settings()


def upsert_str_report(transaction_id: str, status: str, report_json: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO str_reports (transaction_id, status, report_json, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(transaction_id) DO UPDATE SET
            status = excluded.status,
            report_json = excluded.report_json,
            updated_at = datetime('now')
        """,
        (transaction_id, status, report_json),
    )
    conn.commit()
    conn.close()


def get_str_status_map(transaction_ids: List[str]) -> Dict[str, str]:
    if not transaction_ids:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    placeholders = ",".join(["?"] * len(transaction_ids))
    cursor.execute(
        f"""
        SELECT transaction_id, status
        FROM str_reports
        WHERE transaction_id IN ({placeholders})
        """,
        tuple(transaction_ids),
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def create_alert(transaction_id: str, severity: str) -> Dict:
    alert_id = f"ALT-{uuid.uuid4().hex[:8].upper()}"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alerts (alert_id, transaction_id, severity, status, created_at, updated_at)
        VALUES (?, ?, ?, 'Active', datetime('now'), datetime('now'))
        """,
        (alert_id, transaction_id, severity),
    )
    conn.commit()
    conn.close()
    return {"alert_id": alert_id, "transaction_id": transaction_id, "severity": severity, "status": "Active"}


def get_alerts(limit: int = 100) -> List[Dict]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT alert_id, transaction_id, severity, status, created_at
        FROM alerts
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "alert_id": row[0],
            "transaction_id": row[1],
            "severity": row[2],
            "status": row[3],
            "timestamp": row[4],
        }
        for row in rows
    ]


def resolve_alert(alert_id: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE alerts
        SET status = 'Resolved', updated_at = datetime('now')
        WHERE alert_id = ?
        """,
        (alert_id,),
    )
    conn.commit()
    conn.close()


def escalate_alert(alert_id: str) -> None:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE alerts
        SET severity = 'CRITICAL', status = 'Active', updated_at = datetime('now')
        WHERE alert_id = ?
        """,
        (alert_id,),
    )
    conn.commit()
    conn.close()
