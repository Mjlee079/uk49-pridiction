import logging
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, date, timedelta
from src.database import (
    get_recent_predictions,
    get_accuracy_stats,
    update_accuracy,
    get_latest_draw,
    get_all_draws,
    update_prediction_result,
)
from src.state import load_state, update_weights, add_correction_record
from src.prompts import PROMPT_6_SELF_CORRECTION
from src.llm_client import get_llm_client, LLM_MODEL

logger = logging.getLogger(__name__)


def get_learning_context() -> str:
    """
    Get accuracy history as context for the AI to learn from past predictions.
    This feeds back into the prediction system.
    """
    stats = get_accuracy_stats()
    recent = get_recent_predictions(limit=20)

    if not stats or stats.get("total_predictions", 0) == 0:
        return "No prediction history yet. This is the first prediction."

    total = stats.get("total_predictions", 0)
    avg_matches = stats.get("avg_matches", 0) or 0
    avg_accuracy = stats.get("avg_accuracy", 0) or 0
    at_least_1 = stats.get("at_least_1_match", 0)
    at_least_2 = stats.get("at_least_2_matches", 0)
    all_3 = stats.get("all_3_matches", 0)

    context = f"""## PAST PREDICTION PERFORMANCE (Learning Data):
- Total predictions evaluated: {total}
- Average matches per prediction: {avg_matches:.1f}/3
- Average accuracy score: {avg_accuracy:.1f}%
- Predictions with at least 1 match: {at_least_1} ({(at_least_1/total*100) if total else 0:.1f}%)
- Predictions with at least 2 matches: {at_least_2} ({(at_least_2/total*100) if total else 0:.1f}%)
- Predictions with all 3 matches: {all_3} ({(all_3/total*100) if total else 0:.1f}%)

## RECENT PREDICTIONS:
"""

    for pred in recent[:10]:
        nums = pred.get("top_numbers", [])
        actual = pred.get("actual_numbers", "N/A")
        matches = pred.get("matches_count", "N/A")

        context += f"- Predicted {nums} | Actual: {actual} | Matches: {matches}\n"

    if all_3 > 0:
        context += "\n## SUCCESS NOTE:\n"
        context += f"The bot has successfully predicted all 3 numbers correctly {all_3} times. "
        context += "Continue using the methods that led to these successes.\n"

    return context


def check_and_update_accuracy():
    """
    Check the latest draw against the most recent prediction and update accuracy.
    This should be called after a new draw result is fetched.
    """
    recent = get_recent_predictions(limit=5)
    latest_draw = get_latest_draw()

    if not recent or not latest_draw:
        logger.info("No predictions or draws to compare")
        return

    latest_date = latest_draw.get("draw_date")
    actual_numbers = [
        latest_draw[f"ball{i}"] for i in range(1, 7)
    ]

    updated = 0
    for pred in recent:
        pred_for = pred.get("predicted_for")
        if pred_for == latest_date and pred.get("matches_count") is None:
            prediction_id = pred.get("id")
            update_accuracy(prediction_id, actual_numbers)
            updated += 1

    if updated > 0:
        logger.info(f"Updated accuracy for {updated} predictions")
    else:
        logger.info("No pending accuracy updates")


def get_performance_summary() -> str:
    """Generate a human-readable performance summary."""
    stats = get_accuracy_stats()

    if not stats or stats.get("total_predictions", 0) == 0:
        return "📊 No prediction history yet. Make some predictions first!"

    total = stats.get("total_predictions", 0)
    avg_matches = stats.get("avg_matches", 0) or 0
    at_least_1 = stats.get("at_least_1_match", 0)
    at_least_2 = stats.get("at_least_2_matches", 0)
    all_3 = stats.get("all_3_matches", 0)

    summary = f"""📊 UK49 Lunchtime Bot Performance

🎯 Total Predictions Evaluated: {total}

✅ Accuracy Breakdown:
  • All 3 correct: {all_3} ({(all_3/total*100):.1f}%)
  • At least 2 correct: {at_least_2} ({(at_least_2/total*100):.1f}%)
  • At least 1 correct: {at_least_1} ({(at_least_1/total*100):.1f}%)
  • Average matches: {avg_matches:.1f}/3

🧠 Learning Status:
  • Bot is actively learning from each draw
  • Methods are adjusted based on historical accuracy
  • Recent trends influence future predictions
"""

    return summary


