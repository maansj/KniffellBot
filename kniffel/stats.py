"""
stats.py
========
Run N simulations and produce summary statistics + a visualisation.
"""

from __future__ import annotations
import json
import statistics
import logging
from pathlib import Path
from datetime import datetime

from kniffel.game import Game, GameResult

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Run simulations
# ──────────────────────────────────────────────────────────────────────────────

def run_simulations(n: int = 100, verbose: bool = False) -> list[GameResult]:
    """Simulate *n* full games and return results."""
    results = []
    for i in range(n):
        g = Game(verbose=verbose)
        r = g.play_full_game()
        results.append(r)
        if (i + 1) % max(1, n // 10) == 0:
            logger.info(f"  Simulated {i+1}/{n} games …")
    return results


def summarise(results: list[GameResult]) -> dict:
    scores = [r.grand_total for r in results]
    return {
        "n_games":   len(scores),
        "mean":      round(statistics.mean(scores), 1),
        "median":    statistics.median(scores),
        "stdev":     round(statistics.stdev(scores), 1) if len(scores) > 1 else 0,
        "min":       min(scores),
        "max":       max(scores),
        "scores":    scores,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Text report
# ──────────────────────────────────────────────────────────────────────────────

def print_summary(summary: dict):
    print("\n" + "=" * 50)
    print(f"  Kniffel Bot — Simulation Summary ({summary['n_games']} games)")
    print("=" * 50)
    print(f"  Mean score  : {summary['mean']}")
    print(f"  Median score: {summary['median']}")
    print(f"  Std dev     : {summary['stdev']}")
    print(f"  Min score   : {summary['min']}")
    print(f"  Max score   : {summary['max']}")
    print("=" * 50)


# ──────────────────────────────────────────────────────────────────────────────
# Save JSON log of a full game
# ──────────────────────────────────────────────────────────────────────────────

def save_game_log(result: GameResult, path: Path):
    """Save a human-readable JSON log of every turn decision."""
    turns = []
    for tl in result.turn_logs:
        turns.append({
            "turn":       tl.turn_number,
            "final_dice": tl.final_dice,
            "rerolls": [
                {
                    "throw":    rd.throw_number,
                    "dice_before_reroll": rd.kept + rd.reroll,
                    "kept":     rd.kept,
                    "rerolled": rd.reroll,
                    "target_row":  rd.target_row,
                    "expected_value": round(rd.expected_value, 2),
                    "reasoning": rd.reasoning,
                }
                for rd in tl.reroll_decisions
            ],
            "placement": {
                "col_label": tl.placement.col_label,
                "row_name":  tl.placement.row_name,
                "score":     tl.placement.score,
                "reasoning": tl.placement.reasoning,
            } if tl.placement else None,
        })
    data = {
        "timestamp":    datetime.now().isoformat(),
        "grand_total":  result.grand_total,
        "column_totals": result.column_totals,
        "turns": turns,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info(f"Game log saved → {path}")


# ──────────────────────────────────────────────────────────────────────────────
# ASCII histogram
# ──────────────────────────────────────────────────────────────────────────────

def ascii_histogram(scores: list[int], bins: int = 10) -> str:
    if not scores:
        return ""
    lo, hi  = min(scores), max(scores)
    width   = max(1, (hi - lo) // bins)
    buckets = {}
    for s in scores:
        b = ((s - lo) // width) * width + lo
        buckets[b] = buckets.get(b, 0) + 1

    max_count = max(buckets.values())
    bar_w     = 30
    lines     = ["\nScore distribution:", "-" * 50]
    for bucket in sorted(buckets):
        bar    = "█" * int(buckets[bucket] / max_count * bar_w)
        label  = f"{bucket:>5}-{bucket+width-1:<5}"
        lines.append(f"  {label} | {bar} {buckets[bucket]}")
    return "\n".join(lines)
