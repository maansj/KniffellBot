"""
bot.py
======
KniffellBot – greedy expected-value bot with teaching explanations.

Strategy overview
-----------------
1. **Slot selection**  (which cell to target this turn)
   For each available (col, row) slot, compute a "slot value" that weighs:
   - Expected score for the best re-roll strategy targeting that slot
   - Column-type urgency (DOWN/UP columns with few remaining slots are urgent)
   - Bonus proximity (upper-section slots get a boost when close to 63-pt bonus)

2. **Re-roll selection**  (which dice to keep each throw)
   Given the target slot, enumerate all 32 subsets of dice to keep
   and choose the one maximising expected score.

3. **Teaching**  (human-readable reasoning)
   Every decision produces a plain-English explanation covering:
   - Why this slot was chosen (EV, urgency, bonus proximity)
   - Why these dice were kept (EV, combinations being pursued)
"""

from __future__ import annotations
import logging
from collections import Counter
from dataclasses import dataclass, field

from kniffel.constants import (
    ALL_ROWS, NUM_ROWS, NUM_COLS, COLUMNS, ROW_IDX,
    DOWN, UP, FREE, NUM_THROWS, NUM_DICE,
    UPPER_BONUS_THRESHOLD, UPPER_BONUS_VALUE,
)
from kniffel.scoring import score_dice, max_possible_score
from kniffel.board import Board
from kniffel.dice_utils import (
    best_keep_for_row, expected_score_after_reroll, roll_dice, reroll,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data classes for decisions
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RerollDecision:
    """Result of asking the bot which dice to keep/re-roll."""
    kept:     list[int]
    reroll:   list[int]
    target_col: int
    target_row: int
    expected_value: float
    throw_number: int          # 1-based, current throw number
    reasoning: str


@dataclass
class PlacementDecision:
    """Result of asking the bot where to place the final dice."""
    col_idx:  int
    row_idx:  int
    row_name: str
    col_label: str
    score:    int
    reasoning: str


@dataclass
class TurnLog:
    """Full log of one turn."""
    turn_number: int
    reroll_decisions: list[RerollDecision] = field(default_factory=list)
    placement: PlacementDecision | None = None
    final_dice: list[int] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Helper utilities
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


def _remaining_upper_rows(board: Board, col_idx: int) -> list[int]:
    return [r for r in range(6) if board.grid[col_idx][r] is None]


def _bonus_boost(board: Board, col_idx: int, row_idx: int, dice: list[int]) -> float:
    """
    Extra value for placing in an upper-section row when the column is close
    to earning the 35-pt bonus.
    """
    if row_idx >= 6:
        return 0.0
    current_upper = _upper_sum_in_col(board, col_idx)
    remaining_rows = _remaining_upper_rows(board, col_idx)
    if row_idx not in remaining_rows:
        return 0.0

    pts_needed = max(0, UPPER_BONUS_THRESHOLD - current_upper)
    potential  = sum(
        max_possible_score(ALL_ROWS[r]) for r in remaining_rows
    )
    if potential == 0:
        return 0.0

    # Fraction of bonus already within reach
    reach_ratio = min(1.0, potential / max(pts_needed, 1))
    # Score this row contributes
    actual = score_dice(dice, ALL_ROWS[row_idx])
    bonus_fraction = actual / max(pts_needed, 1)
    return UPPER_BONUS_VALUE * reach_ratio * bonus_fraction * 0.5  # dampened


def _column_urgency(board: Board, col_idx: int) -> float:
    """
    DOWN/UP columns have mandatory ordering, so filling them is more
    urgent than FREE columns. Returns a small multiplier (1.0–1.2).
    """
    col_type = COLUMNS[col_idx][1]
    if col_type == FREE:
        return 1.0
    valid = board.valid_rows_for_col(col_idx)
    if not valid:
        return 1.0
    # If we must place in a high-value row next, boost urgency
    next_row = valid[0]
    max_sc   = max_possible_score(ALL_ROWS[next_row])
    return 1.0 + 0.2 * (max_sc / 30.0)


# ──────────────────────────────────────────────────────────────────────────────
# KniffellBot
# ──────────────────────────────────────────────────────────────────────────────

class KniffellBot:
    """
    An AI bot that plays Kniffel (German Yatzy) optimally using greedy
    expected-value maximisation.

    Usage
    -----
    bot = KniffellBot()
    board = Board()

    # --- per turn ---
    dice = roll_dice()
    for throw_num in range(1, 5):      # up to 4 throws
        decision = bot.decide_reroll(board, dice, throw_num)
        print(decision.reasoning)
        if not decision.reroll:
            break                      # bot chose to stop
        dice = reroll(decision.kept, len(decision.reroll))

    placement = bot.decide_placement(board, dice, current_throw=throw_num)
    print(placement.reasoning)
    board.fill(placement.col_idx, placement.row_idx, dice)
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def decide_reroll(
        self,
        board: Board,
        dice: list[int],
        throw_number: int,    # 1-based, current throw number
    ) -> RerollDecision:
        """
        Given current *dice* and *board* state, decide which dice to keep
        and which to re-roll.

        Returns RerollDecision with `reroll=[]` if the bot prefers to stop.
        """
        if throw_number >= 4:
            # No more re-rolls allowed after 4th throw
            best_col, best_row, _ = self._best_placement(board, dice)
            ev = float(score_dice(dice, ALL_ROWS[best_row]))
            return RerollDecision(
                kept=dice, reroll=[], target_col=best_col, target_row=best_row,
                expected_value=ev, throw_number=throw_number,
                reasoning=(
                    f"Throw {throw_number} is the final throw — "
                    f"no more re-rolls available. Will place in "
                    f"{_col_label(best_col)} / {ALL_ROWS[best_row]} "
                    f"for {int(ev)} pts."
                ),
            )

        # Pick the best (col, row, keep_strategy) across all available slots
        best_kept, best_reroll, best_ev, best_col, best_row, reasoning = (
            self._best_reroll_strategy(board, dice, throw_number)
        )

        current_best_score = score_dice(dice, ALL_ROWS[best_row])
        # Stop early if keeping all dice already scores well
        if not best_reroll or current_best_score >= best_ev * 0.95:
            return RerollDecision(
                kept=dice, reroll=[],
                target_col=best_col, target_row=best_row,
                expected_value=float(current_best_score),
                throw_number=throw_number,
                reasoning=(
                    f"Current dice {dice} already score {current_best_score} pts "
                    f"in '{ALL_ROWS[best_row]}' — not worth re-rolling. "
                    f"Stopping here."
                ),
            )

        return RerollDecision(
            kept=best_kept, reroll=best_reroll,
            target_col=best_col, target_row=best_row,
            expected_value=best_ev,
            throw_number=throw_number,
            reasoning=reasoning,
        )

    def decide_placement(
        self,
        board: Board,
        dice: list[int],
        current_throw: int = 4,
    ) -> PlacementDecision:
        """
        After all re-rolls are done, decide the best cell to fill.
        """
        col_idx, row_idx, score = self._best_placement(board, dice)
        row_name  = ALL_ROWS[row_idx]
        col_label = _col_label(col_idx)
        reasoning = self._placement_reasoning(
            board, dice, col_idx, row_idx, score
        )
        return PlacementDecision(
            col_idx=col_idx, row_idx=row_idx,
            row_name=row_name, col_label=col_label,
            score=score, reasoning=reasoning,
        )

    # ──────────────────────────────────────────────
    # Internal: best placement
    # ──────────────────────────────────────────────

    def _best_placement(
        self, board: Board, dice: list[int]
    ) -> tuple[int, int, int]:
        """Return (col_idx, row_idx, score) for the best cell to fill now."""
        best_val   = -1e9
        best_col   = 0
        best_row   = 0
        best_score = 0

        # Cache score per unique row
        row_score: dict[int, int] = {}

        for col_idx in range(NUM_COLS):
            urgency = _column_urgency(board, col_idx)
            for row_idx in board.valid_rows_for_col(col_idx):
                if row_idx not in row_score:
                    row_score[row_idx] = score_dice(dice, ALL_ROWS[row_idx])
                sc    = row_score[row_idx]
                bonus = _bonus_boost(board, col_idx, row_idx, dice)
                val   = (sc + bonus) * urgency

                if val > best_val:
                    best_val   = val
                    best_col   = col_idx
                    best_row   = row_idx
                    best_score = sc

        return best_col, best_row, best_score

    # ──────────────────────────────────────────────
    # Internal: best re-roll strategy
    # ──────────────────────────────────────────────

    def _best_reroll_strategy(
        self,
        board: Board,
        dice: list[int],
        throw_number: int,
    ) -> tuple[list[int], list[int], float, int, int, str]:
        """
        For every available (col, row) slot, compute the best keep strategy
        and expected value.  Return the overall best.

        Optimisation: we group slots by *row* first (same row → same EV calc),
        compute best_keep_for_row once per unique row, then apply per-slot
        multipliers.

        Returns
        -------
        (kept, reroll, ev, best_col, best_row, reasoning)
        """
        # --- 1. Collect which (col, row) pairs are available ---
        slots: list[tuple[int,int]] = []   # (col_idx, row_idx)
        for col_idx in range(NUM_COLS):
            for row_idx in board.valid_rows_for_col(col_idx):
                slots.append((col_idx, row_idx))

        if not slots:
            return dice, [], 0.0, 0, 0, "No slots available."

        # --- 2. Compute best-keep per unique row (cache within this call) ---
        row_cache: dict[int, tuple] = {}   # row_idx → (kept, rl, ev, reason)
        for _, row_idx in slots:
            if row_idx not in row_cache:
                row_name = ALL_ROWS[row_idx]
                row_cache[row_idx] = best_keep_for_row(dice, row_name, score_dice)

        # --- 3. Find slot with highest adjusted EV ---
        best_ev    = -1.0
        best_col   = slots[0][0]
        best_row   = slots[0][1]
        base_reason = ""

        for col_idx, row_idx in slots:
            kept, rl, ev, reason = row_cache[row_idx]
            bonus        = _bonus_boost(board, col_idx, row_idx, dice)
            urgency      = _column_urgency(board, col_idx)
            adjusted_ev  = (ev + bonus) * urgency

            if adjusted_ev > best_ev:
                best_ev     = adjusted_ev
                best_col    = col_idx
                best_row    = row_idx
                base_reason = reason

        best_kept, best_rl = row_cache[best_row][0], row_cache[best_row][1]
        row_name  = ALL_ROWS[best_row]
        col_label = _col_label(best_col)
        reasoning = (
            f"Targeting '{row_name}' in {col_label}. "
            + base_reason
            + f" (adjusted EV: {best_ev:.1f} pts)"
        )
        return best_kept, best_rl, best_ev, best_col, best_row, reasoning

    # ──────────────────────────────────────────────
    # Internal: human-readable placement reasoning
    # ──────────────────────────────────────────────

    def _placement_reasoning(
        self,
        board: Board,
        dice: list[int],
        col_idx: int,
        row_idx: int,
        score: int,
    ) -> str:
        row_name  = ALL_ROWS[row_idx]
        col_label = _col_label(col_idx)
        counts    = Counter(dice)
        col_type  = COLUMNS[col_idx][1]

        parts = [
            f"Placing {dice} → '{row_name}' in {col_label} for {score} pts."
        ]

        # Explain *why* this slot
        if score == 0:
            parts.append(
                "⚠ Scoring 0 here — a sacrificial placement to keep the "
                "board legal (DOWN/UP ordering requires filling this row next)."
            )
        else:
            if row_idx < 6:
                upper_sum = _upper_sum_in_col(board, col_idx) + score
                needed    = max(0, UPPER_BONUS_THRESHOLD - upper_sum)
                parts.append(
                    f"Upper section: column sum becomes ≈{upper_sum}. "
                    + (
                        f"Still need ~{needed} more pts in this column's upper "
                        f"section to reach the 35-pt bonus."
                        if needed > 0 else
                        "Column's upper section already qualifies for the 35-pt bonus! 🎉"
                    )
                )
            elif row_name == "Kniffel":
                parts.append("🏆 Kniffel! Maximum score of 50 pts.")
            elif row_name == "gr.Straße":
                parts.append("🎯 Large straight — 40 pts, a premium score.")
            elif row_name == "Full-House":
                parts.append("Two-and-three mix scores 25 pts flat.")
            elif row_name in ("3er-Pasch", "4er-Pasch", "Chance"):
                parts.append(
                    f"Sum of all dice = {sum(dice)} pts."
                )

        # Column constraint note
        if col_type == DOWN:
            ptr = board._down_ptr[COLUMNS[col_idx][0] - 1]
            parts.append(
                f"↓ DOWN column: row {row_idx+1}/13 filled; "
                f"next fill must be row {ptr+2}/13."
            )
        elif col_type == UP:
            ptr = board._up_ptr[COLUMNS[col_idx][0] - 1]
            parts.append(
                f"↑ UP column: row {row_idx+1}/13 filled; "
                f"next fill must be row {ptr}/13."
            )

        return " ".join(parts)
