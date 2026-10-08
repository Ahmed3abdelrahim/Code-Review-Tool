"""`aireview-eval`: validate cases, score predictions, adjudicate unmatched findings.

Exit codes: 0 success, 1 invalid input (the errors are listed), 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from aireviewer.clock import SystemClock
from aireviewer.eval.adjudicate import (
    AdjudicationStore,
    CodeLookup,
    DirectoryCodeLookup,
    NoCodeLookup,
    run_session,
)
from aireviewer.eval.cases import Case, load_cases, select_split
from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.metrics import Scorecard, score
from aireviewer.eval.predictions import load_predictions
from aireviewer.eval.report import write_report

EXIT_OK: Final = 0
EXIT_INVALID: Final = 1
EXIT_USAGE: Final = 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits on --help (0) and on usage errors (2)
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    try:
        if args.command == "validate":
            return _validate(args.eval_dir)
        if args.command == "score":
            return _score(args)
        return _adjudicate(args)
    except EvalInputError as exc:
        _write("\n".join(exc.messages) + "\n")
        _write(f"{_plural(len(exc.messages), 'error')}; nothing was written.\n")
        return EXIT_INVALID


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aireview-eval", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate", help="validate every case in <eval-dir>/cases")
    _eval_dir(validate)

    for name, text in (
        ("score", "score a predictions file and write a report"),
        ("adjudicate", "record verdicts for unmatched predictions"),
    ):
        sub = commands.add_parser(name, help=text)
        _eval_dir(sub)
        sub.add_argument("--predictions", type=Path, required=True)
        sub.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
        sub.add_argument(
            "--adjudications",
            type=Path,
            help="verdict store (default: <eval-dir>/adjudications.jsonl)",
        )
        if name == "score":
            sub.add_argument("--out-dir", type=Path, help="default: <eval-dir>/reports")
        else:
            sub.add_argument(
                "--code-dir",
                type=Path,
                help="checkouts of each case's head commit, as <code-dir>/<case id>/",
            )
    return parser


def _eval_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--eval-dir", type=Path, default=Path("eval"))


def _validate(eval_dir: Path) -> int:
    loaded = load_cases(eval_dir)
    if loaded.errors:
        _write("\n".join(loaded.errors) + "\n")
        _write(f"{_plural(len(loaded.errors), 'error')}.\n")
        return EXIT_INVALID
    count = len(loaded.cases)
    _write(f"{_plural(count, 'case')} {'is' if count == 1 else 'are'} valid.\n")
    return EXIT_OK


def _scorecard(args: argparse.Namespace) -> tuple[Scorecard, dict[str, Case], AdjudicationStore]:
    loaded = load_cases(args.eval_dir)
    if loaded.errors:
        raise EvalInputError(*loaded.errors)
    cases = select_split(loaded.cases, args.split)
    predictions = load_predictions(args.predictions, cases)
    store = AdjudicationStore(args.adjudications or args.eval_dir / "adjudications.jsonl")
    card = score(cases, predictions, store.load(), split=args.split)
    return card, {c.id: c for c in cases}, store


def _score(args: argparse.Namespace) -> int:
    card, _, _ = _scorecard(args)
    target = write_report(
        card, out_dir=args.out_dir or args.eval_dir / "reports", clock=SystemClock()
    )
    _write((target / "report.md").read_text(encoding="utf-8"))
    _write(f"\nReport written to {target}\n")
    return EXIT_OK


def _adjudicate(args: argparse.Namespace) -> int:
    card, cases, store = _scorecard(args)
    code: CodeLookup = DirectoryCodeLookup(args.code_dir) if args.code_dir else NoCodeLookup()
    _write(f"{_plural(len(card.pending), 'prediction')} without a verdict.\n\n")
    summary = run_session(
        card.pending,
        cases=cases,
        store=store,
        index=store.load(),
        ask=_ask,
        write=_write,
        clock=SystemClock(),
        code=code,
    )
    stopped = ", stopped early" if summary.stopped else ""
    _write(f"{summary.recorded} recorded, {summary.skipped} skipped{stopped}.\n")
    return EXIT_OK


def _ask(prompt: str) -> str:
    _write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.rstrip("\n")


def _write(text: str) -> None:
    sys.stdout.write(text)


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"
