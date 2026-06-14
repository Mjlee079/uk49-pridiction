"""UK49s Prediction Bot — Local Signal Engines (Prompts 1-4)

Computes Frequency/Gap, Markov Chain, Co-occurrence, and Positional signals
entirely in Python without LLM calls. Returns JSON-compatible dicts that match
the exact output format required by the Prompt Suite.
"""

import logging
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Any
import numpy as np

logger = logging.getLogger(__name__)


def _extract_numbers(draw: Dict) -> List[int]:
    """Extract 6 main numbers from a draw dict."""
    return [draw[f"ball{i}"] for i in range(1, 7)]


def _extract_history(draws: List[Dict]) -> List[List[int]]:
    """Convert list of draw dicts to list of number lists."""
    return [_extract_numbers(d) for d in draws]


# =============================================================================
# Prompt 1 — Frequency & Gap Analysis
# =============================================================================
def frequency_gap_signal(draws: List[Dict], window: int = 200) -> Dict[str, float]:
    """
    Compute combined hot/due score for all 49 numbers.
    Returns: { "number": score } where score is 0.0-1.0
    """
    if not draws:
        return {str(i): 0.5 for i in range(1, 50)}

    recent = draws[:window]
    history = _extract_history(recent)
    flat = [n for draw in history for n in draw]

    # 1. Frequency in window
    freq = Counter(flat)
    for i in range(1, 50):
        if i not in freq:
            freq[i] = 0
    max_freq = max(freq.values()) if freq else 1
    freq_scores = {n: (c / max_freq) if max_freq > 0 else 0.0 for n, c in freq.items()}

    # 2. Gap analysis (draws since last appearance)
    gaps = {i: float('inf') for i in range(1, 50)}
    for idx, draw in enumerate(history):
        for num in draw:
            if gaps[num] == float('inf'):
                gaps[num] = idx
    # Cap infinity at window size for normalization
    max_gap = max((g for g in gaps.values() if g != float('inf')), default=1)
    for i in range(1, 50):
        if gaps[i] == float('inf'):
            gaps[i] = max_gap + 10  # penalize slightly for never appearing
    max_gap = max(gaps.values()) if gaps else 1
    gap_scores = {n: (g / max_gap) if max_gap > 0 else 0.0 for n, g in gaps.items()}

    # 3. Combined score: 60% frequency, 40% gap
    # Higher gap = more overdue = higher score
    combined = {}
    for n in range(1, 50):
        f_score = freq_scores.get(n, 0.0)
        g_score = gap_scores.get(n, 0.0)
        # Normalize: frequency is already 0-1, gap is 0-1
        # We want hot numbers (high freq) AND due numbers (high gap)
        # Use harmonic mean style blend
        combined[n] = round(0.6 * f_score + 0.4 * g_score, 4)

    # Normalize to 0-1
    max_c = max(combined.values()) if combined else 1.0
    if max_c > 0:
        combined = {k: round(v / max_c, 4) for k, v in combined.items()}

    return {str(k): v for k, v in combined.items()}


# =============================================================================
# Prompt 2 — Markov Chain / Sequence Pattern
# =============================================================================
def markov_signal(draws: List[Dict]) -> Dict[str, float]:
    """
    Compute transition-based probability scores for all 49 numbers.
    Returns: { "number": probability_score } where score is 0.0-1.0
    """
    if not draws or len(draws) < 2:
        return {str(i): 0.5 for i in range(1, 50)}

    history = _extract_history(draws)
    # Sort by date (oldest first) — draws already come DESC from DB, so reverse
    history = list(reversed(history))

    last_draw = history[-1]
    last_set = set(last_draw)

    # Build transition counts
    transitions = defaultdict(Counter)
    for i in range(1, len(history)):
        prev = history[i - 1]
        curr = history[i]
        for p in prev:
            for c in curr:
                transitions[p][c] += 1

    # 2-draw and 3-draw sequences
    seq2 = defaultdict(Counter)
    seq3 = defaultdict(Counter)
    for i in range(2, len(history)):
        prev2 = tuple(sorted(history[i - 2]))
        prev1 = tuple(sorted(history[i - 1]))
        curr = history[i]
        for c in curr:
            seq2[prev1][c] += 1
            seq3[(prev2, prev1)][c] += 1

    # Score each number
    scores = {}
    for num in range(1, 50):
        score = 0.0

        # 1. Direct transitions from last draw numbers
        for p in last_set:
            if num in transitions[p]:
                total = sum(transitions[p].values())
                score += (transitions[p][num] / total) if total > 0 else 0

        # 2. 2-draw sequence
        last_sorted = tuple(sorted(last_draw))
        if num in seq2[last_sorted]:
            total2 = sum(seq2[last_sorted].values())
            score += 0.5 * (seq2[last_sorted][num] / total2) if total2 > 0 else 0

        # 3. 3-draw sequence
        if len(history) >= 3:
            prev2_sorted = tuple(sorted(history[-2]))
            key3 = (prev2_sorted, last_sorted)
            if num in seq3[key3]:
                total3 = sum(seq3[key3].values())
                score += 0.3 * (seq3[key3][num] / total3) if total3 > 0 else 0

        scores[num] = score

    # Normalize to 0-1
    max_s = max(scores.values()) if scores else 1.0
    if max_s > 0:
        scores = {k: round(v / max_s, 4) for k, v in scores.items()}
    else:
        scores = {k: 0.5 for k in scores}

    return {str(k): v for k, v in scores.items()}


