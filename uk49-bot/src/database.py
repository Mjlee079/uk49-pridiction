import os
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

logger = logging.getLogger(__name__)

# Parse DATABASE_URL from env (Render provides this)
raw_url = os.getenv("DATABASE_URL", "")

# Normalize postgres:// to postgresql:// for psycopg2
if raw_url.startswith("postgres://"):
    raw_url = raw_url.replace("postgres://", "postgresql://", 1)

# Connection pool (min=1, max=10 for free tier)
_db_pool = None

def _get_pool():
    global _db_pool
    if _db_pool is None:
        if not raw_url:
            raise RuntimeError("DATABASE_URL environment variable is not set!")
        _db_pool = pool.ThreadedConnectionPool(1, 10, raw_url)
        logger.info("PostgreSQL connection pool initialized")
    return _db_pool


def get_db_connection():
    """Get a database connection from the pool."""
    return _get_pool().getconn()


def release_db_connection(conn):
    """Return a connection to the pool."""
    if _db_pool:
        _db_pool.putconn(conn)


def init_db():
    """Initialize the database schema."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Main draws table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS draws (
            id SERIAL PRIMARY KEY,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(draw_date, draw_time, draw_type)
        )
    """
    )

    # Predictions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS predictions (
            id SERIAL PRIMARY KEY,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Index on predicted_for for fast lookups
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
            id SERIAL PRIMARY KEY,
            prediction_id INTEGER,
            actual_numbers TEXT,
            matches_count INTEGER,
            accuracy_score REAL,
            notes TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (prediction_id) REFERENCES predictions(id)
        )
    """
    )

    # Statistics snapshots
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS stats_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            hot_numbers TEXT,
            cold_numbers TEXT,
            gap_data TEXT,
            trend_data TEXT,
            sequence_patterns TEXT
        )
    """
    )

    # Audit log table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            action TEXT NOT NULL,
            key_hash TEXT,
            user_id TEXT,
            user_name TEXT,
            details TEXT,
            success INTEGER DEFAULT 1,
            ip_address TEXT,
            error_message TEXT
        )
    """
    )

    # Bot state table (for persistent state)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            state JSONB DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    # Insert default state if not exists
    cursor.execute(
        """
        INSERT INTO bot_state (id, state) VALUES (1, '{}')
        ON CONFLICT (id) DO NOTHING
    """
    )

    conn.commit()
    release_db_connection(conn)
    logger.info("Database initialized successfully (PostgreSQL).")


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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (draw_date, draw_time, draw_type, *numbers, bonus),
        )
        conn.commit()
        logger.info(f"Inserted draw for {draw_date} {draw_time}")
        return True
    except psycopg2.IntegrityError:
        logger.info(f"Duplicate draw ignored: {draw_date} {draw_time}")
        return False
    finally:
        release_db_connection(conn)


def get_all_draws(draw_type: str = "LUNCHTIME", limit: Optional[int] = None) -> List[dict]:
    """Get all draws, optionally limited."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = """
        SELECT id, draw_date, draw_time, draw_type,
               ball1, ball2, ball3, ball4, ball5, ball6, bonus
        FROM draws
        WHERE draw_type = %s
        ORDER BY draw_date DESC, draw_time DESC
    """
    params = (draw_type,)
    if limit:
        query += " LIMIT %s"
        params = (draw_type, limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    release_db_connection(conn)

    return [dict(row) for row in rows]


def get_latest_draw(draw_type: str = "LUNCHTIME") -> Optional[dict]:
    """Get the most recent draw."""
    draws = get_all_draws(draw_type, limit=1)
    return draws[0] if draws else None


def get_draws_in_range(start_date: str, end_date: str, draw_type: str = "LUNCHTIME") -> List[dict]:
    """Get draws within a date range (YYYY-MM-DD format)."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT id, draw_date, draw_time, draw_type,
               ball1, ball2, ball3, ball4, ball5, ball6, bonus
        FROM draws
        WHERE draw_type = %s AND draw_date >= %s AND draw_date <= %s
        ORDER BY draw_date DESC, draw_time DESC
    """,
        (draw_type, start_date, end_date),
    )
    rows = cursor.fetchall()
    release_db_connection(conn)

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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """,
        (predicted_for, draw_type, top_str, conf_str, reasoning, method_used,
         all_rows_str, signal_scores_str, weights_used_str),
    )
    prediction_id = cursor.fetchone()[0]
    conn.commit()
    release_db_connection(conn)

    logger.info(f"Prediction {prediction_id} saved for {predicted_for}")
    return prediction_id


def update_prediction_result(prediction_id: int, actual_numbers: List[int]):
    """Store the actual draw result on a prediction row."""
    conn = get_db_connection()
    cursor = conn.cursor()
    actual_str = ",".join(map(str, actual_numbers))
    cursor.execute(
        "UPDATE predictions SET draw_result = %s WHERE id = %s",
        (actual_str, prediction_id),
    )
    conn.commit()
    release_db_connection(conn)
    logger.info(f"Prediction {prediction_id} updated with actual draw result")


def get_recent_predictions(limit: int = 10, draw_type: str = "LUNCHTIME") -> List[dict]:
    """Get recent predictions."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT p.*, a.matches_count, a.accuracy_score, a.actual_numbers
        FROM predictions p
        LEFT JOIN accuracy a ON p.id = a.prediction_id
        WHERE p.draw_type = %s
        ORDER BY p.created_at DESC
        LIMIT %s
    """,
        (draw_type, limit),
    )
    rows = cursor.fetchall()
    release_db_connection(conn)

    predictions = []
    for row in rows:
        pred = dict(row)
        pred["top_numbers"] = list(map(int, pred["top_numbers"].split(",")))
        pred["confidence_scores"] = list(map(float, pred["confidence_scores"].split(",")))
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        "SELECT top_numbers FROM predictions WHERE id = %s", (prediction_id,)
    )
    row = cursor.fetchone()
    if not row:
        release_db_connection(conn)
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
        VALUES (%s, %s, %s, %s, %s)
    """,
        (prediction_id, actual_str, matches, accuracy, notes),
    )
    conn.commit()
    release_db_connection(conn)

    logger.info(f"Accuracy updated for prediction {prediction_id}: {matches}/3 ({accuracy:.1f}%)")
    return matches, accuracy


def get_accuracy_stats(draw_type: str = "LUNCHTIME") -> dict:
    """Get overall accuracy statistics."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

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
        WHERE p.draw_type = %s AND a.id IS NOT NULL
    """,
        (draw_type,),
    )
    row = cursor.fetchone()
    release_db_connection(conn)

    return dict(row) if row else {}


def get_draw_count() -> int:
    """Get total number of draws in database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM draws WHERE draw_type = 'LUNCHTIME'")
    count = cursor.fetchone()[0]
    release_db_connection(conn)
    return count


# =============================================================================
# Bot State Persistence (PostgreSQL-backed)
# =============================================================================

def load_bot_state() -> Dict[str, Any]:
    """Load bot state from PostgreSQL. Returns empty dict if not found."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT state FROM bot_state WHERE id = 1")
    row = cursor.fetchone()
    release_db_connection(conn)
    if row and row["state"]:
        return dict(row["state"])
    return {}


def save_bot_state(state: Dict[str, Any]):
    """Save bot state to PostgreSQL."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO bot_state (id, state, updated_at)
        VALUES (1, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (id) DO UPDATE SET
            state = EXCLUDED.state,
            updated_at = CURRENT_TIMESTAMP
    """,
        (json.dumps(state),),
    )
    conn.commit()
    release_db_connection(conn)
    logger.info("Bot state saved to PostgreSQL")
