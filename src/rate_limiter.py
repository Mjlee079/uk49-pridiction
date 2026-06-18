import time
import logging
from typing import Dict, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter to prevent API abuse.
    Limits requests per user per time window.
    """

    def __init__(self):
        # user_id -> list of timestamps
        self._requests: Dict[str, list] = defaultdict(list)
        self._limits = {
            "predict": {"max": 5, "window": 3600},  # 5 predictions per hour
            "scrape": {"max": 3, "window": 3600},    # 3 scrapes per hour
            "stats": {"max": 10, "window": 3600},    # 10 stats requests per hour
            "default": {"max": 20, "window": 3600},  # 20 default per hour
        }

    def is_allowed(self, user_id: str, action: str = "default") -> Tuple[bool, str]:
        """
        Check if a request is allowed.
        Returns: (allowed, reason)
        """
        if not user_id:
            return True, ""

        limit_config = self._limits.get(action, self._limits["default"])
        max_requests = limit_config["max"]
        window = limit_config["window"]

        now = time.time()

        # Clean old requests
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < window
        ]

        # Check limit
        if len(self._requests[user_id]) >= max_requests:
            oldest = min(self._requests[user_id])
            wait_time = int(window - (now - oldest))
            return False, f"Rate limit exceeded. Wait {wait_time} seconds."

        # Record request
        self._requests[user_id].append(now)
        return True, ""

    def get_remaining(self, user_id: str, action: str = "default") -> Tuple[int, int]:
        """
        Get remaining requests and reset time.
        Returns: (remaining, reset_seconds)
        """
        if not user_id:
            return 999, 0

        limit_config = self._limits.get(action, self._limits["default"])
        max_requests = limit_config["max"]
        window = limit_config["window"]

        now = time.time()

        # Clean old requests
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if now - t < window
        ]

        remaining = max_requests - len(self._requests[user_id])

        if self._requests[user_id]:
            oldest = min(self._requests[user_id])
            reset_time = int(window - (now - oldest))
        else:
            reset_time = 0

        return max(0, remaining), reset_time

    def reset(self, user_id: str):
        """Reset limits for a user."""
        if user_id in self._requests:
            del self._requests[user_id]


# Global instance
_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get the singleton rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def check_rate_limit(user_id: str, action: str = "default") -> Tuple[bool, str]:
    """Check if request is allowed."""
    return get_rate_limiter().is_allowed(user_id, action)


def get_rate_limit_status(user_id: str, action: str = "default") -> Tuple[int, int]:
    """Get remaining requests and reset time."""
    return get_rate_limiter().get_remaining(user_id, action)
