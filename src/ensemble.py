"""UK49s Prediction Bot — Ensemble Orchestrator (Prompt 5)

Feeds all 5 signal scores into the revised ensemble prompt (Prompt 5),
sends to LLM, and parses the 5 rows of 2 numbers.
"""

import logging
import json
import re
from typing import Dict, List, Any, Tuple

from src.prompts import PROMPT_5_ENSEMBLE, SYSTEM_PROMPT
from src.llm_client import get_llm_client, LLM_MODEL

logger = logging.getLogger(__name__)


def _cap_and_redistribute(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Cap any weight at 0.40 and redistribute excess proportionally
    to other signals. Prompt 5 Rule 2.
    """
    cap = 0.40
    total = sum(weights.values())
    if total == 0:
        return weights

    # Identify capped signals
    excess = 0.0
    capped = {}
    uncapped_keys = []
    for k, v in weights.items():
        if v > cap:
            excess += v - cap
            capped[k] = cap
        else:
            capped[k] = v
            uncapped_keys.append(k)

    if excess > 0 and uncapped_keys:
        # Redistribute excess proportionally to uncapped signals
        uncapped_total = sum(capped[k] for k in uncapped_keys)
        if uncapped_total > 0:
            for k in uncapped_keys:
                share = (capped[k] / uncapped_total) * excess
                capped[k] += share
        else:
            # If all uncapped are 0, distribute equally
            for k in uncapped_keys:
                capped[k] = excess / len(uncapped_keys)

    # Normalize to sum to 1.0
    total = sum(capped.values())
    if total > 0:
        capped = {k: round(v / total, 4) for k, v in capped.items()}

    return capped


def run_ensemble(
    frequency_gap_scores: Dict[str, float],
    markov_scores: Dict[str, float],
    cooccurrence_scores: Dict[str, float],
    positional_scores: Dict[str, Dict[str, float]],
    lstm_scores: Dict[str, float],
    weights: Dict[str, float],
) -> Tuple[List[List[int]], List[Dict[str, Any]], str]:
    """
    Run Prompt 5 ensemble via LLM.

    Returns:
        (predictions, top_candidates, raw_response_text)
    """
    logger.info("Running Prompt 5 ensemble via LLM...")

    # Cap and redistribute weights (Rule 2)
    weights = _cap_and_redistribute(weights)
    logger.info("Capped weights: %s", weights)

    # Build prompt using the template
    prompt = PROMPT_5_ENSEMBLE.format(
        frequency_gap_scores=json.dumps(frequency_gap_scores),
        markov_scores=json.dumps(markov_scores),
        cooccurrence_scores=json.dumps(cooccurrence_scores),
        positional_scores=json.dumps(positional_scores),
        lstm_scores=json.dumps(lstm_scores),
        w_freq=weights.get("frequency_gap", 0.25),
        w_markov=weights.get("markov", 0.20),
        w_cooc=weights.get("cooccurrence", 0.20),
        w_pos=weights.get("positional", 0.15),
        w_lstm=weights.get("lstm", 0.20),
    )

    client = get_llm_client()
    if not client:
        logger.error("No LLM client available for ensemble")
        return _fallback_predictions(frequency_gap_scores), [], ""

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
                temperature=0.5,
                max_tokens=2000,
            )
            response_text = response.choices[0].message.content

        logger.info("Received ensemble response")

        predictions, top_candidates = _parse_ensemble_response(response_text)
        
        if not predictions:
            logger.warning("Ensemble returned no valid predictions, using fallback")
            return _fallback_predictions(frequency_gap_scores), [], response_text

        return predictions, top_candidates, response_text

    except Exception as e:
        logger.error("Ensemble LLM call failed: %s", e)
        return _fallback_predictions(frequency_gap_scores), [], ""


def _fallback_predictions(frequency_gap_scores: Dict[str, float]) -> List[List[int]]:
    """Generate prediction rows locally when LLM fails."""
    import random
    
    # Sort by score and take top 10 for 5 rows of 2
    sorted_scores = sorted(frequency_gap_scores.items(), key=lambda x: x[1], reverse=True)
    top_numbers = [int(n) for n, _ in sorted_scores[:10]]
    
    # Ensure we have at least 10 unique numbers
    if len(top_numbers) < 10:
        available = [n for n in range(1, 50) if n not in top_numbers]
        needed = 10 - len(top_numbers)
        top_numbers.extend(random.sample(available, min(needed, len(available))))
    
    predictions = []
    used = set()
    for i in range(5):
        row = []
        candidates = [n for n in top_numbers if n not in used]
        
        if len(candidates) < 2:
            # Reset used pool if running out
            used.clear()
            candidates = [n for n in top_numbers if n not in used]
        
        if len(candidates) >= 2:
            row = random.sample(candidates, 2)
        else:
            # Ultimate fallback: pick any available
            available = [n for n in range(1, 50) if n not in used]
            row = random.sample(available, 2)
        
        predictions.append(sorted(row))
        used.update(row)
    
    return predictions


def _parse_ensemble_response(text: str) -> Tuple[List[List[int]], List[Dict[str, Any]]]:
    """Parse JSON from ensemble response. Expects 5 rows of 2 numbers."""
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            json_str = text[start:end+1]
            data = json.loads(json_str)
            predictions = data.get("predictions", [])
            top_candidates = data.get("top_candidates", [])

            # Validate predictions (expect 5 rows of 2 numbers)
            valid = []
            for row in predictions:
                if isinstance(row, list) and len(row) == 2:
                    nums = [int(n) for n in row if 1 <= int(n) <= 49]
                    if len(nums) == 2 and len(set(nums)) == 2:
                        valid.append(nums)

            if len(valid) != 5:
                logger.warning("Ensemble returned %d valid rows, expected 5", len(valid))

            return valid, top_candidates
    except Exception as e:
        logger.error("Failed to parse ensemble response: %s", e)

    return [], []


def format_telegram_output(predictions: List[List[int]]) -> str:
    """
    Format predictions as clean Telegram message (Prompt 7).
    Returns multi-line string with numbered rows 1-5.
    """
    lines = []
    for i, row in enumerate(predictions[:5], start=1):
        nums = " - ".join(f"{n:02d}" for n in row)
        lines.append(f"{i}. {nums}")
    return "\n".join(lines)
