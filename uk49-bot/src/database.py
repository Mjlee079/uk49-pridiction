import sqlite3
import os
import json
from datetime import datetime
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DATABASE_URL", "data/uk49_lunchtime.db")


def get_db_connection() -> sqlite3.Connection:
    """Create a database connection."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Main draws table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_date TEXT NOT NULL,
            draw_time TEXT NOT NULL,
            draw_type TEXT NOT NULL DEFAULT 'LUNCHTIME',
            ball1 INTEGER NOT NULL,
            ball2 INTEGER NOT NULL,
            ball3 INTEGER NOT NULL,
            ball4 INTEGER NOT NULL,
            ball5 INTEGER NOT NULL,
            ball6 INTEGER NOT NULL,
            bonus INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(draw_date, draw_time, draw_type)
        )
    """
    )

    # Predictions table (memory/learning)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predicted_for TEXT NOT NULL,
            draw_type TEXT NOT NULL DEFAULT 'LUNCHTIME',
            top_numbers TEXT NOT NULL,
            confidence_scores TEXT NOT NULL,
            reasoning TEXT NOT NULL,
            method_used TEXT NOT NULL,
            all_rows TEXT,
            signal_scores TEXT,
            weights_used TEXT,
            draw_result TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Add index on predicted_for for fast diagnostic lookups
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_predictions_predicted_for
        ON predictions(predicted_for)
    """
    )

    # Accuracy tracking table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS accuracy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prediction_id INTEGER,
            actual_numbers TEXT,
            matches_count INTEGER,
            accuracy_score REAL,
            notes TEXT,
            checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prediction_id) REFERENCES predictions(id)
        )
    """
    )

    # Statistics snapshots (for analytics history)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stats_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT DEFAULT CURRENT_TIMESTAMP,
            hot_numbers TEXT,
            cold_numbers TEXT,
            gap_data TEXT,
            trend_data TEXT,
            sequence_patterns TEXT
        )
    """
    )

    # Migration: add new columns to existing predictions table
    _migrate_predictions_table(cursor)

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")


def _migrate_predictions_table(cursor):
    """Add missing columns to predictions table for v2 schema."""
    try:
        cursor.execute("PRAGMA table_info(predictions)")
        columns = [row[1] for row in cursor.fetchall()]

        if "all_rows" not in columns:
            cursor.execute("ALTER TABLE predictions ADD COLUMN all_rows TEXT")
            logger.info("Migrated: added all_rows column")
        if "signal_scores" not in columns:
            cursor.execute("ALTER TABLE predictions ADD COLUMN signal_scores TEXT")
            logger.info("Migrated: added signal_scores column")
        if "weights_used" not in columns:
            cursor.execute("ALTER TABLE predictions ADD COLUMN weights_used TEXT")
            logger.info("Migrated: added weights_used column")
        if "draw_result" not in columns:
            cursor.execute("ALTER TABLE predictions ADD COLUMN draw_result TEXT")
            logger.info("Migrated: added draw_result column")
    except Exception as e:
        logger.error(f"Migration error: {e}")


def insert_draw(
    draw_date: str,
    draw_time: str,
    numbers: List[int],
    bonus: int,
    draw_type: str = "LUNCHTIME",
) -> bool:
    """Insert a draw result. Returns True if inserted, False if duplicate."""
    if len(numbers) != 6:
        raise ValueError("Exactly 6 numbers required")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO draws (draw_date, draw_time, draw_type, ball1, ball2, ball3, ball4, ball5, ball6, bonus)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (draw_date, draw_time, draw_type, *numbers, bonus),
        )
        conn.commit()
        logger.info(f"Inserted draw for {draw_date} {draw_time}")
        return True
    except sqlite3.IntegrityError:
        logger.info(f"Duplicate draw ignored: {draw_date} {draw_time}")
        return False
    finally:
        conn.close()


def get_all_draws(draw_type: str = "LUNCHTIME", limit: Optional[int] = None) -> List[dict]:
    """Get all draws, optionally limited."""
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT id, draw_date, draw_time, draw_type,
               ball1, ball2, ball3, ball4, ball5, ball6, bonus
        FROM draws
        WHERE draw_type = ?
        ORDER BY draw_date DESC, draw_time DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query, (draw_type,))
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_latest_draw(draw_type: str = "LUNCHTIME") -> Optional[dict]:
    """Get the most recent draw."""
    draws = get_all_draws(draw_type, limit=1)
    return draws[0] if draws else None


def get_draws_in_range(start_date: str, end_date: str, draw_type: str = "LUNCHTIME") -> List[dict]:
    """Get draws within a date range (YYYY-MM-DD format)."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, draw_date, draw_time, draw_type,
               ball1, ball2, ball3, ball4, ball5, ball6, bonus
        FROM draws
        WHERE draw_type = ? AND draw_date >= ? AND draw_date <= ?
        ORDER BY draw_date DESC, draw_time DESC
    """,
        (draw_type, start_date, end_date),
    )
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def insert_prediction(
    predicted_for: str,
    top_numbers: List[int],
    confidence_scores: List[float],
    reasoning: str,
    method_used: str,
    draw_type: str = "LUNCHTIME",
    all_rows: List[List[int]] = None,
    signal_scores: dict = None,
    weights_used: dict = None,
) -> int:
    """Insert a prediction and return its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()

    top_str = ",".join(map(str, top_numbers))
    conf_str = ",".join(map(str, confidence_scores))
    all_rows_str = json.dumps(all_rows) if all_rows else None
    signal_scores_str = json.dumps(signal_scores) if signal_scores else None
    weights_used_str = json.dumps(weights_used) if weights_used else None

    cursor.execute(
        """
        INSERT INTO predictions (
            predicted_for, draw_type, top_numbers, confidence_scores, reasoning, method_used,
            all_rows, signal_scores, weights_used
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (predicted_for, draw_type, top_str, conf_str, reasoning, method_used,
         all_rows_str, signal_scores_str, weights_used_str),
    )
    prediction_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Prediction {prediction_id} saved for {predicted_for}")
    return prediction_id


def update_prediction_result(prediction_id: int, actual_numbers: List[int]):
    """Store the actual draw result on a prediction row."""
    conn = get_db_connection()
    cursor = conn.cursor()
    actual_str = ",".join(map(str, actual_numbers))
    cursor.execute(
        "UPDATE predictions SET draw_result = ? WHERE id = ?",
        (actual_str, prediction_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Prediction {prediction_id} updated with actual draw result")


def get_recent_predictions(limit: int = 10, draw_type: str = "LUNCHTIME") -> List[dict]:
    """Get recent predictions."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT p.*, a.matches_count, a.accuracy_score, a.actual_numbers
        FROM predictions p
        LEFT JOIN accuracy a ON p.id = a.prediction_id
        WHERE p.draw_type = ?
        ORDER BY p.created_at DESC
        LIMIT ?
    """,
        (draw_type, limit),
    )
    rows = cursor.fetchall()
    conn.close()

    predictions = []
    for row in rows:
        pred = dict(row)
        pred["top_numbers"] = list(map(int, pred["top_numbers"].split(",")))
        pred["confidence_scores"] = list(map(float, pred["confidence_scores"].split(",")))
        # Parse new JSON columns if present
        import json
        if pred.get("all_rows"):
            try:
                pred["all_rows"] = json.loads(pred["all_rows"])
            except:
                pred["all_rows"] = None
        if pred.get("signal_scores"):
            try:
                pred["signal_scores"] = json.loads(pred["signal_scores"])
            except:
                pred["signal_scores"] = None
        if pred.get("weights_used"):
            try:
                pred["weights_used"] = json.loads(pred["weights_used"])
            except:
                pred["weights_used"] = None
        predictions.append(pred)

    return predictions


def update_accuracy(prediction_id: int, actual_numbers: List[int]):
    """Compare prediction with actual results and update accuracy."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT top_numbers FROM predictions WHERE id = ?", (prediction_id,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return

    predicted = set(map(int, row["top_numbers"].split(",")))
    actual_set = set(actual_numbers)

    matches = len(predicted & actual_set)
    accuracy = (matches / len(predicted)) * 100 if predicted else 0

    actual_str = ",".join(map(str, actual_numbers))
    notes = f"Predicted {predicted}, got {matches}/3 matches"

    cursor.execute(
        """
        INSERT INTO accuracy (prediction_id, actual_numbers, matches_count, accuracy_score, notes)
        VALUES (?, ?, ?, ?, ?)
    """,
        (prediction_id, actual_str, matches, accuracy, notes),
    )
    conn.commit()
    conn.close()

    logger.info(f"Accuracy updated for prediction {prediction_id}: {matches}/3 ({accuracy:.1f}%)")
    return matches, accuracy


def get_accuracy_stats(draw_type: str = "LUNCHTIME") -> dict:
    """Get overall accuracy statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 
            COUNT(*) as total_predictions,
            AVG(matches_count) as avg_matches,
            AVG(accuracy_score) as avg_accuracy,
            SUM(CASE WHEN matches_count >= 1 THEN 1 ELSE 0 END) as at_least_1_match,
            SUM(CASE WHEN matches_count >= 2 THEN 1 ELSE 0 END) as at_least_2_matches,
            SUM(CASE WHEN matches_count = 3 THEN 1 ELSE 0 END) as all_3_matches
        FROM predictions p
        LEFT JOIN accuracy a ON p.id = a.prediction_id
        WHERE p.draw_type = ? AND a.id IS NOT NULL
    """,
        (draw_type,),
    )
    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else {}


def get_draw_count() -> int:
    """Get total number of draws in database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM draws WHERE draw_type = 'LUNCHTIME'")
    count = cursor.fetchone()[0]
    conn.close()
    return count
