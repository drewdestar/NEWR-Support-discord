"""Dry-run self-test: load all cogs and count slash commands, no token needed.

Run:  python3 dry_run.py
Exits non-zero if fewer than 99 slash commands are found.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from discord import app_commands

from bot import COGS, SupportBot


def count_commands(cmds) -> int:
    total = 0
    for cmd in cmds:
        if isinstance(cmd, app_commands.Group):
            total += count_commands(cmd.commands)
        else:
            total += 1
    return total


async def main() -> int:
    bot = SupportBot()
    # setup_hook is not run by a bare instance, so load cogs explicitly.
    import db
    db.init_db()
    for cog_path in COGS:
        await bot.load_extension(cog_path)
    total = 0
    for cog_name, cog in bot.cogs.items():
        n = count_commands(cog.__cog_app_commands__)
        print(f"{cog_name}: {n} slash commands")
        total += n
    tree_total = count_commands(bot.tree.get_commands())
    print(f"TOTAL (cogs): {total}")
    print(f"TOTAL (tree): {tree_total}")
    assert 99 <= total <= 100, f"Total {total} slash commands, need 99-100 (Discord guild cap)"
    assert 99 <= tree_total <= 100, f"Tree has {tree_total} slash commands, need 99-100"
    print("OK: 99-100 slash commands, dry-run passed (no token used, no Discord connection).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
