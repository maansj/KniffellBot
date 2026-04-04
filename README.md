# 🎲 Kniffel Bot

A Python AI bot that plays **Kniffel** (the German variant of Yatzy), using
greedy expected-value maximisation with full **teaching explanations** for
every decision it makes.

---

## Table of Contents

1. [Game Rules Overview](#game-rules-overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Running Modes](#running-modes)
6. [Bot Strategy Explained](#bot-strategy-explained)
7. [Teaching Feature](#teaching-feature)
8. [API Reference](#api-reference)
9. [Running Tests](#running-tests)
10. [Learning from the Bot](#learning-from-the-bot)

---

## Game Rules Overview

Kniffel uses **5 six-sided dice** and a **13 × 12 scoresheet**.

### Scoresheet Layout

The sheet has **12 columns**, grouped into 3 types across **4 throws (Würfe)**:

| Symbol | Name  | Fill Order           |
|--------|-------|----------------------|
| ↓      | DOWN  | Top → Bottom (strict)|
| ↑      | UP    | Bottom → Top (strict)|
| F      | FREE  | Any row, any time    |

So: columns 1–4 are ↓, columns 5–8 are ↑, columns 9–12 are F (Free).

### Rows (13 per column)

**Upper section**

| Row   | Score                       |
|-------|-----------------------------|
| 1er   | Sum of all 1s               |
| 2er   | Sum of all 2s               |
| 3er   | Sum of all 3s               |
| 4er   | Sum of all 4s               |
| 5er   | Sum of all 5s               |
| 6er   | Sum of all 6s               |
| Bonus | +35 if upper sum ≥ 63       |

**Lower section**

| Row        | Score                       |
|------------|-----------------------------|
| 3er-Pasch  | Sum of all dice (≥3 same)   |
| 4er-Pasch  | Sum of all dice (≥4 same)   |
| Full-House | 25 pts (2 + 3 of same kind) |
| kl.Straße  | 30 pts (4 consecutive)      |
| gr.Straße  | 40 pts (5 consecutive)      |
| Kniffel    | 50 pts (5 of a kind)        |
| Chance     | Sum of all dice             |

### Turn Mechanics

Each turn you may roll up to **4 times**. After each roll you choose which dice
to keep (hold) and which to re-roll. Then you must place the result in an
available cell on your sheet.

**156 turns total** = 13 rows × 12 columns.

---

## Project Structure

```
kniffel_bot/
├── kniffel/
│   ├── __init__.py        # Package exports
│   ├── constants.py       # All game constants (rows, columns, scoring values)
│   ├── scoring.py         # Pure scoring functions
│   ├── board.py           # Board state management (13×12 grid)
│   ├── dice_utils.py      # Dice rolling & expected-value calculations
│   ├── bot.py             # KniffellBot – AI decisions + teaching reasoning
│   ├── game.py            # Full game simulation engine
│   └── stats.py           # Multi-game statistics & JSON logging
├── tests/
│   └── test_scoring.py    # Pytest unit tests
├── logs/                  # JSON game logs (auto-created)
├── main.py                # CLI entry point
├── requirements.txt
└── README.md
```

---

## Installation

Python 3.10+ required. No external dependencies for core play.

```bash
# Clone the repo
git clone https://github.com/your-username/kniffel_bot.git
cd kniffel_bot

# (Optional) create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install test dependency
pip install -r requirements.txt
```

---

## Quick Start

```python
from kniffel.board import Board
from kniffel.bot import KniffellBot
from kniffel.dice_utils import roll_dice, reroll

board = Board()
bot   = KniffellBot()

# --- one turn ---
dice      = roll_dice()
throw_num = 1

while throw_num <= 4:
    decision = bot.decide_reroll(board, dice, throw_num)
    print(decision.reasoning)           # 🎓 teaching output

    if not decision.reroll:
        break                           # bot is happy with the dice

    dice      = reroll(decision.kept, len(decision.reroll))
    throw_num += 1

placement = bot.decide_placement(board, dice)
print(placement.reasoning)             # 🎓 teaching output

board.fill(placement.col_idx, placement.row_idx, dice)
print(board.display())
```

---

## Running Modes

### 1 · Demo — one verbose game

```bash
python main.py demo
```

Prints every roll, every re-roll decision with reasoning, and the final board.

---

### 2 · Simulate — statistical benchmark

```bash
python main.py simulate 200
```

Runs 200 silent games and prints:

```
==================================================
  Kniffel Bot — Simulation Summary (200 games)
==================================================
  Mean score  : 847.3
  Median score: 851.0
  Std dev     : 62.1
  Min score   : 681
  Max score   : 1012
==================================================

Score distribution:
--------------------------------------------------
  681-742  | ████                          8
  742-803  | █████████                     18
  803-864  | ██████████████████████████    52
  ...
```

---

### 3 · Log — save full turn-by-turn JSON

```bash
python main.py log
```

Creates `logs/game_YYYYMMDD_HHMMSS.json` — a complete record of every
throw, re-roll decision, expected value, and reasoning string for every turn.

**Example entry:**

```json
{
  "turn": 42,
  "final_dice": [4, 4, 4, 4, 4],
  "rerolls": [
    {
      "throw": 1,
      "kept": [4, 4, 4],
      "rerolled": [2, 5],
      "target_row": 11,
      "expected_value": 38.4,
      "reasoning": "Targeting 'Kniffel' in Wurf 2 [F]. Keeping [4, 4, 4] ..."
    }
  ],
  "placement": {
    "col_label": "Wurf 2 [F]",
    "row_name": "Kniffel",
    "score": 50,
    "reasoning": "Placing [4, 4, 4, 4, 4] → 'Kniffel' in Wurf 2 [F] for 50 pts. 🏆 Kniffel!"
  }
}
```

---

### 4 · Interactive — human plays with bot coaching

```bash
python main.py interactive
```

You enter your dice values; the bot suggests what to keep and where to place.
You can follow or override the advice.

---

## Bot Strategy Explained

### Step 1 — Slot selection (which cell to target this turn)

For every available `(column, row)` slot the bot computes a **slot value**:

```
slot_value = (expected_score + bonus_boost) × column_urgency
```

- **expected_score** — EV of the best keep strategy for that row (via exhaustive
  enumeration of all 32 subsets of 5 dice)
- **bonus_boost** — extra value for upper-section rows when the 35-pt bonus
  is within reach
- **column_urgency** — ↓/↑ columns are more urgent than FREE columns because
  they force a specific next row; a high-value forced row earns a multiplier

### Step 2 — Re-roll selection (which dice to keep)

Given the target slot, the bot enumerates all **2⁵ = 32 subsets** of the
current dice to keep, computes the exact expected score for each subset
(by iterating all 6^k outcomes for k re-rolled dice), and picks the subset
with the highest EV.

### Step 3 — Early stop

If the current score for the target slot is ≥ 95% of the re-roll EV, the
bot stops and places immediately rather than risking a worse outcome.

---

## Teaching Feature

Every `RerollDecision` and `PlacementDecision` object has a `.reasoning`
string in plain English. Example outputs:

**Re-roll:**
> Targeting 'Kniffel' in Wurf 3 [F]. Keeping [5, 5, 5] and re-rolling 2 dice
> gives an expected value of 18.3 pts for 'Kniffel'. (adjusted EV incl.
> urgency/bonus: 18.3 pts)

**Placement:**
> Placing [3, 3, 3, 5, 6] → '3er-Pasch' in Wurf 1 [↓] for 20 pts. Sum of all
> dice = 20 pts. ↓ DOWN column: row 7/13 filled; next fill must be row 8/13.

These explanations highlight:

- **Why this slot?** — EV, bonus proximity, column urgency
- **Why these dice kept?** — Expected value gain from re-rolling vs holding
- **What combinations are being pursued** — straight, full house, Kniffel
- **Column constraints** — which rows must come next in ↓/↑ columns

---

## API Reference

### `KniffellBot`

```python
bot = KniffellBot(verbose=True)

decision = bot.decide_reroll(board, dice, throw_number)
# Returns RerollDecision(kept, reroll, target_col, target_row,
#                        expected_value, throw_number, reasoning)

decision = bot.decide_placement(board, dice, current_throw=4)
# Returns PlacementDecision(col_idx, row_idx, row_name, col_label,
#                           score, reasoning)
```

### `Board`

```python
board = Board()
board.valid_rows_for_col(col_idx)   # list of valid row indices
board.can_fill(col_idx, row_idx)    # bool
board.fill(col_idx, row_idx, dice)  # returns score placed
board.grand_total()                 # int
board.is_complete()                 # bool
board.display()                     # formatted string table
```

### `Game`

```python
game = Game(verbose=True)
result = game.play_full_game()
# result.grand_total, result.column_totals, result.turn_logs,
# result.board_display
```

### `stats` module

```python
from kniffel.stats import run_simulations, summarise, print_summary, save_game_log
results = run_simulations(n=100)
summary = summarise(results)
print_summary(summary)
save_game_log(results[0], Path("logs/best_game.json"))
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover scoring correctness, board fill-order constraints, bonus
calculation, and a full-game integration smoke test.

---

## Learning from the Bot

Here are the key lessons the bot's reasoning will teach you:

| Situation | Bot lesson |
|-----------|-----------|
| Three-of-a-kind on first throw | Keep the triple, re-roll 2 for Kniffel or 4-of-a-kind |
| 4-straight on first throw | Keep the 4, re-roll 1 aiming for large straight (1-in-3 chance) |
| Close to 63-pt bonus | Prioritise upper-section rows even at slight EV cost |
| ↓ DOWN column at row 12 (Chance) | Any dice is valid — place freely without pressure |
| ↑ UP column: Kniffel is next | High urgency — commit throws toward 5-of-a-kind |
| Sacrifice placement (score 0) | Sometimes mandatory to keep board legal; accept the loss gracefully |

Study the JSON logs to identify patterns in high-scoring games vs low-scoring
games. The `turn_logs` field lists every decision with its reasoning, making
it easy to spot where gains were missed.
