"""
bot.py
======
KniffellBot – advantage-based bot inspired by Yahtzotron.

Strategy (inspired by Yahtzotron's key insight)
------------------------------------------------
Instead of raw expected value, we use ADVANTAGE for slot selection:

    advantage(row, dice) = best_EV(row | dice, k re-rolls) - avg_EV(row)

where avg_EV(row) is the average score for that row across all possible
5-dice rolls (pre-computed at import time).

This means: a large straight on roll 1 has a HUGE advantage for gr.Straße
(40 pts vs ~6 pts average → advantage ~+34), so the bot immediately places
it there at Wurf 1 rather than wasting re-rolls.

Wurf selection
--------------
For each possible Wurf N (1-4) with open slots:
  1. Compute best advantage achievable AT Wurf N given current dice
     (= best advantage with N-1 re-rolls from this roll)
  2. Weight by urgency (ordered cols, nearly-full Wurfs)
  3. Pick the Wurf with the highest weighted advantage

Re-roll selection
-----------------
Given a target Wurf N and current throw T, we have N-T re-rolls left.
Enumerate all 2^5 keep subsets, compute exact multi-roll EV for each,
pick the best.
"""

from __future__ import annotations
import logging
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from kniffel.constants import (
    ALL_ROWS, NUM_ROWS, NUM_COLS, COLUMNS, ROW_IDX,
    DOWN, UP, FREE, NUM_THROWS, NUM_DICE, DICE_FACES,
    UPPER_BONUS_THRESHOLD, UPPER_BONUS_VALUE,
)
from kniffel.scoring import score_dice, max_possible_score
from kniffel.board import Board
from kniffel.dice_utils import (
    best_keep_for_row, expected_score_after_reroll,
    _cached_ev, _OUTCOMES, roll_dice, reroll,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Average EV per row — baseline for advantage computation
# ──────────────────────────────────────────────────────────────────────────────

def _compute_avg_ev() -> dict[str, float]:
    """Average score for each row across all 6^5 possible rolls."""
    all_rolls = _OUTCOMES[5]
    avgs = {}
    for row in ALL_ROWS:
        total = sum(score_dice(list(r), row) for r in all_rolls)
        avgs[row] = total / len(all_rolls)
    return avgs

AVG_EV: dict[str, float] = _compute_avg_ev()


# ──────────────────────────────────────────────────────────────────────────────
# Multi-roll EV with optimal keep strategy
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=65536)
def _ev_after_k_rerolls(kept: tuple[int, ...], row: str, rerolls_left: int) -> float:
    """
    Expected score for *row* starting from *kept* dice with *rerolls_left*
    re-rolls, each time keeping the optimal subset.
    """
    n_reroll = NUM_DICE - len(kept)

    if rerolls_left == 0:
        return _cached_ev(kept, row, "score_dice")

    outcomes = _OUTCOMES[n_reroll]
    total = 0.0
    for outcome in outcomes:
        new_dice = tuple(sorted(list(kept) + list(outcome)))
        best = -1.0
        seen_sub: set[tuple] = set()
        for mask in range(1 << NUM_DICE):
            sub = tuple(new_dice[i] for i in range(NUM_DICE) if mask & (1 << i))
            sub = tuple(sorted(sub))
            if sub in seen_sub:
                continue
            seen_sub.add(sub)
            ev = _ev_after_k_rerolls(sub, row, rerolls_left - 1)
            if ev > best:
                best = ev
        total += best
    return total / len(outcomes)


def best_ev_with_rerolls(dice: list[int], row: str, rerolls: int) -> tuple[float, list[int]]:
    """Best (EV, kept_dice) for *row* from *dice* with *rerolls* re-rolls."""
    best_ev   = -1.0
    best_kept: list[int] = []
    seen: set[tuple] = set()

    for mask in range(1 << NUM_DICE):
        kept = tuple(sorted(dice[i] for i in range(NUM_DICE) if mask & (1 << i)))
        if kept in seen:
            continue
        seen.add(kept)
        ev = _ev_after_k_rerolls(kept, row, rerolls)
        if ev > best_ev or (ev == best_ev and len(kept) > len(best_kept)):
            best_ev   = ev
            best_kept = list(kept)

    return best_ev, best_kept


