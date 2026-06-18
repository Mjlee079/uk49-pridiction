"""UK49s Prediction Bot — All 9 Prompt Templates

This module contains every prompt from the Complete LLM Prompt Suite.
Each prompt is an f-string-compatible template with named placeholders.
Use .format() or f-string substitution to fill in the variables.

System Prompt must be injected on every LLM call.
"""

# =============================================================================
# 0. SYSTEM PROMPT — Base Identity
# =============================================================================
SYSTEM_PROMPT = """You are a UK49s lottery prediction analyst. You analyze draw history using statistical patterns, sequences, frequency analysis, gap theory, Markov chains, co-occurrence correlation, and positional probability. You never guess randomly — every prediction is derived from data. You always return exactly 10 rows of 3 numbers each, where all numbers are between 1 and 49 with no duplicates within a row."""

# =============================================================================
# 1. Prompt 1 — Frequency & Gap Analysis
# =============================================================================
PROMPT_1_FREQUENCY_GAP = """Given the following UK49s draw history (most recent last): {draw_history}

Analyze:
1. The top 15 most frequent numbers in the last 200 draws
2. The top 15 numbers most overdue based on average gap since last appearance
3. Assign each number a combined hot/due score between 0 and 1

Return a JSON object: {{ "number": score }} for all 49 numbers.
"""

# =============================================================================
# 2. Prompt 2 — Markov Chain / Sequence Pattern
# =============================================================================
PROMPT_2_MARKOV = """Given this UK49s draw history: {draw_history}
The most recent draw was: {last_draw}

Using Markov chain analysis:
1. Identify which numbers most frequently followed the numbers in the last draw
2. Identify 2-draw and 3-draw sequence patterns leading to the current state
3. Score each number 1-49 by how likely it is to appear in the next draw based on transitions

Return a JSON object: {{ "number": probability_score }}
"""

# =============================================================================
# 3. Prompt 3 — Co-occurrence & Correlation
# =============================================================================
PROMPT_3_COOCURRENCE = """Given this UK49s draw history: {draw_history}
The most recent draw was: {last_draw}

Analyze co-occurrence patterns:
1. Which numbers appear together most frequently in the same draw
2. Which numbers from the last draw have strong pair/triplet partners historically
3. Score each number 1-49 by co-occurrence affinity with the last draw

Return a JSON object: {{ "number": affinity_score }}
"""

# =============================================================================
# 4. Prompt 4 — Positional Probability
# =============================================================================
PROMPT_4_POSITIONAL = """Given this UK49s draw history (each draw sorted ascending): {draw_history}

Analyze positional distribution across 6 positions:
1. For each position 1-6, which numbers appear most frequently
2. Identify positional biases - numbers that strongly prefer certain positions
3. Score each number per position

Return a JSON object:
{{
  "position_1": {{ "number": probability }},
  "position_2": {{ "number": probability }},
  "position_3": {{ "number": probability }},
  "position_4": {{ "number": probability }},
  "position_5": {{ "number": probability }},
  "position_6": {{ "number": probability }}
}}
"""

# =============================================================================
# 8. Prompt 8 — LSTM / Sequence Momentum
# =============================================================================
PROMPT_8_LSTM = """You are analyzing UK49s draw history to simulate LSTM sequential pattern recognition.
Draw history (most recent last, each draw as a list of 6 numbers): {draw_history}
Last 10 draws specifically: {last_10_draws}

Using deep sequence analysis:
1. Treat each draw as a timestep in a sequence
2. Identify recurring number patterns across windows of 5, 10, and 20 draws
3. Detect which numbers are trending upward in appearance frequency over the last 30 draws vs the last 100 draws
4. Identify numbers that appeared in clusters (3+ consecutive draws) recently
5. Score each number 1-49 by sequence momentum

Return only this JSON:
{{
  "lstm_scores": {{ "1": 0.XX, "2": 0.XX, ... "49": 0.XX }},
  "trending_up": [list of numbers gaining momentum],
  "trending_down": [list of numbers losing momentum],
  "cluster_numbers": [numbers appearing in 3+ recent consecutive draws]
}}
"""

