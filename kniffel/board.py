"""
board.py
========
Manages the 13×12 Kniffel scoresheet state.

Internal storage
----------------
self.grid[col][row]  = None (unfilled) or int (score)

Column indices  0-3  : DOWN columns (throw 1-4)
Column indices  4-7  : UP   columns (throw 1-4)
Column indices  8-11 : FREE columns (throw 1-4)

Within each column:
  DOWN: pointer starts at 0, advances downward  (0→12)
  UP  : pointer starts at 12, advances upward   (12→0)
  FREE: any unfilled row is valid
"""

from __future__ import annotations
from copy import deepcopy
from kniffel.constants import (
    ALL_ROWS, NUM_ROWS, NUM_COLS, COLUMNS, ROW_IDX,
    DOWN, UP, FREE, NUM_THROWS,
    UPPER_BONUS_THRESHOLD, UPPER_BONUS_VALUE,
)
from kniffel.scoring import score_dice, compute_bonus


class Board:
    """Represents a single player's 13×12 scoresheet."""

    def __init__(self):
        # grid[col_idx][row_idx] = score or None
        self.grid: list[list[int | None]] = [
            [None] * NUM_ROWS for _ in range(NUM_COLS)
        ]
        # Pointer for DOWN columns: next row to fill (starts at 0)
        self._down_ptr: list[int] = [0] * NUM_THROWS  # one per throw-number
        # Pointer for UP   columns: next row to fill (starts at NUM_ROWS-1)
        self._up_ptr:   list[int] = [NUM_ROWS - 1] * NUM_THROWS

    # ──────────────────────────────────────────────
    # Column helpers
    # ──────────────────────────────────────────────

    @staticmethod
    def _col_type(col_idx: int):
        """Return the column type (DOWN / UP / FREE) for a given col index."""
        return COLUMNS[col_idx][1]

    @staticmethod
    def _throw_num(col_idx: int) -> int:
        """Return 1-based throw number for column index."""
        return COLUMNS[col_idx][0]

    def valid_rows_for_col(self, col_idx: int) -> list[int]:
        """
        Return sorted list of row indices that are currently valid
        (i.e. can be filled next) for the given column.
        """
        col_type = self._col_type(col_idx)
        throw_idx = self._throw_num(col_idx) - 1

        if col_type == DOWN:
            ptr = self._down_ptr[throw_idx]
            return [ptr] if ptr < NUM_ROWS else []

        elif col_type == UP:
            ptr = self._up_ptr[throw_idx]
            return [ptr] if ptr >= 0 else []

        else:  # FREE
            return [r for r in range(NUM_ROWS) if self.grid[col_idx][r] is None]

    def can_fill(self, col_idx: int, row_idx: int) -> bool:
        return row_idx in self.valid_rows_for_col(col_idx)

    # ──────────────────────────────────────────────
    # Fill a cell
    # ──────────────────────────────────────────────

    def fill(self, col_idx: int, row_idx: int, dice: list[int]) -> int:
        """
        Fill cell (col_idx, row_idx) with the score for *dice* in that row.
        Returns the score placed (0 if combination didn't qualify).
        Raises ValueError if the cell is not a valid choice.
        """
        if not self.can_fill(col_idx, row_idx):
            raise ValueError(
                f"Cannot fill col={col_idx} row={row_idx} "
                f"(valid rows: {self.valid_rows_for_col(col_idx)})"
            )
        sc = score_dice(dice, ALL_ROWS[row_idx])
        self.grid[col_idx][row_idx] = sc

        # Advance pointer
        col_type  = self._col_type(col_idx)
        throw_idx = self._throw_num(col_idx) - 1
        if col_type == DOWN:
            self._down_ptr[throw_idx] += 1
        elif col_type == UP:
            self._up_ptr[throw_idx] -= 1

        return sc

    # ──────────────────────────────────────────────
    # Score summaries
    # ──────────────────────────────────────────────

    def column_total(self, col_idx: int) -> int:
        """Total score for one column (including bonus if applicable)."""
        cells = self.grid[col_idx]
        upper_sum = sum(cells[r] for r in range(6) if cells[r] is not None)
        lower_sum = sum(cells[r] for r in range(6, NUM_ROWS) if cells[r] is not None)
        bonus = compute_bonus(upper_sum)
        return upper_sum + bonus + lower_sum

    def grand_total(self) -> int:
        return sum(self.column_total(c) for c in range(NUM_COLS))

    def is_complete(self) -> bool:
        return all(
            self.grid[c][r] is not None
            for c in range(NUM_COLS)
            for r in range(NUM_ROWS)
        )

    def filled_count(self) -> int:
        return sum(
            1 for c in range(NUM_COLS)
            for r in range(NUM_ROWS)
            if self.grid[c][r] is not None
        )

    # ──────────────────────────────────────────────
    # Serialisation / display
    # ──────────────────────────────────────────────

    def display(self) -> str:
        """Return a formatted string table of the current scoresheet."""
        col_labels = []
        for t, ctype in COLUMNS:
            symbol = {"DOWN": "↓", "UP": "↑", "FREE": "F"}[ctype]
            col_labels.append(f"W{t}{symbol}")

        header = f"{'Row':<14}" + "".join(f"{lbl:>6}" for lbl in col_labels)
        lines  = [header, "-" * len(header)]

        for r_idx, row_name in enumerate(ALL_ROWS):
            row_str = f"{row_name:<14}"
            for c_idx in range(NUM_COLS):
                val = self.grid[c_idx][r_idx]
                row_str += f"{'—' if val is None else val:>6}"
            lines.append(row_str)

        # Column totals
        lines.append("-" * len(header))
        total_str = f"{'TOTAL':<14}"
        for c_idx in range(NUM_COLS):
            total_str += f"{self.column_total(c_idx):>6}"
        lines.append(total_str)
        lines.append(f"\nGrand Total: {self.grand_total()}")
        return "\n".join(lines)

    def clone(self) -> "Board":
        return deepcopy(self)
