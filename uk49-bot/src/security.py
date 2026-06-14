import os
import re
import hashlib
import logging
from typing import Optional, Dict
from dotenv import load_dotenv

# Try to load .env file if it exists
if os.path.exists('.env'):
    load_dotenv()

logger = logging.getLogger(__name__)


class SecureKeyManager:
    """
    Secure key manager that prevents accidental exposure.
    Loads keys from environment, validates them, and provides sanitized access.
    """

    def __init__(self):
        self._keys: Dict[str, str] = {}
        self._load_keys()

    def _load_keys(self):
        """Load keys from environment with validation."""
        # Telegram Bot Token
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if telegram_token and self._is_valid_telegram_token(telegram_token):
            self._keys["TELEGRAM_BOT_TOKEN"] = telegram_token
        elif telegram_token:
            logger.warning("Invalid Telegram token format detected")

        # Custom LLM API Key
        custom_key = os.getenv("CUSTOM_LLM_API_KEY", "").strip()
        if custom_key:
            self._keys["CUSTOM_LLM_API_KEY"] = custom_key

        # Custom LLM Base URL
        custom_url = os.getenv("CUSTOM_LLM_BASE_URL", "").strip()
        if custom_url:
            self._keys["CUSTOM_LLM_BASE_URL"] = custom_url

        # Groq API Key (optional)
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            self._keys["GROQ_API_KEY"] = groq_key

        # LLM Model
        llm_model = os.getenv("LLM_MODEL", "qwen/qwen3-32b").strip()
        self._keys["LLM_MODEL"] = llm_model

        # Admin IDs
        admin_ids = os.getenv("ADMIN_IDS", "").strip()
        if admin_ids:
            self._keys["ADMIN_IDS"] = admin_ids

    def _is_valid_telegram_token(self, token: str) -> bool:
        """Validate Telegram bot token format."""
        pattern = r'^\d+:[A-Za-z0-9_-]{35,}$'
        return bool(re.match(pattern, token))

    def get_key(self, name: str) -> Optional[str]:
        """Get a key by name. Returns None if not found."""
        return self._keys.get(name)

    def get_key_masked(self, name: str) -> str:
        """Get a masked version of a key for logging."""
        key = self._keys.get(name, "")
        if not key:
            return "[NOT SET]"
        if len(key) <= 8:
            return "***" + key[-3:]
        return key[:3] + "***" + key[-4:]

    def get_key_hash(self, name: str) -> str:
        """Get a SHA-256 hash of the key for audit logging."""
        key = self._keys.get(name, "")
        if not key:
            return "[EMPTY]"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def has_key(self, name: str) -> bool:
        """Check if a key is configured."""
        return name in self._keys and self._keys[name]

    def validate_all_keys(self) -> Dict[str, bool]:
        """Validate all required keys are present."""
        required = ["TELEGRAM_BOT_TOKEN", "CUSTOM_LLM_API_KEY"]
        return {name: self.has_key(name) for name in required}

    def get_status(self) -> Dict:
        """Get status of all keys (masked)."""
        return {
            "TELEGRAM_BOT_TOKEN": self.get_key_masked("TELEGRAM_BOT_TOKEN"),
            "CUSTOM_LLM_API_KEY": self.get_key_masked("CUSTOM_LLM_API_KEY"),
            "CUSTOM_LLM_BASE_URL": self.get_key_masked("CUSTOM_LLM_BASE_URL"),
            "GROQ_API_KEY": self.get_key_masked("GROQ_API_KEY"),
            "LLM_MODEL": self._keys.get("LLM_MODEL", "[NOT SET]"),
            "ADMIN_IDS": self._keys.get("ADMIN_IDS", "[NOT SET]"),
        }

    def __repr__(self):
        return f"SecureKeyManager(keys_loaded={len(self._keys)}, keys_masked=True)"

    def __str__(self):
        return self.__repr__()


# Global instance
_key_manager = None


def get_key_manager() -> SecureKeyManager:
    """Get the singleton key manager instance."""
    global _key_manager
    if _key_manager is None:
        _key_manager = SecureKeyManager()
    else:
        # Reload keys in case .env was loaded after first import
        _key_manager._load_keys()
    return _key_manager


def get_key(name: str) -> Optional[str]:
    """Get a key by name."""
    return get_key_manager().get_key(name)


def get_key_masked(name: str) -> str:
    """Get a masked key for display."""
    return get_key_manager().get_key_masked(name)


def has_key(name: str) -> bool:
    """Check if a key exists."""
    return get_key_manager().has_key(name)


def validate_keys() -> Dict[str, bool]:
    """Validate all required keys."""
    return get_key_manager().validate_all_keys()


def get_key_status() -> Dict:
    """Get status of all keys (safe to log)."""
    return get_key_manager().get_status()


def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive data in text (API keys, tokens, etc.).
    Use this before logging any error messages or tracebacks.
    """
    # Mask Telegram tokens
    text = re.sub(
        r'\d{8,}:[A-Za-z0-9_-]{30,}',
        '[TELEGRAM_TOKEN_MASKED]',
        text
    )

    # Mask API keys (sk- prefix)
    text = re.sub(
        r'sk-[A-Za-z0-9]{30,}',
        '[API_KEY_MASKED]',
        text
    )

    # Mask Groq keys
    text = re.sub(
        r'gsk_[A-Za-z0-9]{30,}',
        '[GROQ_KEY_MASKED]',
        text
    )

    # Mask generic hex keys
    text = re.sub(
        r'[a-f0-9]{32,}',
        '[HEX_KEY_MASKED]',
        text
    )

    return text