# =============================================================================
# 5. Prompt 5 — Revised Ensemble Scoring & Prediction (MASTER)
# =============================================================================
PROMPT_5_ENSEMBLE = """You have the following signal scores for all 49 UK49s numbers:

Frequency/Gap scores: {frequency_gap_scores}
Markov/Sequence scores: {markov_scores}
Co-occurrence scores: {cooccurrence_scores}
Positional scores: {positional_scores}
LSTM/Sequence momentum scores: {lstm_scores}

Current signal weights:
- Frequency/Gap: {w_freq}
- Markov: {w_markov}
- Co-occurrence: {w_cooc}
- Positional: {w_pos}
- LSTM: {w_lstm}

Rules:
1. Compute a weighted ensemble score for each number using the weights above
2. Do NOT let any single signal dominate - if one weight exceeds 0.40 cap it at 0.40 and redistribute
3. Avoid selecting numbers that are trending_down in the LSTM signal unless their other scores are exceptionally high
4. Prioritize numbers that appear in at least 3 of the 5 signals top 20 candidates
5. Each row of 3 must have internal coherence - mix hot, due, and trending numbers rather than picking the top 3 ranked numbers for every row

Generate exactly 10 rows of 3 numbers. No duplicates within a row. Numbers must be between 1-49.

Return only this JSON:
{{
  "predictions": [ [n1, n2, n3], [n4, n5, n6], ... ],
  "top_candidates": [ {{ "number": n, "score": 0.XX, "signals_agreed": 3 }} ]
}}
"""

# =============================================================================
# 6. Prompt 6 — Revised Self-Correction
# =============================================================================
PROMPT_6_SELF_CORRECTION = """The predicted numbers for the last UK49s draw were: {predicted_numbers}
The actual draw result was: {actual_draw}

Signal scores that were used (top 20 per signal):
- Frequency/Gap: {frequency_gap_scores}
- Markov: {markov_scores}
- Co-occurrence: {cooccurrence_scores}
- Positional: {positional_scores}
- LSTM: {lstm_scores}

Current weights: {current_weights}

Analyze:
1. For each number in the actual draw, which signals scored it highly vs missed it
2. Which signal was most accurate overall this draw
3. Which signal contributed most to wrong predictions
4. Why the predictions deviated from the actual draw - was it a pattern break, a cold number returning, or a positional anomaly
5. Suggest new weights that would have improved this draw's prediction - be conservative, max shift of 0.05 per signal per correction cycle

Return only this JSON:
{{
  "hit_count": number of predicted numbers that matched,
  "best_signal_this_draw": "signal name",
  "worst_signal_this_draw": "signal name",
  "deviation_reason": "brief explanation",
  "adjusted_weights": {{
    "frequency_gap": 0.XX,
    "markov": 0.XX,
    "cooccurrence": 0.XX,
    "positional": 0.XX,
    "lstm": 0.XX
  }}
}}
"""

# =============================================================================
# 7. Prompt 7 — /predict Command Formatter
# =============================================================================
PROMPT_7_FORMAT = """Given these 10 prediction rows for the next UK49s draw: {predictions}

Format them cleanly for a Telegram message.
Each row on its own line, numbered 1-10.
Numbers separated by dashes.
No extra commentary, no disclaimers.

Example format:
1. 05 - 18 - 33
2. 07 - 22 - 41
3. 11 - 29 - 44
4. 03 - 15 - 27
5. 08 - 19 - 35
6. 12 - 24 - 38
7. 01 - 14 - 46
8. 06 - 21 - 49
9. 09 - 30 - 42
10. 02 - 17 - 45
"""

# =============================================================================
# 9. Diagnostic Prompt — Accuracy Analysis
# =============================================================================
PROMPT_DIAGNOSTIC = """I have a UK49s prediction bot whose predictions are consistently far from actual draw results.

Here are the last 20 actual draws: {last_20_draws}
Here are the bot's predictions for those same draws: {last_20_predictions}

Diagnose:
1. What is the average hit rate (predicted numbers matching actual draw per row)
2. Which number ranges (1-16 low, 17-32 mid, 33-49 high) is the bot consistently missing
3. Is the bot over-indexing on hot numbers and ignoring due/cold numbers
4. Are there positional patterns in the actual draws the bot is completely missing
5. What is the single biggest flaw in the prediction pattern

Return only this JSON:
{{
  "avg_hit_rate": 0.XX,
  "weak_range": "low / mid / high / spread",
  "over_indexing_issue": "description",
  "missed_positional_pattern": "description",
  "biggest_flaw": "description",
  "recommended_weight_start": {{
    "frequency_gap": 0.XX,
    "markov": 0.XX,
    "cooccurrence": 0.XX,
    "positional": 0.XX,
    "lstm": 0.XX
  }}
}}
"""

# =============================================================================
# Convenience mapping
# =============================================================================
PROMPT_TEMPLATES = {
    "system": SYSTEM_PROMPT,
    "frequency_gap": PROMPT_1_FREQUENCY_GAP,
    "markov": PROMPT_2_MARKOV,
    "cooccurrence": PROMPT_3_COOCURRENCE,
    "positional": PROMPT_4_POSITIONAL,
    "ensemble": PROMPT_5_ENSEMBLE,
    "self_correction": PROMPT_6_SELF_CORRECTION,
    "format": PROMPT_7_FORMAT,
    "lstm": PROMPT_8_LSTM,
    "diagnostic": PROMPT_DIAGNOSTIC,
}
