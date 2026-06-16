"""UK49s Prediction Bot — Main Orchestrator

This module replaces the monolithic prediction pipeline with the full
5-signal parallel architecture:

1. Run Diagnostic (optional)
2. Run Signals in Parallel (4 local + 1 LLM)
3. Run Ensemble (LLM)
4. Format for Telegram
5. Save to Database + State

Usage:
    from src.predictor_new import generate_predictions_pipeline
    predictions, telegram_text, reasoning = generate_predictions_pipeline(draw_type="LUNCHTIME")
"""

import os
import logging
import json
import asyncio
from typing import List, Dict, Tuple, Any
from datetime import date, datetime

from src.database import get_all_draws, insert_prediction
from src.state import (
    load_state,
    save_state,
    get_weights,
    add_prediction_record,
)
from src.signals import run_all_local_signals
from src.ensemble import run_ensemble, format_telegram_output
from src.prompts import PROMPT_8_LSTM, SYSTEM_PROMPT
from src.llm_client import get_llm_client, LLM_MODEL
from src.analytics import get_combined_stats

logger = logging.getLogger(__name__)


def _format_draw_history(draws: List[Dict], compact: bool = False) -> str:
    """Format draws as list of lists for prompts."""
    history = []
    for d in draws:
        nums = [d[f"ball{i}"] for i in range(1, 7)]
        history.append(nums)
    return json.dumps(history, separators=(',', ':') if compact else None)


def _get_last_draw(draws: List[Dict]) -> str:
    """Get most recent draw as JSON string."""
    if not draws:
        return "[]"
    nums = [draws[0][f"ball{i}"] for i in range(1, 7)]
    return json.dumps(nums)


def _get_last_10_draws(draws: List[Dict]) -> str:
    """Get last 10 draws as compact JSON string."""
    history = []
    for d in draws[:10]:
        nums = [d[f"ball{i}"] for i in range(1, 7)]
        history.append(nums)
    return json.dumps(history, separators=(',', ':'))


# =============================================================================
# LSTM Signal — LLM Call (Prompt 8)
# =============================================================================
def run_lstm_signal(draws: List[Dict]) -> Dict[str, Any]:
    """
    Run Prompt 8 via LLM. Returns dict with:
    { "lstm_scores": {...}, "trending_up": [...], "trending_down": [...], "cluster_numbers": [...] }
    """
    logger.info("Running LSTM signal (Prompt 8) via LLM...")

    if not draws:
        return {
            "lstm_scores": {str(i): 0.5 for i in range(1, 50)},
            "trending_up": [],
            "trending_down": [],
            "cluster_numbers": [],
        }

    # Only send last 50 draws for LSTM to keep prompt size manageable (compact JSON)
    draw_history = _format_draw_history(draws[:50], compact=True)
    last_10_draws = _get_last_10_draws(draws)

    prompt = PROMPT_8_LSTM.format(
        draw_history=draw_history,
        last_10_draws=last_10_draws,
    )

    client = get_llm_client()
    if not client:
        logger.error("No LLM client for LSTM signal")
        return {
            "lstm_scores": {str(i): 0.5 for i in range(1, 50)},
            "trending_up": [],
            "trending_down": [],
            "cluster_numbers": [],
        }

    try:
        if hasattr(client, 'messages_create'):
            response = client.messages_create(
                model=LLM_MODEL,
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            text_content = None
            for content in response.get('content', []):
                if content.get('type') == 'text':
                    text_content = content.get('text', '')
                    break
            response_text = text_content or ''
        else:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,
                max_tokens=2000,
            )
            response_text = response.choices[0].message.content

        # Parse JSON
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1:
            data = json.loads(response_text[start:end+1])
            logger.info("LSTM signal received: trending_up=%s, trending_down=%s",
                        data.get("trending_up"), data.get("trending_down"))
            return data

    except Exception as e:
        logger.error("LSTM signal failed: %s", e)

    return {
        "lstm_scores": {str(i): 0.5 for i in range(1, 50)},
        "trending_up": [],
        "trending_down": [],
        "cluster_numbers": [],
    }


def _get_top_20(scores: Dict[str, float]) -> Dict[str, float]:
    """Filter scores to top 20 candidates."""
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]
    return dict(sorted_scores)


