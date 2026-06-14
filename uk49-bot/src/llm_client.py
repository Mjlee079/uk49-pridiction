"""UK49s Prediction Bot — LLM Client

Extracted to avoid circular imports between predictor.py, predictor_new.py,
diagnostic.py, ensemble.py, and memory.py.
"""

import os
import logging
import requests
from src.security import get_key, get_key_masked

logger = logging.getLogger(__name__)

# Get model name from secure manager (safe to log)
LLM_MODEL = get_key("LLM_MODEL") or "qwen3.7-plus"


class AnthropicCompatibleClient:
    """Custom client for Anthropic-compatible API with x-api-key header."""

    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url

    def messages_create(self, model, max_tokens, messages):
        """Create a message using the Anthropic Messages API format."""
        endpoint = f"{self.base_url}/messages"

        headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }

        data = {
            'model': model,
            'max_tokens': max_tokens,
            'messages': messages
        }

        response = requests.post(endpoint, headers=headers, json=data, timeout=180)
        response.raise_for_status()

        return response.json()


def get_llm_client():
    """Initialize LLM client using secure key manager."""
    # Priority 1: Custom API (Anthropic Messages API format)
    custom_key = get_key("CUSTOM_LLM_API_KEY")
    custom_url = get_key("CUSTOM_LLM_BASE_URL")

    if custom_key and custom_url:
        logger.info(f"Using Anthropic Messages API endpoint: {custom_url}")
        logger.info(f"API Key (masked): {get_key_masked('CUSTOM_LLM_API_KEY')}")
        return AnthropicCompatibleClient(custom_key, custom_url)

    # Priority 2: Groq (OpenAI format)
    try:
        from openai import OpenAI
        groq_key = get_key("GROQ_API_KEY")
        if groq_key:
            logger.info("Using Groq API (OpenAI format)")
            logger.info(f"API Key (masked): {get_key_masked('GROQ_API_KEY')}")
            return OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
            )
    except ImportError:
        pass

    logger.error("No LLM API key configured. Set CUSTOM_LLM_API_KEY or GROQ_API_KEY in .env")
    return None