# ──────────────────────────────────────────────────────────────────────────────
# Advantage
# ──────────────────────────────────────────────────────────────────────────────

def advantage(row: str, dice: list[int], rerolls: int) -> float:
    """advantage = best_EV_with_rerolls - avg_EV_for_row"""
    ev, _ = best_ev_with_rerolls(dice, row, rerolls)
    return ev - AVG_EV[row]


# ──────────────────────────────────────────────────────────────────────────────
# Column / slot helpers
# ──────────────────────────────────────────────────────────────────────────────

def _col_label(col_idx: int) -> str:
    throw_n, ctype = COLUMNS[col_idx]
    symbol = {DOWN: "↓", UP: "↑", FREE: "F"}[ctype]
    return f"Wurf {throw_n} [{symbol}]"


def _upper_sum_in_col(board: Board, col_idx: int) -> int:
    return sum(
        board.grid[col_idx][r]
        for r in range(6)
        if board.grid[col_idx][r] is not None
    )


def _bonus_boost(board: Board, col_idx: int, row_idx: int, score: float) -> float:
    """Extra value when a score pushes a column toward the 35-pt bonus."""
    if row_idx >= 6:
        return 0.0
    current_upper = _upper_sum_in_col(board, col_idx)
    needed = max(0, UPPER_BONUS_THRESHOLD - current_upper)
    if needed == 0:
        return 0.0
    contribution = min(score, needed) / needed
    return UPPER_BONUS_VALUE * contribution * 0.4


def _slot_urgency(board: Board, col_idx: int, wurf: int) -> float:
    """
    Urgency weight for a slot. Higher when:
    - This Wurf is running low on slots (must fill them soon)
    - Column is DOWN or UP ordered (fill order is forced)
    Returns 0.0 if no slots are available at this Wurf.
    """
    slots_here = len(board.valid_rows_for_col(col_idx, wurf))
    if slots_here == 0:
        return 0.0

    slots_in_wurf = sum(
        len(board.valid_rows_for_col(c, wurf)) for c in range(NUM_COLS)
    )
    slots_total = sum(
        len(board.valid_rows_for_col(c, w))
        for w in range(1, 5)
        for c in range(NUM_COLS)
    )

    scarcity    = 1.0 + 0.3 * max(0.0, 1.0 - slots_in_wurf / max(slots_total * 0.25, 1))
    order_boost = 1.15 if COLUMNS[col_idx][1] in (DOWN, UP) else 1.0

    return scarcity * order_boost


def _compute_reroll(dice: list[int], kept: list[int]) -> list[int]:
    remaining = list(dice)
    for k in kept:
        remaining.remove(k)
    return remaining


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RerollDecision:
    kept:           list[int]
    reroll:         list[int]
    target_col:     int
    target_row:     int
    expected_value: float
    throw_number:   int
    reasoning:      str


@dataclass
class PlacementDecision:
    col_idx:   int
    row_idx:   int
    row_name:  str
    col_label: str
    score:     int
    reasoning: str


@dataclass
class TurnLog:
    turn_number:      int
    reroll_decisions: list[RerollDecision] = field(default_factory=list)
    placement:        PlacementDecision | None = None
    final_dice:       list[int] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# KniffellBot
# ──────────────────────────────────────────────────────────────────────────────

