#!/usr/bin/env python3
"""
main.py - Entry point for the Kniffel bot.

Modes:
  python main.py demo          – play one verbose game
  python main.py simulate N    – run N silent games, print statistics
  python main.py log           – play one game, save full JSON turn log
  python main.py interactive   – human plays with bot suggestions
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime

from kniffel.board import Board
from kniffel.bot import KniffellBot
from kniffel.game import Game
from kniffel.stats import (
    run_simulations, summarise, print_summary, ascii_histogram, save_game_log,
)
from kniffel.dice_utils import roll_dice, reroll
from kniffel.constants import ALL_ROWS, COLUMNS, DOWN, UP, FREE, NUM_COLS

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# CLI subcommands
# ──────────────────────────────────────────────────────────────────────────────

def cmd_demo(args):
    print("\n🎲  Kniffel Bot — Demo Game\n")
    g = Game(verbose=True)
    r = g.play_full_game()
    print("\n" + r.board_display)
    print(f"\n🏆  Final grand total: {r.grand_total} pts")


def cmd_simulate(args):
    n = int(args.n)
    print(f"\n🎲  Simulating {n} games …\n")
    results = run_simulations(n, verbose=False)
    summary = summarise(results)
    print_summary(summary)
    print(ascii_histogram(summary["scores"]))


def cmd_log(args):
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

    Each turn:
      1. Roll dice (digitally or enter manually)
      2. Bot recommends which Wurf (1-4) to target — i.e. how many rolls to take
         Wurf 1 = place immediately, Wurf 2 = re-roll once, etc.
      3. Re-roll the suggested dice (up to target_wurf - 1 times)
      4. Bot recommends where to place; player can accept or override
    """
    print("\n🎲  Kniffel Bot — Interactive Mode")
    print("    The bot advises on which Wurf to target, re-rolls, and placement.\n")
    print("  Reminder: Wurf N = you rolled exactly N times this turn.")
    print("  Wurf 1 cols = placed after 1 roll, Wurf 2 = after 2 rolls, etc.\n")

    while True:
        mode = input("  Roll dice digitally or enter them manually? [d/m]: ").strip().lower()
        if mode in ("d", "m"):
            break
        print("  Please enter 'd' for digital or 'm' for manual.")

    digital = (mode == "d")
    print(f"  ✅ {'Digital' if digital else 'Manual'} mode.\n")

    board      = Board()
    bot        = KniffellBot(verbose=True)
    turn       = 0
    total_turns = len(COLUMNS) * len(ALL_ROWS)

    while not board.is_complete():
        turn += 1
        print(f"\n{'─'*60}")
        print(f"  Turn {turn} / {total_turns}  "
              f"({board.filled_count()} / {total_turns} cells filled)")
        print(board.display())

        # ── Step 1: initial roll ──────────────────────────────────────────
        if digital:
            dice = roll_dice()
            print(f"\n  🎲 Roll 1: {dice}")
        else:
            dice = _ask_dice("  Enter your initial roll (5 numbers, space-separated): ")

        # ── Step 2: bot recommends target Wurf ───────────────────────────
        target_wurf = bot.choose_target_wurf(board, dice)
        rerolls_needed = target_wurf - 1
        if rerolls_needed == 0:
            wurf_desc = "place now — no re-rolls"
        elif rerolls_needed == 1:
            wurf_desc = "re-roll once"
        else:
            wurf_desc = f"re-roll {rerolls_needed} times"
        print(f"\n  🤖 Bot recommends Wurf {target_wurf} ({wurf_desc})")

        # Player can override
        resp = input(f"  Use Wurf {target_wurf}? [Y / type 1-4 to override]: ").strip()
        if resp in ("1", "2", "3", "4"):
            chosen = int(resp)
            if any(board.valid_rows_for_col(c, chosen) for c in range(NUM_COLS)):
                target_wurf = chosen
                print(f"  → Overridden to Wurf {target_wurf}")
            else:
                print(f"  ⚠️  Wurf {chosen} is fully filled — keeping Wurf {target_wurf}")

        # ── Step 3: re-roll loop (exactly target_wurf - 1 re-rolls) ──────
        throw_num = 1
        while throw_num < target_wurf:
            decision = bot.decide_reroll(board, dice, throw_num, target_wurf)
            print(f"\n  🤖 Bot says: {decision.reasoning}")

            answer = input(
                "  Follow bot's suggestion? [Y/n]: "
                if digital else
                "  Re-roll as suggested? [Y/n]: "
            ).strip().lower()

            if answer in ("", "y"):
                if digital:
                    dice = reroll(decision.kept, len(decision.reroll))
                    print(f"  🎲 Re-rolling {len(decision.reroll)} dice ... {dice}")
                else:
                    dice = reroll(decision.kept, len(decision.reroll))
                    print(f"  🎲 Suggested result: {dice}")
                    if input("  Use this or enter your own? [Y/manual]: ").strip().lower() == "manual":
                        dice = _ask_dice("  Enter your new dice (5 numbers): ")
            else:
                if digital:
                    keep_input = input(
                        f"  Which values to keep from {dice}? "
                        "(space-separated, blank = re-roll all): "
                    ).strip()
                    kept_manual = list(map(int, keep_input.split())) if keep_input else []
                    dice = reroll(kept_manual, 5 - len(kept_manual))
                    print(f"  🎲 Re-rolling {5 - len(kept_manual)} dice ... {dice}")
                else:
                    dice = _ask_dice("  Enter your new dice (5 numbers): ")

            throw_num += 1
            if throw_num < target_wurf:
                print(f"  (Throw {throw_num} of {target_wurf})")

        # ── Step 4: placement ─────────────────────────────────────────────
        placement = bot.decide_placement(board, dice, target_wurf)
        print(f"\n  🤖 Bot recommends: {placement.reasoning}")

        agree = input("  Accept placement? [Y/n]: ").strip().lower()
        if agree in ("", "y"):
            board.fill(placement.col_idx, placement.row_idx, dice, target_wurf)
        else:
            _manual_placement(board, dice, target_wurf)

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


