"""UK49s Prediction Bot — Diagnostic Prompt Runner

Runs the Diagnostic Prompt (Prompt 9) against last 20 draws + predictions
to identify the single biggest flaw before touching weights.
"""

import logging
import json
from typing import Dict, List, Any
from datetime import datetime

from src.prompts import PROMPT_DIAGNOSTIC
from src.state import get_last_n_predictions
from src.database import get_all_draws, get_recent_predictions
from src.llm_client import get_llm_client, LLM_MODEL

logger = logging.getLogger(__name__)


def _format_draws(draws: List[Dict]) -> str:
    """Format draws as JSON list for prompt."""
    history = []
    for d in draws:
        nums = [d[f"ball{i}"] for i in range(1, 7)]
        history.append({
            "date": d.get("draw_date", ""),
            "numbers": nums,
        })
    return json.dumps(history, indent=2)


def _format_predictions(preds: List[Dict]) -> str:
    """Format predictions as JSON list for prompt."""
    out = []
    for p in preds:
        out.append({
            "date": p.get("predicted_for", ""),
            "predicted": p.get("predictions", []),
            "actual": p.get("actual_numbers", []),
        })
    return json.dumps(out, indent=2)


def run_diagnostic(draw_type: str = "LUNCHTIME") -> Dict[str, Any]:
    """
    Run diagnostic prompt against last 20 draws + predictions.
    Returns parsed JSON dict with recommended_weight_start.
    """
    logger.info("Running diagnostic prompt...")

    # Get last 20 actual draws
    draws = get_all_draws(draw_type, limit=20)
    if len(draws) < 20:
        logger.warning("Only %d draws available for diagnostic (need 20)", len(draws))

    # Get last 20 predictions from state
    pred_records = get_last_n_predictions(20)

    # Also get from DB if state doesn't have enough
    if len(pred_records) < 20:
        db_preds = get_recent_predictions(limit=20, draw_type=draw_type)
        # Convert DB format to state format
        for p in db_preds:
            # Skip if already in state
            if any(r.get("prediction_id") == p.get("id") for r in pred_records):
                continue
            pred_records.append({
                "predicted_for": p.get("predicted_for", ""),
                "predictions": [p.get("top_numbers", [])],  # DB only stored top row
                "actual_numbers": p.get("actual_numbers", []),
            })

    last_20_draws = _format_draws(draws)
    last_20_predictions = _format_predictions(pred_records[-20:])

    prompt = PROMPT_DIAGNOSTIC.format(
        last_20_draws=last_20_draws,
        last_20_predictions=last_20_predictions,
    )

    client = get_llm_client()
    if not client:
        logger.error("No LLM client available for diagnostic")
        return _default_diagnostic()

    try:
        if hasattr(client, 'messages_create'):
            response = client.messages_create(
                model=LLM_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
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
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2000,
            )
            response_text = response.choices[0].message.content

        # Parse JSON from response
        return _parse_diagnostic_response(response_text)

    except Exception as e:
        logger.error("Diagnostic LLM call failed: %s", e)
        return _default_diagnostic()


def _parse_diagnostic_response(text: str) -> Dict[str, Any]:
    """Extract JSON from LLM response."""
    try:
        # Try to find JSON block
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            data = json.loads(json_str)
            logger.info("Diagnostic result: avg_hit_rate=%s, biggest_flaw=%s",
                        data.get("avg_hit_rate"), data.get("biggest_flaw"))
            return data
    except Exception as e:
        logger.error("Failed to parse diagnostic response: %s", e)

    return _default_diagnostic()


def _default_diagnostic() -> Dict[str, Any]:
    """Return default diagnostic when LLM fails."""
    return {
        "avg_hit_rate": 0.0,
        "weak_range": "unknown",
        "over_indexing_issue": "diagnostic unavailable",
        "missed_positional_pattern": "diagnostic unavailable",
        "biggest_flaw": "diagnostic unavailable",
        "recommended_weight_start": {
            "frequency_gap": 0.25,
            "markov": 0.20,
            "cooccurrence": 0.20,
            "positional": 0.15,
            "lstm": 0.20,
        }
    }
