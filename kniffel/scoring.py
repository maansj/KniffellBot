"""
scoring.py
==========
Pure functions that compute scores for a given set of dice and a row name.
Returns 0 if the combination does not qualify for that row.
"""

from collections import Counter
from kniffel.constants import (
    ALL_ROWS, ROW_IDX,
    FULL_HOUSE_SCORE, SMALL_STRAIGHT_SCORE, LARGE_STRAIGHT_SCORE, KNIFFEL_SCORE,
)


def score_dice(dice: list[int], row: str) -> int:
    """
    Return the score for *dice* placed in *row*.

    Parameters
    ----------
    dice : list of 5 ints (1-6)
    row  : one of the 13 row name strings

    Returns
    -------
    int  – score (0 if combination does not qualify)
    """
    counts = Counter(dice)
    total  = sum(dice)

    # ── Upper section ────────────────────────────────────────────────────────
    if row == "1er":
        return dice.count(1) * 1
    if row == "2er":
        return dice.count(2) * 2
    if row == "3er":
        return dice.count(3) * 3
    if row == "4er":
        return dice.count(4) * 4
    if row == "5er":
        return dice.count(5) * 5
    if row == "6er":
        return dice.count(6) * 6

    # ── Lower section ────────────────────────────────────────────────────────
    if row == "3er-Pasch":
        return total if max(counts.values()) >= 3 else 0

    if row == "4er-Pasch":
        return total if max(counts.values()) >= 4 else 0

    if row == "Full-House":
        vals = sorted(counts.values())
        return FULL_HOUSE_SCORE if vals == [2, 3] else 0

    if row == "kl.Straße":
        # Four consecutive numbers anywhere in the dice
        unique = set(dice)
        straights = [{1,2,3,4}, {2,3,4,5}, {3,4,5,6}]
        return SMALL_STRAIGHT_SCORE if any(s <= unique for s in straights) else 0

    if row == "gr.Straße":
        unique = set(dice)
        return LARGE_STRAIGHT_SCORE if unique in ({1,2,3,4,5}, {2,3,4,5,6}) else 0

    if row == "Kniffel":
        return KNIFFEL_SCORE if max(counts.values()) == 5 else 0

    if row == "Chance":
        return total

    raise ValueError(f"Unknown row: {row!r}")


def score_upper_section(board_scores: dict) -> int:
    """Sum of the upper section scores across a single column's filled rows."""
    upper_rows = ALL_ROWS[:6]
    return sum(board_scores.get(r, 0) for r in upper_rows)


def compute_bonus(upper_sum: int) -> int:
    """Return bonus (35) if upper section sum >= 63, else 0."""
    from kniffel.constants import UPPER_BONUS_THRESHOLD, UPPER_BONUS_VALUE
    return UPPER_BONUS_VALUE if upper_sum >= UPPER_BONUS_THRESHOLD else 0


def max_possible_score(row: str) -> int:
    """Return the theoretical maximum score for a row (for normalisation)."""
    maxima = {
        "1er": 5, "2er": 10, "3er": 15, "4er": 20, "5er": 25, "6er": 30,
        "3er-Pasch": 30, "4er-Pasch": 30,
        "Full-House": FULL_HOUSE_SCORE,
        "kl.Straße": SMALL_STRAIGHT_SCORE,
        "gr.Straße": LARGE_STRAIGHT_SCORE,
        "Kniffel": KNIFFEL_SCORE,
        "Chance": 30,
    }
    return maxima.get(row, 30)


def expected_score(row: str, dice: list[int]) -> float:
    """
    Quick heuristic expected value of placing *dice* in *row*
    (no re-rolls considered – used for slot selection after final throw).
    """
    return float(score_dice(dice, row))
