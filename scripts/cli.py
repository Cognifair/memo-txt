#!/usr/bin/env python3
"""Stable Memo-TXT CLI: lint/finalize/guide. No network, no account access."""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, args):
    command = [sys.executable, "-B", str(HERE / script), *args]
    return subprocess.call(command)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)

    lint = commands.add_parser("lint", help="validate TXT container structure")
    lint.add_argument("path")
    lint.add_argument("--require-answer-line", action="store_true")

    finalize = commands.add_parser("finalize", help="validate and print delivery block")
    finalize.add_argument("path")
    finalize.add_argument("--member", choices=["pro", "free"], default="free")
    finalize.add_argument("--require-answer-line", action="store_true")

    commands.add_parser("guide", help="print import tutorial and copy GIF to CWD")

    args = parser.parse_args(argv)
    if args.action == "lint":
        extra = ["--require-answer-line"] if args.require_answer_line else []
        return run("lint_txt.py", [args.path, *extra])
    if args.action == "finalize":
        extra = ["--member", args.member]
        if args.require_answer_line:
            extra.append("--require-answer-line")
        return run("finalize_txt.py", [args.path, *extra])
    return run("import_guide.py", [])


if __name__ == "__main__":
    raise SystemExit(main())