def format_prediction_history(limit: int = 5) -> str:
    """Format recent predictions for display."""
    predictions = get_recent_predictions(limit=limit)

    if not predictions:
        return "No predictions made yet."

    text = f"📋 Last {len(predictions)} Predictions:\n\n"

    for pred in predictions:
        nums = pred.get("top_numbers", [])
        actual = pred.get("actual_numbers", "Pending")
        matches = pred.get("matches_count")
        date = pred.get("predicted_for", "Unknown")

        status = "⏳ Pending" if matches is None else f"✅ {matches}/3 correct"

        text += f"📅 {date}\n"
        text += f"   Predicted: {nums}\n"
        text += f"   Actual: {actual}\n"
        text += f"   Status: {status}\n\n"

    return text


def get_trending_methods() -> List[str]:
    """Analyze which prediction methods have been most successful."""
    recent = get_recent_predictions(limit=50)
    method_success = {}

    for pred in recent:
        method = pred.get("method_used", "Unknown")
        matches = pred.get("matches_count", 0)

        if method not in method_success:
            method_success[method] = {"total": 0, "matches": 0}

        method_success[method]["total"] += 1
        method_success[method]["matches"] += matches or 0

    # Sort by average matches per prediction
    sorted_methods = sorted(
        method_success.items(),
        key=lambda x: x[1]["matches"] / max(x[1]["total"], 1),
        reverse=True,
    )

    return [method for method, _ in sorted_methods[:5]]


def _get_top_20_dict(scores: Dict[str, float]) -> Dict[str, float]:
    """Filter scores to top 20 candidates."""
    if not scores:
        return scores
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:20]
    return dict(sorted_scores)


