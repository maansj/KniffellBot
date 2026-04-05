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

    def valid_rows_for_col(self, col_idx: int, current_throw: int = 1) -> list[int]:
        """
        Return sorted list of row indices that are currently valid
        (i.e. can be filled next) for the given column.

        Wurf N columns can ONLY be filled when current_throw == N exactly.
        - Wurf 1: placed after rolling once (no re-rolls)
        - Wurf 2: placed after rolling twice (1 re-roll)
        - Wurf 3: placed after rolling three times (2 re-rolls)
        - Wurf 4: placed after rolling four times (3 re-rolls)
        """
        col_wurf  = self._throw_num(col_idx)   # 1-based Wurf number of this column
        if current_throw != col_wurf:
            return []                           # must match exactly

        col_type  = self._col_type(col_idx)
        throw_idx = col_wurf - 1

        if col_type == DOWN:
            ptr = self._down_ptr[throw_idx]
            return [ptr] if ptr < NUM_ROWS else []

        elif col_type == UP:
            ptr = self._up_ptr[throw_idx]
            return [ptr] if ptr >= 0 else []

        else:  # FREE
            return [r for r in range(NUM_ROWS) if self.grid[col_idx][r] is None]

    def can_fill(self, col_idx: int, row_idx: int, current_throw: int = 1) -> bool:
        return row_idx in self.valid_rows_for_col(col_idx, current_throw)

    # ──────────────────────────────────────────────
    # Fill a cell
    # ──────────────────────────────────────────────

    def fill(self, col_idx: int, row_idx: int, dice: list[int], current_throw: int = 1) -> int:
        """
        Fill cell (col_idx, row_idx) with the score for *dice* in that row.
        Returns the score placed (0 if combination didn't qualify).
        Raises ValueError if the cell is not a valid choice.
        current_throw enforces that Wurf N columns are only fillable after throw N.
        """
        if not self.can_fill(col_idx, row_idx, current_throw):
            raise ValueError(
                f"Cannot fill col={col_idx} row={row_idx} "
                f"(valid rows at throw {current_throw}: {self.valid_rows_for_col(col_idx, current_throw)})"
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
        """
        Return a formatted scoresheet grouped by throw:
          W1↓  W1↑  W1F | W2↓  W2↑  W2F | W3↓  W3↑  W3F | W4↓  W4↑  W4F
        """
        SYM = {DOWN: "↓", UP: "↑", FREE: "F"}

        # Build display order: for each throw 1-4, show ↓ ↑ F
        # Map (throw, ctype) → internal col_idx
        col_map: dict[tuple, int] = {}
        for c_idx, (t, ctype) in enumerate(COLUMNS):
            col_map[(t, ctype)] = c_idx

        display_order: list[int] = []  # col indices in display order
        display_labels: list[str] = []
        for t in range(1, NUM_THROWS + 1):
            for ctype in (DOWN, UP, FREE):
                display_order.append(col_map[(t, ctype)])
                display_labels.append(f"W{t}{SYM[ctype]}")

        COL_W  = 5   # width per data column
        ROW_W  = 12  # width of row-name column

        # ── header ──────────────────────────────────────────────────────────
        # Throw group labels  (W1 spans 3 cols, etc.)
        group_w = COL_W * 3
        throw_hdr = " " * ROW_W
        for t in range(1, NUM_THROWS + 1):
            label = f" Wurf {t} "
            throw_hdr += label.center(group_w)

        col_hdr = " " * ROW_W
        for i, lbl in enumerate(display_labels):
            col_hdr += lbl.center(COL_W)
            if i % 3 == 2 and i < len(display_labels) - 1:
                col_hdr += " "   # small gap between throw groups

        sep_inner = "─" * (COL_W * 3)
        separator = "─" * ROW_W + ("┼" + sep_inner) * NUM_THROWS

        lines = [throw_hdr, col_hdr, separator]

        # ── upper section rows ───────────────────────────────────────────────
        for r_idx in range(6):
            row_name = ALL_ROWS[r_idx]
            row_str  = f"{row_name:<{ROW_W}}"
            for i, c_idx in enumerate(display_order):
                val = self.grid[c_idx][r_idx]
                cell = "·" if val is None else str(val)
                row_str += cell.center(COL_W)
                if i % 3 == 2 and i < len(display_order) - 1:
                    row_str += " "
            lines.append(row_str)

        # ── bonus row ────────────────────────────────────────────────────────
        bonus_str = f"{'Bonus':<{ROW_W}}"
        for i, c_idx in enumerate(display_order):
            upper_sum = sum(
                self.grid[c_idx][r] for r in range(6)
                if self.grid[c_idx][r] is not None
            )
            bonus = compute_bonus(upper_sum)
            # Show bonus value only once all upper rows in the column are filled,
            # otherwise show the running deficit / earned amount
            filled_upper = sum(1 for r in range(6) if self.grid[c_idx][r] is not None)
            if filled_upper == 6:
                cell = str(bonus)
            else:
                needed = max(0, UPPER_BONUS_THRESHOLD - upper_sum)
                cell = f"-{needed}" if needed > 0 else "+35"
            bonus_str += cell.center(COL_W)
            if i % 3 == 2 and i < len(display_order) - 1:
                bonus_str += " "
        lines.append(bonus_str)

        lines.append(separator)

        # ── lower section rows ───────────────────────────────────────────────
        for r_idx in range(6, NUM_ROWS):
            row_name = ALL_ROWS[r_idx]
            row_str  = f"{row_name:<{ROW_W}}"
            for i, c_idx in enumerate(display_order):
                val = self.grid[c_idx][r_idx]
                cell = "·" if val is None else str(val)
                row_str += cell.center(COL_W)
                if i % 3 == 2 and i < len(display_order) - 1:
                    row_str += " "
            lines.append(row_str)

        lines.append(separator)

        # ── column totals ────────────────────────────────────────────────────
        total_str = f"{'TOTAL':<{ROW_W}}"
        for i, c_idx in enumerate(display_order):
            total_str += str(self.column_total(c_idx)).center(COL_W)
            if i % 3 == 2 and i < len(display_order) - 1:
                total_str += " "
        lines.append(total_str)
        lines.append(f"\n  Grand Total: {self.grand_total()} pts")
        return "\n".join(lines)

    def clone(self) -> "Board":
        return deepcopy(self)