# =============================================================================
# Prompt 3 — Co-occurrence & Correlation
# =============================================================================
def cooccurrence_signal(draws: List[Dict]) -> Dict[str, float]:
    """
    Compute co-occurrence affinity scores for all 49 numbers.
    Returns: { "number": affinity_score } where score is 0.0-1.0
    """
    if not draws:
        return {str(i): 0.5 for i in range(1, 50)}

    history = _extract_history(draws)
    last_draw = history[0] if history else []
    last_set = set(last_draw)

    # Pair counts
    pair_counts = Counter()
    triplet_counts = Counter()

    for draw in history:
        nums = sorted(draw)
        # Pairs
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair_counts[(nums[i], nums[j])] += 1
        # Triplets
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                for k in range(j + 1, len(nums)):
                    triplet_counts[(nums[i], nums[j], nums[k])] += 1

    # Score each number based on its affinity with last draw numbers
    scores = {}
    for num in range(1, 50):
        score = 0.0

        if num in last_set:
            # Number already appeared in last draw — check its partners
            for partner in last_set:
                if partner != num:
                    pair = tuple(sorted([num, partner]))
                    score += pair_counts.get(pair, 0)
        else:
            # Number not in last draw — check its historical affinity with last draw numbers
            for last_num in last_set:
                pair = tuple(sorted([num, last_num]))
                score += pair_counts.get(pair, 0) * 0.5

        # Triplet boost
        for t, count in triplet_counts.items():
            if num in t:
                last_overlap = len(set(t) & last_set)
                if last_overlap >= 2:
                    score += count * 0.3

        scores[num] = score

    # Normalize to 0-1
    max_s = max(scores.values()) if scores else 1.0
    if max_s > 0:
        scores = {k: round(v / max_s, 4) for k, v in scores.items()}
    else:
        scores = {k: 0.5 for k in scores}

    return {str(k): v for k, v in scores.items()}


# =============================================================================
# Prompt 4 — Positional Probability
# =============================================================================
def positional_signal(draws: List[Dict]) -> Dict[str, Dict[str, float]]:
    """
    Compute positional probability for each number across 6 positions.
    Returns: { "position_1": { "number": probability }, ... }
    """
    if not draws:
        return {
            f"position_{p}": {str(i): 1/49 for i in range(1, 50)}
            for p in range(1, 7)
        }

    history = _extract_history(draws)
    # Sort each draw ascending to map positions
    sorted_history = [sorted(draw) for draw in history]

    positional_counts = {p: Counter() for p in range(1, 7)}

    for draw in sorted_history:
        for pos, num in enumerate(draw, start=1):
            positional_counts[pos][num] += 1

    # Fill missing numbers with 0
    for p in range(1, 7):
        for i in range(1, 50):
            if i not in positional_counts[p]:
                positional_counts[p][i] = 0

    # Convert to probabilities with Laplace smoothing
    result = {}
    for p in range(1, 7):
        counts = positional_counts[p]
        total = sum(counts.values())
        n_numbers = 49
        # Laplace smoothing: (count + 1) / (total + n_numbers)
        probs = {}
        for num in range(1, 50):
            probs[str(num)] = round((counts.get(num, 0) + 1) / (total + n_numbers), 6)
        result[f"position_{p}"] = probs

    return result


# =============================================================================
# Convenience: Run all 4 local signals at once
# =============================================================================
def run_all_local_signals(draws: List[Dict]) -> Dict[str, Any]:
    """Run all 4 local signal engines and return combined dict."""
    logger.info("Running local signals (frequency/gap, markov, cooccurrence, positional)...")
    return {
        "frequency_gap": frequency_gap_signal(draws),
        "markov": markov_signal(draws),
        "cooccurrence": cooccurrence_signal(draws),
        "positional": positional_signal(draws),
    }
