import numpy as np
import pandas as pd
from collections import Counter, defaultdict
from typing import List, Tuple, Dict
from datetime import datetime, timedelta
import logging
from src.database import get_all_draws, get_draws_in_range

logger = logging.getLogger(__name__)


def get_numbers_matrix(draws: List[dict]) -> np.ndarray:
    """Convert draws to a matrix of shape (n_draws, 6)."""
    numbers = []
    for draw in draws:
        nums = [draw[f"ball{i}"] for i in range(1, 7)]
        numbers.append(nums)
    return np.array(numbers)


def frequency_analysis(draws: List[dict], window: int = 30) -> Dict:
    """
    Calculate frequency of each number over the last N draws.
    Returns hot numbers (most frequent) and cold numbers (least frequent).
    """
    if not draws:
        return {"hot": [], "cold": [], "frequencies": {}}

    recent = draws[:window]
    numbers = get_numbers_matrix(recent).flatten()

    freq = Counter(numbers)
    total_draws = len(recent)

    # Fill in missing numbers (0 frequency)
    for i in range(1, 50):
        if i not in freq:
            freq[i] = 0

    # Sort by frequency
    sorted_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)

    hot = [n for n, c in sorted_freq[:10]]
    cold = [n for n, c in sorted_freq[-10:]]

    return {
        "hot": hot,
        "cold": cold,
        "frequencies": dict(freq),
        "total_draws": total_draws,
    }


def gap_analysis(draws: List[dict]) -> Dict[int, int]:
    """
    Calculate how many draws since each number last appeared.
    Lower gap = number appeared recently.
    """
    gaps = {i: float('inf') for i in range(1, 50)}

    for idx, draw in enumerate(draws):
        numbers = [draw[f"ball{i}"] for i in range(1, 7)]
        for num in numbers:
            if gaps[num] == float('inf'):
                gaps[num] = idx

    return gaps


def cooccurrence_matrix(draws: List[dict], top_n: int = 10) -> Dict:
    """
    Find pairs of numbers that appear together most frequently.
    """
    pair_counts = Counter()

    for draw in draws:
        numbers = [draw[f"ball{i}"] for i in range(1, 7)]
        numbers.sort()
        for i in range(len(numbers)):
            for j in range(i + 1, len(numbers)):
                pair = (numbers[i], numbers[j])
                pair_counts[pair] += 1

    top_pairs = pair_counts.most_common(top_n)
    return {"top_pairs": top_pairs, "total_pairs": len(pair_counts)}


def sequence_patterns(draws: List[dict]) -> Dict:
    """
    Analyze sequential patterns: which numbers tend to follow others.
    """
    transitions = defaultdict(Counter)

    # Sort draws by date (oldest first)
    sorted_draws = sorted(draws, key=lambda x: x["draw_date"])

    for i in range(1, len(sorted_draws)):
        prev = [sorted_draws[i - 1][f"ball{j}"] for j in range(1, 7)]
        curr = [sorted_draws[i][f"ball{j}"] for j in range(1, 7)]

        for p in prev:
            for c in curr:
                transitions[p][c] += 1

    # Get top 5 most likely followers for each number
    top_followers = {}
    for num in range(1, 50):
        if num in transitions:
            top = transitions[num].most_common(5)
            top_followers[num] = top
        else:
            top_followers[num] = []

    return {"transitions": dict(top_followers)}


def moving_averages(draws: List[dict], windows: List[int] = [7, 14, 30]) -> Dict:
    """
    Calculate moving average frequency over different windows.
    """
    ma_data = {}

    for window in windows:
        if len(draws) < window:
            continue

        recent = draws[:window]
        numbers = get_numbers_matrix(recent).flatten()
        freq = Counter(numbers)

        avg_freq = len(numbers) / 49  # Expected frequency if uniform

        ma_data[f"ma_{window}"] = {
            "above_avg": [n for n, c in freq.items() if c > avg_freq],
            "below_avg": [n for n, c in freq.items() if c < avg_freq],
            "avg_frequency": avg_freq,
        }

    return ma_data


