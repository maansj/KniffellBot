#!/usr/bin/env python3
"""
main.py
=======
Entry point for the Kniffel bot.

Modes
-----
  python main.py demo          – play one verbose game, print board + reasoning
  python main.py simulate N    – run N silent games, print score statistics
  python main.py log           – play one game, save full JSON turn log
  python main.py interactive   – human plays with bot suggestions

Run  python main.py --help  for details.
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

# ── project imports ───────────────────────────────────────────────────────────
from kniffel.board import Board
from kniffel.bot import KniffellBot
from kniffel.game import Game
from kniffel.stats import (
    run_simulations, summarise, print_summary, ascii_histogram, save_game_log,
)
from kniffel.dice_utils import roll_dice, reroll
from kniffel.constants import ALL_ROWS, COLUMNS, DOWN, UP, FREE


# ── logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(message)s",
    stream = sys.stdout,
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# CLI subcommands
# ──────────────────────────────────────────────────────────────────────────────

def cmd_demo(args):
    """Play one game with full verbose output."""
    print("\n🎲  Kniffel Bot — Demo Game\n")
    g = Game(verbose=True)
    r = g.play_full_game()
    print("\n" + r.board_display)
    print(f"\n🏆  Final grand total: {r.grand_total} pts")


def cmd_simulate(args):
    """Run N silent games and print statistics."""
    n = int(args.n)
    print(f"\n🎲  Simulating {n} games …\n")
    results  = run_simulations(n, verbose=False)
    summary  = summarise(results)
    print_summary(summary)
    print(ascii_histogram(summary["scores"]))


def cmd_log(args):
    """Play one game and save a full JSON turn log."""
    print("\n🎲  Playing one game and saving log …\n")
    g = Game(verbose=False)
    r = g.play_full_game()
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path("logs") / f"game_{ts}.json"
    save_game_log(r, path)
    print(r.board_display)
    print(f"\n🏆  Grand total: {r.grand_total} pts")
    print(f"📄  Full turn log saved to: {path}")


def cmd_interactive(args):
    """
    Human plays with bot suggestions.
    The human rolls the dice themselves and enters the values; the bot
    advises on re-rolls and placement.
    """
    print("\n🎲  Kniffel Bot — Interactive Mode")
    print("    You roll the dice; the bot advises.\n")

    board = Board()
    bot   = KniffellBot(verbose=True)
    turn  = 0
    total_turns = len(COLUMNS) * len(ALL_ROWS)

    while not board.is_complete():
        turn += 1
        print(f"\n{'─'*60}")
        print(f"  Turn {turn} / {total_turns}")
        print(f"  Board so far ({board.filled_count()} / {total_turns} cells filled)")
        print(board.display())

        dice = _ask_dice("  Enter your initial roll (5 numbers separated by spaces): ")
        throw_num = 1

        while throw_num <= 4:
            decision = bot.decide_reroll(board, dice, throw_num)
            print(f"\n  🤖 Bot says: {decision.reasoning}")

            if not decision.reroll:
                break

            again = input("  Re-roll as suggested? [Y/n]: ").strip().lower()
            if again in ("", "y"):
                dice = reroll(decision.kept, len(decision.reroll))
                print(f"  New dice: {dice}")
            else:
                custom = _ask_dice("  Enter your new dice values: ")
                dice = custom
            throw_num += 1

        placement = bot.decide_placement(board, dice, throw_num)
        print(f"\n  🤖 Bot recommends: {placement.reasoning}")

        agree = input("  Accept placement? [Y/n]: ").strip().lower()
        if agree in ("", "y"):
            board.fill(placement.col_idx, placement.row_idx, dice)
        else:
            # Let human choose manually
            _manual_placement(board, dice)

    print("\n" + board.display())
    print(f"\n🏆  Final grand total: {board.grand_total()} pts")


def _ask_dice(prompt: str) -> list[int]:
    while True:
        try:
            vals = list(map(int, input(prompt).split()))
            if len(vals) == 5 and all(1 <= v <= 6 for v in vals):
                return sorted(vals)
            print("  Please enter exactly 5 values between 1 and 6.")
        except ValueError:
            print("  Invalid input — use space-separated integers.")


def _manual_placement(board: Board, dice: list[int]):
    """Ask human to pick a column and row manually."""
    print("  Available placements:")
    options = []
    for c in range(len(COLUMNS)):
        for r in board.valid_rows_for_col(c):
            throw_n, ctype = COLUMNS[c]
            sym = {DOWN: "↓", UP: "↑", FREE: "F"}[ctype]
            row_name = ALL_ROWS[r]
            from kniffel.scoring import score_dice
            sc = score_dice(dice, row_name)
            options.append((c, r))
            print(f"  [{len(options)-1:>3}] Wurf{throw_n}[{sym}] / {row_name:<15} → {sc} pts")

    while True:
        try:
            idx = int(input("  Choose option number: "))
            if 0 <= idx < len(options):
                c, r = options[idx]
                board.fill(c, r, dice)
                return
        except ValueError:
            pass
        print("  Invalid choice.")


# ──────────────────────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = "kniffel_bot",
        description = "Kniffel AI Bot — demo, simulate, log, or play interactively.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("demo",
        help="Play one verbose demo game and print the reasoning.")

    sim = sub.add_parser("simulate",
        help="Run N silent games and print score statistics.")
    sim.add_argument("n", nargs="?", default=50,
        help="Number of games to simulate (default: 50)")

    sub.add_parser("log",
        help="Play one game and save a full JSON turn log to logs/.")

    sub.add_parser("interactive",
        help="Human plays with bot suggestions — enter your own dice rolls.")

    return p


if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()

    dispatch = {
        "demo":        cmd_demo,
        "simulate":    cmd_simulate,
        "log":         cmd_log,
        "interactive": cmd_interactive,
    }
    dispatch[args.command](args)