def _manual_placement(board: Board, dice: list[int], current_throw: int = 1):
    """Ask human to pick a column and row manually."""
    print("  Available placements:")
    options = []
    for c in range(len(COLUMNS)):
        for r in board.valid_rows_for_col(c, current_throw):
            throw_n, ctype = COLUMNS[c]
            sym = {DOWN: "↓", UP: "↑", FREE: "F"}[ctype]
            row_name = ALL_ROWS[r]
            from kniffel.scoring import score_dice
            sc = score_dice(dice, row_name)
            options.append((c, r))
            print(f"  [{len(options)-1:>3}] Wurf{throw_n}[{sym}] / {row_name:<15} → {sc} pts")

    if not options:
        print("  No valid placements at this Wurf — accepting bot placement instead.")
        return

    while True:
        try:
            idx = int(input("  Choose option number: "))
            if 0 <= idx < len(options):
                c, r = options[idx]
                board.fill(c, r, dice, current_throw)
                return
        except ValueError:
            pass
        print("  Invalid choice.")


# ──────────────────────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kniffel_bot",
        description="Kniffel AI Bot — demo, simulate, log, or play interactively.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play one verbose demo game.")
    sim = sub.add_parser("simulate", help="Run N silent games and print statistics.")
    sim.add_argument("n", nargs="?", default=50, help="Number of games (default: 50)")
    sub.add_parser("log", help="Play one game and save a JSON turn log.")
    sub.add_parser("interactive", help="Human plays with bot coaching.")
    return p


if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()
    {"demo": cmd_demo, "simulate": cmd_simulate,
     "log": cmd_log, "interactive": cmd_interactive}[args.command](args)