def calculate_probability_weights(draws: List[dict]) -> Dict[int, float]:
    """
    Calculate weighted probability for each number 1-49.
    Combines multiple factors into a composite score.
    """
    if not draws or len(draws) < 10:
        # Default: uniform probability
        return {i: 100 / 49 for i in range(1, 50)}

    # 1. Frequency weight (40%)
    freq_data = frequency_analysis(draws, window=min(90, len(draws)))
    max_freq = max(freq_data["frequencies"].values()) if freq_data["frequencies"] else 1
    freq_weights = {
        n: (c / max_freq) * 40 if max_freq > 0 else 0
        for n, c in freq_data["frequencies"].items()
    }

    # 2. Gap weight (30%) - numbers that haven't appeared recently get higher weight
    gaps = gap_analysis(draws)
    max_gap = max(gaps.values()) if gaps else 1
    gap_weights = {
        n: (g / max_gap) * 30 if max_gap > 0 else 0
        for n, g in gaps.items()
    }

    # 3. Recency weight (20%) - numbers from last 7 draws
    recent_7 = draws[:7]
    recent_numbers = set(get_numbers_matrix(recent_7).flatten())
    recency_weights = {n: 20 if n in recent_numbers else 0 for n in range(1, 50)}

    # 4. Hot streak weight (10%) - numbers trending up
    ma = moving_averages(draws, windows=[7, 14])
    hot_streak = set()
    if "ma_7" in ma and "ma_14" in ma:
        hot_7 = set(ma["ma_7"]["above_avg"])
        hot_14 = set(ma["ma_14"]["above_avg"])
        hot_streak = hot_7.intersection(hot_14)
    streak_weights = {n: 10 if n in hot_streak else 0 for n in range(1, 50)}

    # Combine all weights
    composite = {}
    for n in range(1, 50):
        composite[n] = freq_weights.get(n, 0) + gap_weights.get(n, 0) + recency_weights.get(n, 0) + streak_weights.get(n, 0)

    # Normalize to 0-100 scale
    max_score = max(composite.values()) if composite else 1
    if max_score > 0:
        composite = {n: round((s / max_score) * 100, 2) for n, s in composite.items()}

    return composite


def get_top_numbers_by_probability(draws: List[dict], top_n: int = 15) -> List[Tuple[int, float]]:
    """Get top N numbers by composite probability score."""
    weights = calculate_probability_weights(draws)
    sorted_numbers = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    return sorted_numbers[:top_n]


def generate_analytics_report(draws: List[dict]) -> str:
    """Generate a human-readable analytics report."""
    if not draws:
        return "No data available for analytics."

    total_draws = len(draws)
    freq = frequency_analysis(draws, window=min(90, total_draws))
    gaps = gap_analysis(draws)
    cooc = cooccurrence_matrix(draws[:100])
    seq = sequence_patterns(draws[:200])
    weights = calculate_probability_weights(draws)
    top_15 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:15]

    report = f"""📊 UK49 Lunchtime Analytics Report
📅 Based on {total_draws} draws

🔥 HOT NUMBERS (Top 10):
{', '.join(map(str, freq['hot']))}

❄️ COLD NUMBERS (Top 10):
{', '.join(map(str, freq['cold']))}

📈 TOP 15 BY PROBABILITY SCORE:
"""
    for num, score in top_15:
        report += f"  #{num}: {score}%\n"

    report += f"\n🔗 TOP CO-OCCURRING PAIRS:\n"
    for pair, count in cooc["top_pairs"][:5]:
        report += f"  {pair[0]} + {pair[1]}: {count} times\n"

    return report


