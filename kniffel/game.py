"""
game.py
=======
Full game simulation engine.

A "game" consists of 156 turns (13 rows × 12 columns).
Each turn:
  1. Bot picks a target slot and re-roll strategy.
  2. Dice are rolled up to 4 times.
  3. Bot places the final dice in the chosen slot.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field

from kniffel.constants import NUM_COLS, NUM_ROWS, NUM_DICE, COLUMNS
from kniffel.board import Board
from kniffel.bot import KniffellBot, TurnLog, RerollDecision, PlacementDecision
from kniffel.dice_utils import roll_dice, reroll

logger = logging.getLogger(__name__)


@dataclass
class GameResult:
    grand_total: int
    column_totals: list[int]
    turn_logs: list[TurnLog]
    board_display: str


class Game:
    """Simulate a full Kniffel game played by the bot."""

    def __init__(self, verbose: bool = False):
        self.board   = Board()
        self.bot     = KniffellBot(verbose=verbose)
        self.verbose = verbose
        self.turn_logs: list[TurnLog] = []
        self._turn_number = 0

    def play_full_game(self) -> GameResult:
        """Play all 156 turns and return the result."""
        total_turns = NUM_COLS * NUM_ROWS
        for _ in range(total_turns):
            self._play_turn()

        result = GameResult(
            grand_total    = self.board.grand_total(),
            column_totals  = [self.board.column_total(c) for c in range(NUM_COLS)],
            turn_logs      = self.turn_logs,
            board_display  = self.board.display(),
        )
        return result

    # ──────────────────────────────────────────────
    # Single turn
    # ──────────────────────────────────────────────

    def _play_turn(self):
        self._turn_number += 1
        turn_log = TurnLog(turn_number=self._turn_number)

        if self.verbose:
            logger.info(f"\n{'='*60}")
            logger.info(f"Turn {self._turn_number}")

        # --- Step 1: initial roll ---
        dice      = roll_dice()
        throw_num = 1

        if self.verbose:
            logger.info(f"  Roll 1: {dice}")

        # --- Step 2: choose target Wurf based on the actual first roll ---
        # The bot sees the dice and decides how many total rolls to make (1-4),
        # which determines which Wurf column it will fill this turn.
        target_wurf = self.bot.choose_target_wurf(self.board, dice)

        if self.verbose:
            logger.info(f"  → Targeting Wurf {target_wurf} (will roll {target_wurf} time(s) total)")

        while throw_num < target_wurf:
            # Ask bot which dice to keep for the re-roll
            reroll_dec = self.bot.decide_reroll(self.board, dice, throw_num, target_wurf)
            turn_log.reroll_decisions.append(reroll_dec)

            if self.verbose:
                logger.info(f"  🤖 {reroll_dec.reasoning}")

            dice      = reroll(reroll_dec.kept, len(reroll_dec.reroll))
            throw_num += 1

            if self.verbose:
                logger.info(f"  Roll {throw_num}: {dice}")

        # Record a final "no reroll" decision for logging
        if throw_num == target_wurf:
            final_dec = self.bot.decide_reroll(self.board, dice, throw_num, target_wurf)
            turn_log.reroll_decisions.append(final_dec)

        turn_log.final_dice = dice

        # --- Step 3: place in Wurf target_wurf ---
        placement = self.bot.decide_placement(self.board, dice, target_wurf)
        turn_log.placement = placement

        if self.verbose:
            logger.info(f"  Final dice: {dice}")
            logger.info(f"  📝 {placement.reasoning}")
            logger.info(
                f"  Score: {placement.score}  |  "
                f"Grand total so far: {self.board.grand_total() + placement.score}"
            )

        self.board.fill(placement.col_idx, placement.row_idx, dice, target_wurf)
        self.turn_logs.append(turn_log)
