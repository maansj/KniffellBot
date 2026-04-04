"""
tests/test_scoring.py
=====================
Unit tests for scoring functions and board logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from kniffel.scoring import score_dice
from kniffel.board import Board
from kniffel.constants import ALL_ROWS, NUM_COLS, NUM_ROWS, DOWN, UP, FREE, COLUMNS


# ──────────────────────────────────────────────────────────────────────────────
# Scoring tests
# ──────────────────────────────────────────────────────────────────────────────

class TestUpperSection:
    def test_ones(self):
        assert score_dice([1, 1, 2, 3, 4], "1er") == 2
    def test_sixes_full(self):
        assert score_dice([6, 6, 6, 6, 6], "6er") == 30
    def test_fours_none(self):
        assert score_dice([1, 2, 3, 5, 6], "4er") == 0


class TestLowerSection:
    def test_three_of_a_kind(self):
        assert score_dice([3, 3, 3, 1, 2], "3er-Pasch") == 12
    def test_three_fail(self):
        assert score_dice([1, 2, 3, 4, 5], "3er-Pasch") == 0

    def test_four_of_a_kind(self):
        assert score_dice([5, 5, 5, 5, 2], "4er-Pasch") == 22
    def test_four_fail(self):
        assert score_dice([3, 3, 3, 1, 2], "4er-Pasch") == 0

    def test_full_house(self):
        assert score_dice([2, 2, 3, 3, 3], "Full-House") == 25
    def test_full_house_fail(self):
        assert score_dice([1, 2, 3, 4, 5], "Full-House") == 0

    def test_small_straight(self):
        assert score_dice([1, 2, 3, 4, 6], "kl.Straße") == 30
    def test_small_straight_fail(self):
        assert score_dice([1, 1, 2, 3, 6], "kl.Straße") == 0

    def test_large_straight_low(self):
        assert score_dice([1, 2, 3, 4, 5], "gr.Straße") == 40
    def test_large_straight_high(self):
        assert score_dice([2, 3, 4, 5, 6], "gr.Straße") == 40
    def test_large_straight_fail(self):
        assert score_dice([1, 2, 3, 4, 6], "gr.Straße") == 0

    def test_kniffel(self):
        assert score_dice([4, 4, 4, 4, 4], "Kniffel") == 50
    def test_kniffel_fail(self):
        assert score_dice([4, 4, 4, 4, 3], "Kniffel") == 0

    def test_chance(self):
        assert score_dice([1, 2, 3, 4, 5], "Chance") == 15


# ──────────────────────────────────────────────────────────────────────────────
# Board tests
# ──────────────────────────────────────────────────────────────────────────────

class TestBoard:
    def test_initial_board_empty(self):
        b = Board()
        for c in range(NUM_COLS):
            for r in range(NUM_ROWS):
                assert b.grid[c][r] is None

    def test_down_column_must_fill_in_order(self):
        b = Board()
        # Column 0 is DOWN, throw 1
        valid = b.valid_rows_for_col(0)
        assert valid == [0]  # must start at top

        b.fill(0, 0, [1, 1, 2, 3, 4])
        valid = b.valid_rows_for_col(0)
        assert valid == [1]  # now row 1

    def test_up_column_must_fill_in_reverse_order(self):
        b = Board()
        # Column 4 is UP, throw 1
        valid = b.valid_rows_for_col(4)
        assert valid == [12]  # must start at bottom (row 12 = "Chance")

        b.fill(4, 12, [1, 2, 3, 4, 5])
        valid = b.valid_rows_for_col(4)
        assert valid == [11]

    def test_free_column_any_row(self):
        b = Board()
        # Column 8 is FREE, throw 1
        valid = b.valid_rows_for_col(8)
        assert set(valid) == set(range(NUM_ROWS))

        b.fill(8, 6, [3, 3, 3, 1, 2])  # 3er-Pasch
        valid2 = b.valid_rows_for_col(8)
        assert 6 not in valid2
        assert len(valid2) == NUM_ROWS - 1

    def test_cannot_fill_wrong_row_in_down_col(self):
        b = Board()
        with pytest.raises(ValueError):
            b.fill(0, 5, [6, 6, 6, 6, 6])  # row 5 not valid yet

    def test_column_total_with_bonus(self):
        b = Board()
        # Fill all upper rows of column 8 (FREE) with high scores
        b.fill(8, 0, [1, 1, 1, 1, 1])   # 5
        b.fill(8, 1, [2, 2, 2, 2, 2])   # 10
        b.fill(8, 2, [3, 3, 3, 3, 3])   # 15
        b.fill(8, 3, [4, 4, 4, 4, 4])   # 20
        b.fill(8, 4, [5, 5, 5, 5, 5])   # 25
        # Sum = 75 → bonus triggered
        upper_sum = sum(b.grid[8][r] for r in range(5))
        assert upper_sum == 75
        # Column total should include bonus
        ct = b.column_total(8)
        assert ct >= 75 + 35

    def test_is_complete(self):
        b = Board()
        assert not b.is_complete()
        # Fill everything
        for c in range(NUM_COLS):
            while b.valid_rows_for_col(c):
                r = b.valid_rows_for_col(c)[0]
                b.fill(c, r, [1, 2, 3, 4, 5])
        assert b.is_complete()


# ──────────────────────────────────────────────────────────────────────────────
# Bot integration test
# ──────────────────────────────────────────────────────────────────────────────

class TestBot:
    def test_full_game_completes(self):
        from kniffel.game import Game
        g = Game(verbose=False)
        r = g.play_full_game()
        assert r.grand_total > 0
        assert len(r.turn_logs) == NUM_COLS * NUM_ROWS

    def test_bot_produces_reasoning(self):
        from kniffel.bot import KniffellBot
        bot   = KniffellBot()
        board = Board()
        dec   = bot.decide_reroll(board, [1, 2, 3, 4, 5], throw_number=1)
        assert isinstance(dec.reasoning, str)
        assert len(dec.reasoning) > 10

        pdec = bot.decide_placement(board, [1, 2, 3, 4, 5])
        assert isinstance(pdec.reasoning, str)
        assert pdec.score >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