def _get_top_20_positional(positional_scores: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    """Filter positional scores to top 20 per position."""
    result = {}
    for pos, scores in positional_scores.items():
        sorted_scores = sorted(scores.items(), key=lambda x: float(x[1]), reverse=True)[:20]
        result[pos] = dict(sorted_scores)
    return result


# =============================================================================
# Main Pipeline
# =============================================================================
def generate_predictions_pipeline(
    draw_type: str = "LUNCHTIME",
    user_id: str = None,
    user_name: str = None,
) -> Tuple[List[List[int]], str, str, Dict[str, Any]]:
    """
    Full prediction pipeline.

    Returns:
        (predictions_list, telegram_text, reasoning_text, metadata_dict)
    """
    logger.info("=" * 50)
    logger.info("Starting prediction pipeline for %s", draw_type)
    logger.info("=" * 50)

    # Load state
    state = load_state()
    weights = get_weights(state)

    # Get draw history
    draws = get_all_draws(draw_type, limit=200)
    if not draws:
        logger.error("No draw data available")
        return [], "No data available.", "", {}

    logger.info("Loaded %d draws for analysis", len(draws))

    # Step 1: Run local signals (1-4) synchronously
    local_signals = run_all_local_signals(draws)
    logger.info("Local signals complete")

    # Step 2: Run LSTM signal (Prompt 8) via LLM
    lstm_data = run_lstm_signal(draws)
    lstm_scores = lstm_data.get("lstm_scores", {})

    # Step 3: Run Ensemble (Prompt 5) via LLM
    # Filter to top 20 per signal to reduce prompt size
    predictions, top_candidates, ensemble_text = run_ensemble(
        frequency_gap_scores=_get_top_20(local_signals["frequency_gap"]),
        markov_scores=_get_top_20(local_signals["markov"]),
        cooccurrence_scores=_get_top_20(local_signals["cooccurrence"]),
        positional_scores=_get_top_20_positional(local_signals["positional"]),
        lstm_scores=_get_top_20(lstm_scores),
        weights=weights,
    )

    if not predictions:
        logger.error("Ensemble failed to produce predictions")
        return [], "Failed to generate predictions.", "", {}

    logger.info("Ensemble produced %d prediction rows", len(predictions))

    # Step 4: Format for Telegram (Prompt 7)
    telegram_text = format_telegram_output(predictions)

    # Step 5: Save to database
    today = date.today().isoformat()
    all_numbers = [n for row in predictions for n in row]
    all_confidences = [50] * len(predictions)  # Placeholder; ensemble doesn't output per-row confidence
    method_used = "ensemble_v2"

    prediction_id = insert_prediction(
        predicted_for=today,
        top_numbers=all_numbers[:2],  # First row as primary (2 numbers)
        confidence_scores=all_confidences,
        reasoning=ensemble_text[:2000],
        method_used=method_used,
        draw_type=draw_type,
    )

    # Save full prediction to state
    add_prediction_record(
        prediction_id=prediction_id,
        predicted_for=today,
        draw_type=draw_type,
        predictions=predictions,
        top_candidates=top_candidates,
        weights_used=weights,
        state=state,
    )

    # Build metadata
    metadata = {
        "prediction_id": prediction_id,
        "weights_used": weights,
        "signal_scores": {
            "frequency_gap": local_signals["frequency_gap"],
            "markov": local_signals["markov"],
            "cooccurrence": local_signals["cooccurrence"],
            "positional": local_signals["positional"],
            "lstm": lstm_scores,
        },
        "lstm_trending_up": lstm_data.get("trending_up", []),
        "lstm_trending_down": lstm_data.get("trending_down", []),
        "lstm_cluster_numbers": lstm_data.get("cluster_numbers", []),
    }

    logger.info("Prediction pipeline complete. ID=%d", prediction_id)
    return predictions, telegram_text, ensemble_text, metadata


# =============================================================================
# Simple wrapper for backward compatibility
# =============================================================================
def generate_predictions(
    num_rows: int = 10,
    user_id: str = None,
    user_name: str = None,
    draw_type: str = "LUNCHTIME",
) -> Tuple[List[Dict], str]:
    """
    Backward-compatible wrapper that returns the old format:
    List of dicts with "row", "numbers", "confidence", "method", "reason"
    """
    predictions, telegram_text, reasoning, metadata = generate_predictions_pipeline(
        draw_type=draw_type,
        user_id=user_id,
        user_name=user_name,
    )

    # Convert to old format
    old_format = []
    for i, row in enumerate(predictions[:num_rows], start=1):
        old_format.append({
            "row": i,
            "numbers": row,
            "confidence": 50,  # Ensemble doesn't give per-row confidence
            "method": "ensemble_v2",
            "reason": f"Row {i} from ensemble scoring",
        })

    return old_format, reasoning


def generate_simple_prediction(user_id: str = None, user_name: str = None, draw_type: str = "LUNCHTIME") -> Tuple[List[int], str, float]:
    """Generate a simple top-3 prediction (backward compatible)."""
    predictions, text, _, _ = generate_predictions_pipeline(
        draw_type=draw_type,
        user_id=user_id,
        user_name=user_name,
    )
    if predictions:
        return predictions[0], "Top ensemble prediction", 50.0
    return [], "No prediction available", 0.0
