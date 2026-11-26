"""Offline knowledge indexer CLI (operator machine only; never deployed to the Worker).

Usage (from backend/cloudflare-worker):
    uv run python -m indexer <command>

Commands are implemented in Phase 2 (chunks) and Phase 3 (reindex, query, eval).
"""

from __future__ import annotations

import argparse
import sys

COMMANDS = {
    "chunks": "Load and chunk knowledge files, print a chunk report (Phase 2)",
    "reindex": "Embed new/changed chunks and sync them to Vectorize (Phase 3)",
    "query": "Embed a question and show the best-matching chunks (Phase 3)",
    "eval": "Run the labelled question set and report retrieval hit rate (Phase 3)",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m indexer", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"'{args.command}' is not implemented yet: {COMMANDS[args.command]}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
