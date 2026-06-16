"""UK49s Prediction Bot — Ensemble Orchestrator (Prompt 5)

Feeds all 5 signal scores into the revised ensemble prompt (Prompt 5),
sends to LLM, and parses the 10 rows of 3 numbers.
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
    to other signals.
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


def _compute_ensemble_scores(
    frequency_gap_scores: Dict[str, float],
    markov_scores: Dict[str, float],
    cooccurrence_scores: Dict[str, float],
    positional_scores: Dict[str, Dict[str, float]],
    lstm_scores: Dict[str, float],
    weights: Dict[str, float],
) -> Dict[str, float]:
    """
    Compute weighted ensemble score for each number locally.
    Returns dict: {number_str: score}
    """
    # Cap weights
    weights = _cap_and_redistribute(weights)
    
    # Normalize positional scores to a single score per number
    # Take the maximum probability across all positions
    positional_flat = {}
    for pos, scores in positional_scores.items():
        for num, score in scores.items():
            score_val = float(score)
            if num not in positional_flat or score_val > positional_flat[num]:
                positional_flat[num] = score_val
    
    # Combine all scores
    all_numbers = set(frequency_gap_scores.keys()) | set(markov_scores.keys()) | \
                  set(cooccurrence_scores.keys()) | set(positional_flat.keys()) | \
                  set(lstm_scores.keys())
    
    ensemble = {}
    for num in all_numbers:
        score = (
            weights.get("frequency_gap", 0.25) * frequency_gap_scores.get(num, 0) +
            weights.get("markov", 0.20) * markov_scores.get(num, 0) +
            weights.get("cooccurrence", 0.20) * cooccurrence_scores.get(num, 0) +
            weights.get("positional", 0.15) * positional_flat.get(num, 0) +
            weights.get("lstm", 0.20) * lstm_scores.get(num, 0)
        )
        ensemble[num] = score
    
    return ensemble


def run_ensemble(
    frequency_gap_scores: Dict[str, float],
    markov_scores: Dict[str, float],
    cooccurrence_scores: Dict[str, float],
    positional_scores: Dict[str, Dict[str, float]],
    lstm_scores: Dict[str, float],
    weights: Dict[str, float],
) -> Tuple[List[List[int]], List[Dict[str, Any]], str]:
    """
    Run ensemble scoring locally, then send top 15 to LLM for row generation.

    Returns:
        (predictions, top_candidates, raw_response_text)
    """
    logger.info("Running ensemble (local scoring + LLM row generation)...")

    # Step 1: Compute ensemble scores locally
    ensemble_scores = _compute_ensemble_scores(
        frequency_gap_scores, markov_scores, cooccurrence_scores,
        positional_scores, lstm_scores, weights
    )
    
    # Step 2: Get top 15 candidates
    sorted_candidates = sorted(ensemble_scores.items(), key=lambda x: x[1], reverse=True)
    top_15 = sorted_candidates[:15]
    top_candidates = [{"number": int(n), "score": round(s, 4)} for n, s in top_15]
    
    logger.info("Top 15 candidates: %s", [c["number"] for c in top_candidates])

    # Step 3: Build compact prompt for LLM
    candidates_str = ", ".join([f"{c['number']}({c['score']})" for c in top_candidates])
    
    prompt = f"""You are a UK49s lottery prediction analyst.

Top 15 candidates by ensemble score: {candidates_str}

Generate exactly 5 rows of 2 numbers each. Rules:
1. Numbers must be between 1-49, no duplicates within a row
2. Mix high, medium, and low-scoring candidates for diversity
3. Each row should be different combinations
4. Consider both hot (high score) and due (lower score but overdue) numbers

Return only this JSON:
{{
  "predictions": [ [n1, n2], [n3, n4], [n5, n6], [n7, n8], [n9, n10] ],
  "top_candidates": [ {{ "number": n, "score": 0.XX }} ]
}}
"""

    client = get_llm_client()
    if not client:
        logger.error("No LLM client available for ensemble")
        return [], [], ""

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

        predictions, _ = _parse_ensemble_response(response_text)
        
        # Use our locally computed top_candidates instead of LLM's
        return predictions, top_candidates, response_text

    except Exception as e:
        logger.error("Ensemble LLM call failed: %s", e)
        # Fallback: generate rows from top 15 locally without LLM
        return _fallback_predictions(top_candidates), top_candidates, ""


def _fallback_predictions(top_candidates: List[Dict[str, Any]]) -> List[List[int]]:
    """Generate prediction rows locally when LLM fails."""
    import random
    numbers = [c["number"] for c in top_candidates]
    
    # Ensure we have at least 10 unique numbers for 5 rows of 2
    if len(numbers) < 10:
        available = [n for n in range(1, 50) if n not in numbers]
        numbers.extend(random.sample(available, min(10 - len(numbers), len(available))))
    
    predictions = []
    used = set()
    for i in range(5):
        row = []
        candidates = [n for n in numbers if n not in used]
        if len(candidates) < 2:
            candidates = numbers
        
        row = random.sample(candidates, min(2, len(candidates)))
        if len(row) < 2:
            available = [n for n in range(1, 50) if n not in row]
            row.extend(random.sample(available, 2 - len(row)))
        
        predictions.append(sorted(row))
        used.update(row)
    
    return predictions


def _parse_ensemble_response(text: str) -> Tuple[List[List[int]], List[Dict[str, Any]]]:
    """Parse JSON from ensemble response."""
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
    Returns multi-line string with numbered rows.
    """
    lines = []
    for i, row in enumerate(predictions[:5], start=1):
        nums = " - ".join(f"{n:02d}" for n in row)
        lines.append(f"{i}. {nums}")
    return "\n".join(lines)
