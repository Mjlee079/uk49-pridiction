import os
import logging
from typing import List, Tuple, Dict
from datetime import datetime, date
import json
import re
from src.database import insert_prediction
from src.analytics import get_combined_stats as get_stats
from src.security import get_key, get_key_masked, has_key, mask_sensitive_data
from src.audit import log_api_call
from src.llm_client import get_llm_client, LLM_MODEL

logger = logging.getLogger(__name__)


def build_prediction_prompt(
    stats: Dict,
    num_rows: int = 10,
    cross_stats: Dict = None,
    date_stats: Dict = None,
    target_date: str = None,
) -> str:
    """Build a detailed prompt with analytics for the LLM."""
    if not stats:
        return "No data available. Please provide UK49 lunchtime draw history."

    total = stats.get("total_draws", 0)
    top_15 = stats.get("top_15", [])
    hot = stats.get("hot_numbers", [])
    cold = stats.get("cold_numbers", [])
    gaps = stats.get("gaps", {})
    cooc = stats.get("cooccurrence", {})
    seq = stats.get("sequence", {})

    # Format top 15 with scores
    top_15_str = "\n".join([f"  {n}: {s}%" for n, s in top_15])

    # Format gaps (top 10 overdue numbers)
    sorted_gaps = sorted(gaps.items(), key=lambda x: x[1], reverse=True)[:10]
    gaps_str = "\n".join([f"  #{n}: {g} draws since last seen" for n, g in sorted_gaps])

    # Format co-occurrence
    cooc_str = ""
    if cooc.get("top_pairs"):
        for pair, count in cooc["top_pairs"][:8]:
            cooc_str += f"  {pair[0]} + {pair[1]}: appeared together {count} times\n"

    # Format sequence patterns (top transitions)
    seq_str = ""
    if seq.get("transitions"):
        for num in hot[:5]:
            followers = seq["transitions"].get(num, [])
            if followers:
                follower_str = ", ".join([f"{f}({c}x)" for f, c in followers[:3]])
                seq_str += f"  After {num}, most likely: {follower_str}\n"

    # Cross-draw analysis
    cross_str = ""
    if cross_stats:
        carryover = cross_stats.get("carryover", [])
        if carryover:
            cross_str += "### CROSS-DRAW PATTERNS (Brunchtime -> Lunchtime):\n"
            cross_str += "Numbers that appeared in Brunchtime and likely to carry over:\n"
            for num, count in carryover[:10]:
                cross_str += f"  #{num}: appeared {count} times in Lunchtime after Brunchtime\n"

    # Date-based patterns
    date_str = ""
    if date_stats and target_date:
        from datetime import datetime
        dt = datetime.strptime(target_date, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        day_num = dt.day

        day_favorites = date_stats.get("day_favorites", {})
        date_favorites = date_stats.get("date_favorites", {})

        date_str += f"### DATE PATTERNS (for {day_name} {target_date}):\n"

        if day_name in day_favorites:
            date_str += f"Numbers that frequently appear on {day_name}:\n"
            for num, count in day_favorites[day_name]:
                date_str += f"  #{num}: appeared {count} times\n"

        if day_num in date_favorites:
            date_str += f"Numbers that frequently appear on the {day_num}th of the month:\n"
            for num, count in date_favorites[day_num]:
                date_str += f"  #{num}: appeared {count} times\n"

    prompt = f"""You are an expert lottery data analyst specializing in the UK 49's Lunchtime lottery. You analyze patterns, frequencies, gaps, cross-draw correlations, and date-based trends to predict the most likely numbers.

## IMPORTANT RULES:
1. The lottery draws 6 main numbers + 1 bonus from 1-49.
2. I need exactly {num_rows} rows of the TOP 3 most probable numbers for the NEXT draw.
3. Each row should be DIFFERENT combinations based on different analytical angles.
4. For each row, explain your reasoning briefly.
5. Include a confidence score (0-100%) for each row.
6. Base predictions on ALL data below, including cross-draw patterns and date analysis.
7. Pay special attention to numbers that appeared in Brunchtime as they often carry over to Lunchtime.

## HISTORICAL DATA ANALYSIS ({total} draws analyzed):

### TOP 15 NUMBERS BY COMPOSITE PROBABILITY:
{top_15_str}

### HOT NUMBERS (Most frequent recently):
{', '.join(map(str, hot[:15]))}

### COLD NUMBERS (Least frequent / Overdue):
{', '.join(map(str, cold[:15]))}

### MOST OVERDUE NUMBERS (Gap Analysis):
{gaps_str}

### TOP CO-OCCURRING PAIRS:
{cooc_str}

### SEQUENCE PATTERNS (What follows what):
{seq_str}

{cross_str}

{date_str}

## YOUR TASK:
Provide exactly {num_rows} rows in this format:

Row 1: [N1, N2, N3] | Confidence: X% | Method: [method used] | Reason: [1-sentence reason]
Row 2: [N1, N2, N3] | Confidence: X% | Method: [method used] | Reason: [1-sentence reason]
...and so on.

Each row should use different numbers when possible. Base your analysis on:
- Hot numbers
- Overdue numbers
- Co-occurrence pairs
- Sequence patterns
- Cross-draw patterns (Brunchtime carryover)
- Date-based patterns

The first row should be your highest confidence prediction.

Response format - be concise but analytical:"""

    return prompt


def parse_prediction_response(response_text: str, num_rows: int = 10) -> List[Dict]:
    """Parse LLM response into structured predictions."""
    predictions = []

    # Look for row patterns
    row_pattern = re.compile(
        r'Row\s*(\d+)[\s:]*\[?([\d\s,]+)\]?.*?(?:Confidence|confidence)[\s:]*(\d+)%.*?'
        r'(?:Method|method)[\s:]*([^|]+).*?(?:Reason|reason)[\s:]*(.+)',
        re.IGNORECASE | re.DOTALL
    )

    matches = row_pattern.findall(response_text)

    if matches:
        for match in matches[:num_rows]:
            try:
                numbers_str = match[1]
                numbers = [int(n.strip()) for n in numbers_str.split(",")]
                numbers = [n for n in numbers if 1 <= n <= 49][:3]

                if len(numbers) == 3:
                    predictions.append({
                        "row": int(match[0]),
                        "numbers": numbers,
                        "confidence": int(match[2]),
                        "method": match[3].strip(),
                        "reason": match[4].strip(),
                    })
            except:
                continue

    # Fallback: simple number extraction
    if not predictions:
        all_numbers = re.findall(r'\b(\d{1,2})\b', response_text)
        nums = [int(n) for n in all_numbers if 1 <= int(n) <= 49]

        for i in range(0, len(nums) - 2, 3):
            if i + 2 < len(nums):
                predictions.append({
                    "row": len(predictions) + 1,
                    "numbers": [nums[i], nums[i + 1], nums[i + 2]],
                    "confidence": 50,
                    "method": "Pattern extraction",
                    "reason": "Extracted from AI analysis",
                })

    return predictions[:num_rows]


# =============================================================================
# New Pipeline Delegation (predictor_new.py)
# =============================================================================
# The old monolithic prompt generation below is DEPRECATED.
# All new predictions route through the 5-signal parallel pipeline.
# =============================================================================


def generate_predictions(num_rows: int = 10, user_id: str = None, user_name: str = None) -> Tuple[List[Dict], str]:
    """
    Generate AI predictions via the new 5-signal parallel pipeline.
    Backward-compatible wrapper that returns old-format dicts.
    """
    from src.predictor_new import generate_predictions as _new_generate

    logger.info("Delegating to new prediction pipeline...")
    return _new_generate(
        num_rows=num_rows,
        user_id=user_id,
        user_name=user_name,
    )


def generate_simple_prediction(user_id: str = None, user_name: str = None) -> Tuple[List[int], str, float]:
    """Generate a simple top-3 prediction via new pipeline."""
    from src.predictor_new import generate_simple_prediction as _new_simple

    return _new_simple(
        user_id=user_id,
        user_name=user_name,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    preds, text = generate_predictions(num_rows=5)
    print(json.dumps(preds, indent=2))