class KniffellBot:
    """
    Advantage-based Kniffel bot.

    Core idea from Yahtzotron: use advantage (EV minus category average) rather
    than raw EV. This immediately recognises exceptional rolls (large straight,
    Kniffel, full house) as worth placing now, even on Wurf 1.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    # ── Public API ────────────────────────────────────────────────────────────

    def choose_target_wurf(self, board: Board, dice: list[int]) -> int:
        """
        Given the opening roll, pick the best Wurf (1-4) to target.

        Evaluates advantage for each Wurf using multi-roll EV lookahead.
        A great first roll (e.g. large straight) scores high advantage at
        Wurf 1 and the bot will place immediately rather than re-rolling.
        """
        best_wurf = None
        best_val  = -1e9

        for wurf in range(1, 5):
            rerolls = wurf - 1
            wurf_best_val = -1e9

            for col_idx in range(NUM_COLS):
                urgency = _slot_urgency(board, col_idx, wurf)
                if urgency == 0:
                    continue
                for row_idx in board.valid_rows_for_col(col_idx, wurf):
                    row_name = ALL_ROWS[row_idx]
                    adv      = advantage(row_name, dice, rerolls)
                    bonus    = _bonus_boost(board, col_idx, row_idx,
                                            adv + AVG_EV[row_name])
                    val      = (adv + bonus) * urgency

                    if val > wurf_best_val:
                        wurf_best_val = val

            if wurf_best_val > best_val:
                best_val  = wurf_best_val
                best_wurf = wurf

        if best_wurf is None:
            raise RuntimeError("No Wurf has remaining slots — board is complete.")

        return best_wurf

    def decide_reroll(
        self,
        board: Board,
        dice: list[int],
        throw_number: int,
        target_wurf: int = 0,
    ) -> RerollDecision:
        """Decide which dice to keep. Returns reroll=[] on final throw."""
        wurf     = target_wurf if target_wurf > 0 else throw_number
        is_final = (throw_number >= wurf)

        if is_final:
            try:
                col_idx, row_idx, sc = self._best_placement(board, dice, wurf)
            except RuntimeError:
                col_idx, row_idx, sc = self._best_placement_any(board, dice)
            return RerollDecision(
                kept=dice, reroll=[],
                target_col=col_idx, target_row=row_idx,
                expected_value=float(sc), throw_number=throw_number,
                reasoning=(
                    f"Final roll for Wurf {wurf} — placing in "
                    f"{_col_label(col_idx)} / '{ALL_ROWS[row_idx]}' for {sc} pts."
                ),
            )

        best_kept, best_col, best_row, best_ev, reasoning = (
            self._best_keep_for_wurf(board, dice, throw_number, wurf)
        )
        return RerollDecision(
            kept=best_kept,
            reroll=_compute_reroll(dice, best_kept),
            target_col=best_col, target_row=best_row,
            expected_value=best_ev, throw_number=throw_number,
            reasoning=reasoning,
        )

    def decide_placement(
        self,
        board: Board,
        dice: list[int],
        current_throw: int = 4,
    ) -> PlacementDecision:
        """Place dice in the best advantage slot at current_throw."""
        current_throw = min(current_throw, 4)
        try:
            col_idx, row_idx, score = self._best_placement(board, dice, current_throw)
        except RuntimeError:
            col_idx, row_idx, score = self._best_placement_any(board, dice)

        return PlacementDecision(
            col_idx=col_idx, row_idx=row_idx,
            row_name=ALL_ROWS[row_idx], col_label=_col_label(col_idx),
            score=score,
            reasoning=self._placement_reasoning(board, dice, col_idx, row_idx, score),
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _best_keep_for_wurf(
        self,
        board: Board,
        dice: list[int],
        throw_number: int,
        target_wurf: int,
    ) -> tuple[list[int], int, int, float, str]:
        """Best (kept, col, row, ev, reasoning) targeting *target_wurf*."""
        rerolls = target_wurf - throw_number

        best_val      = -1e9
        best_kept:    list[int] = []
        best_col      = 0
        best_row      = 0
        best_ev       = 0.0
        best_row_name = ""

        # Pre-build unique kept subsets
        subsets: set[tuple] = set()
        for mask in range(1 << NUM_DICE):
            subsets.add(tuple(sorted(dice[i] for i in range(NUM_DICE) if mask & (1 << i))))

        ev_cache: dict[tuple, float] = {}

        for col_idx in range(NUM_COLS):
            urgency = _slot_urgency(board, col_idx, target_wurf)
            if urgency == 0:
                continue
            for row_idx in board.valid_rows_for_col(col_idx, target_wurf):
                row_name = ALL_ROWS[row_idx]

                row_best_ev   = -1.0
                row_best_kept = list(dice)
                for kept in subsets:
                    key = (kept, row_name, rerolls)
                    if key not in ev_cache:
                        ev_cache[key] = _ev_after_k_rerolls(kept, row_name, rerolls)
                    ev = ev_cache[key]
                    if ev > row_best_ev or (ev == row_best_ev and len(kept) > len(row_best_kept)):
                        row_best_ev   = ev
                        row_best_kept = list(kept)

                adv   = row_best_ev - AVG_EV[row_name]
                bonus = _bonus_boost(board, col_idx, row_idx, row_best_ev)
                val   = (adv + bonus) * urgency

                if val > best_val:
                    best_val      = val
                    best_kept     = row_best_kept
                    best_col      = col_idx
                    best_row      = row_idx
                    best_ev       = row_best_ev
                    best_row_name = row_name

        reroll_dice = _compute_reroll(dice, best_kept)
        avg         = AVG_EV.get(best_row_name, 0)
        reasoning   = (
            f"Targeting '{best_row_name}' in {_col_label(best_col)} "
            f"(advantage {best_val:.1f}, avg {avg:.1f}). "
            f"Keeping {best_kept or 'nothing'}, "
            f"re-rolling {len(reroll_dice)} "
            f"{'die' if len(reroll_dice)==1 else 'dice'} "
            f"→ expected {best_ev:.1f} pts "
            f"with {rerolls} re-roll{'s' if rerolls!=1 else ''} left."
        )
        return best_kept, best_col, best_row, best_ev, reasoning

    def _best_placement(
        self, board: Board, dice: list[int], current_throw: int = 1
    ) -> tuple[int, int, int]:
        best_val   = -1e9
        best_col   = None
        best_row   = None
        best_score = 0
        score_cache: dict[int, int] = {}

        for col_idx in range(NUM_COLS):
            urgency = _slot_urgency(board, col_idx, current_throw)
            if urgency == 0:
                continue
            for row_idx in board.valid_rows_for_col(col_idx, current_throw):
                if row_idx not in score_cache:
                    score_cache[row_idx] = score_dice(dice, ALL_ROWS[row_idx])
                sc    = score_cache[row_idx]
                adv   = sc - AVG_EV[ALL_ROWS[row_idx]]
                bonus = _bonus_boost(board, col_idx, row_idx, sc)
                val   = (adv + bonus) * urgency

                if val > best_val:
                    best_val   = val
                    best_col   = col_idx
                    best_row   = row_idx
                    best_score = sc

        if best_col is None:
            raise RuntimeError(f"No valid placement at throw {current_throw}.")
        return best_col, best_row, best_score

    def _best_placement_any(self, board: Board, dice: list[int]) -> tuple[int, int, int]:
        for wurf in range(1, 5):
            try:
                return self._best_placement(board, dice, wurf)
            except RuntimeError:
                continue
        raise RuntimeError("Board is complete.")

    def _placement_reasoning(
        self, board: Board, dice: list[int],
        col_idx: int, row_idx: int, score: int,
    ) -> str:
        row_name  = ALL_ROWS[row_idx]
        col_label = _col_label(col_idx)
        avg       = AVG_EV[row_name]
        adv       = score - avg

        parts = [f"Placing {dice} → '{row_name}' in {col_label} for {score} pts."]

        if adv >= 10:
            parts.append(f"🎯 Excellent! +{adv:.0f} above average ({avg:.0f} avg).")
        elif adv >= 3:
            parts.append(f"Good roll — {adv:.0f} pts above average ({avg:.0f} avg).")
        elif adv >= -3:
            parts.append(f"Average roll (avg is {avg:.0f} pts).")
        else:
            parts.append(f"⚠ Below average ({adv:.0f} vs avg {avg:.0f}) — forced or sacrificial.")

        if score == 0:
            parts.append("Scoring 0 — forced to keep board legal.")
        elif row_name == "Kniffel":
            parts.append("🏆 Kniffel! Maximum 50 pts.")
        elif row_name == "gr.Straße":
            parts.append("Large straight — 40 pts.")
        elif row_name == "kl.Straße":
            parts.append("Small straight — 30 pts.")
        elif row_name == "Full-House":
            parts.append("Full house — 25 pts.")

        if row_idx < 6:
            upper_sum = _upper_sum_in_col(board, col_idx) + score
            needed    = max(0, UPPER_BONUS_THRESHOLD - upper_sum)
            if needed == 0:
                parts.append("Column upper section qualifies for +35 bonus! 🎉")
            else:
                parts.append(f"Upper section now {upper_sum}/63 — need {needed} more for +35 bonus.")

        return " ".join(parts)
