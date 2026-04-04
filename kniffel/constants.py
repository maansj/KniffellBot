"""
constants.py
============
All game constants for Kniffel (German Yatzy variant).

Board layout mirrors the PDF scoresheet:
- 4 "throws" (Wurf), each with 3 column types: DOWN (↓), UP (↑), FREE (F)
- 12 total columns, 13 scoring rows each
- DOWN columns fill top→bottom, UP columns fill bottom→top, FREE fills any row
"""

# ──────────────────────────────────────────────
# Row definitions
# ──────────────────────────────────────────────

# Upper section (index 0-5)
UPPER_ROWS = ["1er", "2er", "3er", "4er", "5er", "6er"]

# Lower section (index 6-12)
LOWER_ROWS = [
    "3er-Pasch",   # Three-of-a-kind  → sum of all dice
    "4er-Pasch",   # Four-of-a-kind   → sum of all dice
    "Full-House",  # Full house        → 25 pts
    "kl.Straße",   # Small straight    → 30 pts
    "gr.Straße",   # Large straight    → 40 pts
    "Kniffel",     # Yatzy             → 50 pts
    "Chance",      # Any dice          → sum of all dice
]

ALL_ROWS = UPPER_ROWS + LOWER_ROWS
NUM_ROWS = len(ALL_ROWS)          # 13

# Row indices for quick lookup
ROW_IDX = {name: i for i, name in enumerate(ALL_ROWS)}

# ──────────────────────────────────────────────
# Column definitions
# ──────────────────────────────────────────────

# Column types
DOWN = "DOWN"   # ↓  Must fill top→bottom
UP   = "UP"     # ↑  Must fill bottom→top
FREE = "FREE"   # F  Any row, any time

NUM_THROWS = 4   # 4 throws per column type
NUM_COL_TYPES = 3
NUM_COLS = NUM_THROWS * NUM_COL_TYPES  # 12 columns total

# Column layout: list of (throw_number, column_type) pairs, 0-indexed
#   Columns 0-3  : throw 1-4, type DOWN
#   Columns 4-7  : throw 1-4, type UP
#   Columns 8-11 : throw 1-4, type FREE
COLUMNS = []
for t in range(NUM_THROWS):
    COLUMNS.append((t + 1, DOWN))
for t in range(NUM_THROWS):
    COLUMNS.append((t + 1, UP))
for t in range(NUM_THROWS):
    COLUMNS.append((t + 1, FREE))

# ──────────────────────────────────────────────
# Dice constants
# ──────────────────────────────────────────────

NUM_DICE = 5
MAX_THROWS_PER_TURN = 4
DICE_FACES = [1, 2, 3, 4, 5, 6]

# ──────────────────────────────────────────────
# Scoring constants
# ──────────────────────────────────────────────

UPPER_BONUS_THRESHOLD = 63   # ≥63 → +35 bonus (standard Yatzy rule)
UPPER_BONUS_VALUE = 35

FULL_HOUSE_SCORE   = 25
SMALL_STRAIGHT_SCORE = 30
LARGE_STRAIGHT_SCORE = 40
KNIFFEL_SCORE      = 50

# ──────────────────────────────────────────────
# Fill-order constraints
# ──────────────────────────────────────────────
# For DOWN columns: next available row index is tracked (increases 0→12)
# For UP   columns: next available row index is tracked (decreases 12→0)
# For FREE columns: any unfilled row is valid

DOWN_FILL_ORDER = list(range(NUM_ROWS))          # 0, 1, 2, … 12
UP_FILL_ORDER   = list(range(NUM_ROWS - 1, -1, -1))  # 12, 11, … 0