def get_combined_stats(draw_type: str = "LUNCHTIME") -> Dict:
    """Get all combined statistics for predictions."""
    draws = get_all_draws(draw_type)

    if not draws:
        return {}

    total = len(draws)
    weights = calculate_probability_weights(draws)
    top_15 = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:15]
    freq = frequency_analysis(draws, window=min(90, total))
    gaps = gap_analysis(draws)
    cooc = cooccurrence_matrix(draws[:100])
    seq = sequence_patterns(draws[:200])
    ma = moving_averages(draws)

    return {
        "total_draws": total,
        "top_15": top_15,
        "hot_numbers": freq["hot"],
        "cold_numbers": freq["cold"],
        "frequencies": freq["frequencies"],
        "gaps": gaps,
        "cooccurrence": cooc,
        "sequence": seq,
        "moving_averages": ma,
        "weights": weights,
    }


def cross_draw_analysis(
    source_draws: List[dict],
    target_draws: List[dict],
    lookback: int = 30
) -> Dict:
    """
    Analyze patterns from one draw type to another.
    e.g., Brunchtime -> Lunchtime
    Returns numbers that appeared in source and likelihood in target.
    """
    if not source_draws or not target_draws:
        return {"carryover": [], "hot_cross": [], "cold_cross": []}

    # Get recent source draws
    recent_source = source_draws[:lookback]
    recent_target = target_draws[:lookback]

    # Extract all numbers from source
    source_numbers = set()
    for draw in recent_source:
        nums = [draw[f"ball{i}"] for i in range(1, 7)]
        source_numbers.update(nums)

    # Check which source numbers appeared in target
    target_numbers = []
    for draw in recent_target:
        nums = [draw[f"ball{i}"] for i in range(1, 7)]
        target_numbers.extend(nums)

    target_freq = Counter(target_numbers)

    # Find carryover numbers (appeared in source AND likely in target)
    carryover = []
    for num in source_numbers:
        if target_freq[num] > 0:
            carryover.append((num, target_freq[num]))

    # Sort by frequency in target
    carryover = sorted(carryover, key=lambda x: x[1], reverse=True)

    # Find hot cross numbers (high frequency in both)
    hot_cross = []
    cold_cross = []
    for num in range(1, 50):
        tf = target_freq.get(num, 0)
        if tf >= 3:
            hot_cross.append((num, tf))
        elif tf == 0:
            cold_cross.append(num)

    return {
        "carryover": carryover[:10],
        "hot_cross": hot_cross[:10],
        "cold_cross": cold_cross[:10],
        "source_numbers": list(source_numbers),
    }


def date_pattern_analysis(draws: List[dict]) -> Dict:
    """
    Analyze which numbers appear on specific dates/days.
    """
    if not draws:
        return {}

    # Day of week patterns
    day_patterns = defaultdict(list)
    date_patterns = defaultdict(list)

    for draw in draws:
        date = draw["draw_date"]
        dt = datetime.strptime(date, "%Y-%m-%d")
        day_name = dt.strftime("%A")
        day_num = dt.day
        month = dt.month

        numbers = [draw[f"ball{i}"] for i in range(1, 7)]

        # Track by day of week
        day_patterns[day_name].extend(numbers)

        # Track by date of month
        date_patterns[day_num].extend(numbers)

    # Find most frequent numbers by day
    day_favorites = {}
    for day, nums in day_patterns.items():
        freq = Counter(nums)
        top = freq.most_common(5)
        day_favorites[day] = top

    # Find most frequent numbers by date
    date_favorites = {}
    for date_num, nums in date_patterns.items():
        if len(nums) > 3:  # Only if we have enough data
            freq = Counter(nums)
            top = freq.most_common(3)
            date_favorites[date_num] = top

    return {
        "day_favorites": day_favorites,
        "date_favorites": date_favorites,
    }


def get_cross_draw_stats() -> Dict:
    """Get combined stats including cross-draw analysis."""
    from src.database import get_all_draws

    brunchtime = get_all_draws("BRUNCHTIME")
    lunchtime = get_all_draws("LUNCHTIME")

    stats = {}

    if brunchtime and lunchtime:
        stats["cross_draw"] = cross_draw_analysis(brunchtime, lunchtime)
        stats["brunchtime_count"] = len(brunchtime)
        stats["lunchtime_count"] = len(lunchtime)

    if lunchtime:
        stats["date_patterns"] = date_pattern_analysis(lunchtime)

    return stats