# =============================================================================
# Self-Correction (Prompt 6) — Run after every real draw
# =============================================================================
def self_correct(draw_type: str = "LUNCHTIME"):
    """
    Run Prompt 6 after each real draw result.
    Compares most recent prediction with actual draw, then adjusts weights.
    """
    logger.info("Running self-correction (Prompt 6)...")

    latest_draw = get_latest_draw(draw_type)
    if not latest_draw:
        logger.info("No latest draw available for self-correction")
        return

    actual_numbers = [latest_draw[f"ball{i}"] for i in range(1, 7)]
    actual_date = latest_draw.get("draw_date")

    # Get most recent prediction for this draw date
    recent_preds = get_recent_predictions(limit=5, draw_type=draw_type)
    target_pred = None
    for pred in recent_preds:
        if pred.get("predicted_for") == actual_date and pred.get("matches_count") is not None:
            target_pred = pred
            break

    if not target_pred:
        logger.info("No evaluated prediction found for self-correction on %s", actual_date)
        return

    # Update draw_result on prediction row
    update_prediction_result(target_pred["id"], actual_numbers)

    # Extract signal scores from prediction record
    signal_scores = target_pred.get("signal_scores", {})
    weights_used = target_pred.get("weights_used", {})
    all_rows = target_pred.get("all_rows", [])

    # If signal_scores not stored in DB, skip LLM correction and use heuristic
    if not signal_scores or not weights_used:
        logger.warning("Missing signal_scores or weights_used for self-correction, using heuristic")
        _heuristic_weight_adjustment(target_pred, actual_numbers)
        return

    # Build Prompt 6
    predicted_numbers = json.dumps(all_rows) if all_rows else json.dumps([target_pred.get("top_numbers", [])])
    actual_draw = json.dumps(actual_numbers)

    # Filter scores to top 20 to reduce prompt size
    freq_scores = json.dumps(_get_top_20_dict(signal_scores.get("frequency_gap", {})))
    markov_scores = json.dumps(_get_top_20_dict(signal_scores.get("markov", {})))
    cooc_scores = json.dumps(_get_top_20_dict(signal_scores.get("cooccurrence", {})))
    # Positional is nested dict, filter each position
    pos_raw = signal_scores.get("positional", {})
    pos_filtered = {}
    for pos, scores in pos_raw.items():
        if isinstance(scores, dict):
            sorted_scores = sorted(scores.items(), key=lambda x: float(x[1]), reverse=True)[:20]
            pos_filtered[pos] = dict(sorted_scores)
    pos_scores = json.dumps(pos_filtered)
    lstm_scores = json.dumps(_get_top_20_dict(signal_scores.get("lstm", {})))
    current_weights = json.dumps(weights_used)

    prompt = PROMPT_6_SELF_CORRECTION.format(
        predicted_numbers=predicted_numbers,
        actual_draw=actual_draw,
        frequency_gap_scores=freq_scores,
        markov_scores=markov_scores,
        cooccurrence_scores=cooc_scores,
        positional_scores=pos_scores,
        lstm_scores=lstm_scores,
        current_weights=current_weights,
    )

    client = get_llm_client()
    if not client:
        logger.error("No LLM client for self-correction")
        return

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

        # Parse JSON
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1:
            data = json.loads(response_text[start:end+1])
            adjusted_weights = data.get("adjusted_weights", {})
            hit_count = data.get("hit_count", 0)
            best_signal = data.get("best_signal_this_draw", "unknown")
            worst_signal = data.get("worst_signal_this_draw", "unknown")
            deviation = data.get("deviation_reason", "")

            # Apply conservative cap: max shift of 0.05 per signal
            state = load_state()
            old_weights = state.get("signal_weights", {})
            new_weights = {}
            for key in ["frequency_gap", "markov", "cooccurrence", "positional", "lstm"]:
                old = old_weights.get(key, 0.20)
                new = adjusted_weights.get(key, old)
                diff = new - old
                if abs(diff) > 0.05:
                    diff = 0.05 if diff > 0 else -0.05
                    new = old + diff
                new_weights[key] = round(max(0.05, min(0.95, new)), 4)

            # Normalize to sum to 1.0
            total = sum(new_weights.values())
            if total > 0:
                new_weights = {k: round(v / total, 4) for k, v in new_weights.items()}

            update_weights(new_weights, state)
            add_correction_record(
                hit_count=hit_count,
                best_signal=best_signal,
                worst_signal=worst_signal,
                deviation_reason=deviation,
                adjusted_weights=new_weights,
                state=state,
            )

            logger.info("Self-correction complete: hit_count=%d, best=%s, worst=%s, new_weights=%s",
                        hit_count, best_signal, worst_signal, new_weights)
        else:
            logger.error("Self-correction response contained no JSON")

    except Exception as e:
        logger.error("Self-correction failed: %s", e)


def _heuristic_weight_adjustment(pred: Dict[str, Any], actual_numbers: List[int]):
    """Fallback weight adjustment when LLM self-correction is unavailable."""
    state = load_state()
    weights = state.get("signal_weights", {}).copy()
    predicted = set(pred.get("top_numbers", []))
    actual = set(actual_numbers)
    matches = len(predicted & actual)

    if matches >= 2:
        # Good prediction — slight boost to all weights (small random drift)
        weights = {k: v * 1.02 for k, v in weights.items()}
    elif matches == 0:
        # Bad prediction — slight nudge
        weights = {k: v * 0.98 for k, v in weights.items()}

    # Normalize
    total = sum(weights.values())
    if total > 0:
        weights = {k: round(v / total, 4) for k, v in weights.items()}

    update_weights(weights, state)
    logger.info("Heuristic weight adjustment applied: matches=%d, weights=%s", matches, weights)
