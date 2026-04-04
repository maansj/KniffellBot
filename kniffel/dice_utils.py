"""
dice_utils.py
=============
Utility functions for dice probability and expected-value calculations.
Used by the bot to reason about re-rolling strategies.
"""

from __future__ import annotations
import random
import itertools
from collections import Counter
from functools import lru_cache
from kniffel.constants import NUM_DICE, DICE_FACES


# ──────────────────────────────────────────────────────────────────────────────
# Basic dice operations
# ──────────────────────────────────────────────────────────────────────────────

def roll_dice(n: int = NUM_DICE) -> list[int]:
    """Roll *n* fresh dice, return sorted list."""
    return sorted(random.randint(1, 6) for _ in range(n))


def reroll(kept: list[int], n_reroll: int) -> list[int]:
    """Keep *kept* dice and add *n_reroll* fresh dice."""
    return sorted(kept + roll_dice(n_reroll))


def dice_hash(dice: list[int]) -> tuple[int, ...]:
    return tuple(sorted(dice))


# ──────────────────────────────────────────────────────────────────────────────
# Enumerate all possible outcomes after re-rolling k dice
# ──────────────────────────────────────────────────────────────────────────────

# Pre-build outcome tables at import time (tiny memory, big speed win)
_OUTCOMES: dict[int, list[tuple[int,...]]] = {
    k: list(itertools.product(DICE_FACES, repeat=k))
    for k in range(NUM_DICE + 1)
}


def all_outcomes(n_reroll: int) -> list[tuple[int, ...]]:
    """All sorted outcomes of rolling *n_reroll* dice (with repetition)."""
    return _OUTCOMES[n_reroll]


@lru_cache(maxsize=65536)
def _cached_ev(kept: tuple[int,...], row: str, score_fn_name: str) -> float:
    """Cached expected-value computation.  score_fn looked up by name."""
    from kniffel.scoring import score_dice as _sd
    n_reroll = NUM_DICE - len(kept)
    if n_reroll == 0:
        return float(_sd(list(kept), row))
    outcomes = _OUTCOMES[n_reroll]
    total = sum(_sd(sorted(list(kept) + list(o)), row) for o in outcomes)
    return total / len(outcomes)


def expected_score_after_reroll(
    kept: tuple[int, ...],
    row: str,
    score_fn,
) -> float:
    return _cached_ev(kept, row, "score_dice")


# ──────────────────────────────────────────────────────────────────────────────
# Best keep strategy for a target row
# ──────────────────────────────────────────────────────────────────────────────

def best_keep_for_row(
    dice: list[int],
    row: str,
    score_fn,
) -> tuple[list[int], list[int], float, str]:
    """
    Enumerate all *unique* value-multisets of *dice* to keep, return the one
    that maximises expected score for *row*.

    We work with sorted tuples so equivalent subsets (e.g. keeping die #1
    vs die #3 when both show 4) are evaluated only once, cutting work from
    2^5=32 masks to at most 32 unique multisets (often far fewer).

    Returns
    -------
    (kept_dice, reroll_dice, expected_value, reasoning)
    """
    best_ev   = -1.0
    best_kept: list[int] = []

    seen: set[tuple] = set()
    for mask in range(1 << NUM_DICE):
        kept_tuple = tuple(sorted(dice[i] for i in range(NUM_DICE) if mask & (1 << i)))
        if kept_tuple in seen:
            continue
        seen.add(kept_tuple)

        ev = expected_score_after_reroll(kept_tuple, row, score_fn)
        kept_list = list(kept_tuple)
        if ev > best_ev or (ev == best_ev and len(kept_list) > len(best_kept)):
            best_ev   = ev
            best_kept = kept_list

    reroll = _compute_reroll(dice, best_kept)
    reasoning = _keep_reasoning(dice, best_kept, row, best_ev)
    return best_kept, reroll, best_ev, reasoning


def _compute_reroll(dice: list[int], kept: list[int]) -> list[int]:
    """Given original dice and kept subset, return which dice to re-roll."""
    remaining = list(dice)
    for k in kept:
        remaining.remove(k)
    return remaining


def _keep_reasoning(
    dice: list[int],
    kept: list[int],
    row: str,
    ev: float,
) -> str:
    n_reroll = NUM_DICE - len(kept)
    if n_reroll == 0:
        return f"Keeping all dice {dice} — no re-roll needed for {row}."
    return (
        f"Keeping {kept or 'nothing'} and re-rolling {n_reroll} die/dice "
        f"gives an expected value of {ev:.1f} pts for '{row}'."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Monte-Carlo simulation of expected score (for validation / complex rows)
# ──────────────────────────────────────────────────────────────────────────────

def monte_carlo_ev(
    kept: list[int],
    row: str,
    score_fn,
    n_sim: int = 5_000,
) -> float:
    """Monte-Carlo estimate of expected score keeping *kept* dice."""
    n_reroll = NUM_DICE - len(kept)
    total = 0
    for _ in range(n_sim):
        outcome = sorted(kept + roll_dice(n_reroll))
        total  += score_fn(outcome, row)
    return total / n_sim
