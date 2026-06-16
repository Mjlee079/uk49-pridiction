"""UK49s Prediction Bot — PostgreSQL-backed State Persistence

Handles loading, saving, and updating of the bot's internal state.
State is persisted in PostgreSQL (bot_state table) instead of a JSON file.
"""

import json
import os
import logging
from typing import Dict, List, Any
from datetime import datetime
from src.database import load_bot_state, save_bot_state

logger = logging.getLogger(__name__)

# Default weights per prompt specification
DEFAULT_WEIGHTS = {
    "frequency_gap": 0.25,
    "markov": 0.20,
    "cooccurrence": 0.20,
    "positional": 0.15,
    "lstm": 0.20,
}


def load_state() -> Dict[str, Any]:
    """Load state from PostgreSQL. Returns defaults if not found."""
    state = load_bot_state()
    if state:
        logger.info("State loaded from PostgreSQL")
        # Ensure all required keys exist
        if "signal_weights" not in state:
            state["signal_weights"] = DEFAULT_WEIGHTS.copy()
        if "last_correction" not in state:
            state["last_correction"] = None
        if "correction_history" not in state:
            state["correction_history"] = []
        if "prediction_history" not in state:
            state["prediction_history"] = []
        return state

    logger.info("No state found in database, initializing defaults")
    return {
        "signal_weights": DEFAULT_WEIGHTS.copy(),
        "last_correction": None,
        "correction_history": [],
        "prediction_history": [],
    }


def save_state(state: Dict[str, Any]):
    """Persist state to PostgreSQL."""
    save_bot_state(state)
    logger.info("State saved to PostgreSQL")


def get_weights(state: Dict[str, Any] = None) -> Dict[str, float]:
    """Get current signal weights."""
    if state is None:
        state = load_state()
    return state.get("signal_weights", DEFAULT_WEIGHTS).copy()


def update_weights(new_weights: Dict[str, float], state: Dict[str, Any] = None) -> Dict[str, Any]:
    """Update weights and save state."""
    if state is None:
        state = load_state()
    state["signal_weights"] = new_weights
    state["last_correction"] = datetime.utcnow().isoformat()
    save_state(state)
    return state


def add_correction_record(
    hit_count: int,
    best_signal: str,
    worst_signal: str,
    deviation_reason: str,
    adjusted_weights: Dict[str, float],
    state: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Append a self-correction record to history."""
    if state is None:
        state = load_state()
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "hit_count": hit_count,
        "best_signal": best_signal,
        "worst_signal": worst_signal,
        "deviation_reason": deviation_reason,
        "adjusted_weights": adjusted_weights,
    }
    state["correction_history"].append(record)
    # Keep last 100 records
    state["correction_history"] = state["correction_history"][-100:]
    save_state(state)
    return state


def add_prediction_record(
    prediction_id: int,
    predicted_for: str,
    draw_type: str,
    predictions: List[List[int]],
    top_candidates: List[Dict],
    weights_used: Dict[str, float],
    state: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Append a prediction record for diagnostic history."""
    if state is None:
        state = load_state()
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "prediction_id": prediction_id,
        "predicted_for": predicted_for,
        "draw_type": draw_type,
        "predictions": predictions,
        "top_candidates": top_candidates,
        "weights_used": weights_used,
    }
    state["prediction_history"].append(record)
    # Keep last 50 records
    state["prediction_history"] = state["prediction_history"][-50:]
    save_state(state)
    return state


def get_last_n_predictions(n: int = 20, state: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Return last N prediction records for diagnostic use."""
    if state is None:
        state = load_state()
    return state.get("prediction_history", [])[-n:]
