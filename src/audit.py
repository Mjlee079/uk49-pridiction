import os
import logging
import hashlib
from datetime import datetime
from typing import Dict, Optional, List
from src.database import get_db_connection

logger = logging.getLogger(__name__)


def _hash_key(key: str) -> str:
    """Create a hash of a key for audit logging."""
    if not key:
        return "[EMPTY]"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class AuditLogger:
    """
    Audit logger that tracks API key usage without exposing keys.
    Records: timestamp, action, key_hash, user_id, success/failure
    """

    def __init__(self):
        self._init_db()

    def _init_db(self):
        """Initialize audit table in database."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                key_hash TEXT,
                user_id TEXT,
                user_name TEXT,
                details TEXT,
                success INTEGER DEFAULT 1,
                ip_address TEXT,
                error_message TEXT
            )
        """)

        conn.commit()
        conn.close()

    def log_prediction_request(
        self,
        user_id: str,
        user_name: str,
        key_used: str,
        success: bool = True,
        error: str = None,
    ):
        """Log a prediction API call."""
        self._log(
            action="PREDICTION_REQUEST",
            key_hash=_hash_key(key_used),
            user_id=str(user_id),
            user_name=user_name,
            details="User requested predictions",
            success=success,
            error_message=error,
        )

    def log_scrape_attempt(
        self,
        user_id: str,
        user_name: str,
        success: bool = True,
        error: str = None,
    ):
        """Log a scrape attempt."""
        self._log(
            action="SCRAPE_ATTEMPT",
            user_id=str(user_id),
            user_name=user_name,
            details="Manual scrape triggered",
            success=success,
            error_message=error,
        )

    def log_api_call(
        self,
        action: str,
        key_used: str,
        user_id: str = None,
        success: bool = True,
        error: str = None,
    ):
        """Log any API call with key hash."""
        self._log(
            action=action,
            key_hash=_hash_key(key_used),
            user_id=str(user_id) if user_id else None,
            details=f"API call: {action}",
            success=success,
            error_message=error,
        )

    def log_security_event(
        self,
        event: str,
        user_id: str = None,
        details: str = None,
    ):
        """Log a security-related event."""
        self._log(
            action="SECURITY_EVENT",
            user_id=str(user_id) if user_id else None,
            details=details or event,
            success=False,  # Security events are failures
        )

    def _log(
        self,
        action: str,
        key_hash: str = None,
        user_id: str = None,
        user_name: str = None,
        details: str = None,
        success: bool = True,
        ip_address: str = None,
        error_message: str = None,
    ):
        """Internal logging method."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO audit_log (
                    timestamp, action, key_hash, user_id, user_name,
                    details, success, ip_address, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                action,
                key_hash,
                user_id,
                user_name,
                details,
                1 if success else 0,
                ip_address,
                error_message,
            ))

            conn.commit()
            conn.close()

            # Also log to Python logger (safe, no keys exposed)
            logger.info(f"Audit: {action} | user={user_id} | success={success}")

        except Exception as e:
            logger.error(f"Audit logging failed: {e}")

    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """Get recent audit logs."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]

    def get_stats(self) -> Dict:
        """Get audit statistics."""
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_actions,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as failed,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT key_hash) as unique_keys
            FROM audit_log
        """)

        row = cursor.fetchone()
        conn.close()

        return dict(row) if row else {}


# Global instance
_audit_logger = None


def get_audit_logger() -> AuditLogger:
    """Get the singleton audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def log_prediction(user_id: str, user_name: str, key_used: str, success: bool = True, error: str = None):
    """Log a prediction request."""
    get_audit_logger().log_prediction_request(user_id, user_name, key_used, success, error)


def log_scrape(user_id: str, user_name: str, success: bool = True, error: str = None):
    """Log a scrape attempt."""
    get_audit_logger().log_scrape_attempt(user_id, user_name, success, error)


def log_api_call(action: str, key_used: str, user_id: str = None, success: bool = True, error: str = None):
    """Log an API call."""
    get_audit_logger().log_api_call(action, key_used, user_id, success, error)


def log_security_event(event: str, user_id: str = None, details: str = None):
    """Log a security event."""
    get_audit_logger().log_security_event(event, user_id, details)
