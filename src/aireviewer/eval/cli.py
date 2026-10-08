"""`aireview-eval`: build and validate the benchmark, score predictions, adjudicate.

Exit codes: 0 success, 1 invalid input (the errors are listed), 2 usage error.
`seed-build` runs git only in temporary repositories (D11); `snapshot-upstream` reads a
clone under eval/repos/ and is run by the user; `sandbox-commands` only prints commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import Final

from aireviewer.clock import SystemClock
from aireviewer.config_files import ConfigFileError, load_yaml_mapping
from aireviewer.eval.adjudicate import (
    AdjudicationStore,
    CodeLookup,
    DirectoryCodeLookup,
    NoCodeLookup,
    run_session,
)
from aireviewer.eval.bundles import (
    BundleCodeLookup,
    BundleError,
    build_seed_bundle,
    build_upstream_bundle,
)
from aireviewer.eval.cases import MAX_CASE_BYTES, Case, load_cases, select_split
from aireviewer.eval.coderabbit import build_predictions, load_overrides
from aireviewer.eval.errors import EvalInputError
from aireviewer.eval.git import GitError
from aireviewer.eval.matcher import MatchingMode
from aireviewer.eval.metrics import Scorecard, score
from aireviewer.eval.predictions import load_predictions
from aireviewer.eval.report import summary_document, write_report
from aireviewer.eval.sandbox import ORG_PATTERN, sandbox_commands
from aireviewer.eval.seeds import discover_seeds, pr_description, repository_ignore_spec

EXIT_OK: Final = 0
EXIT_INVALID: Final = 1
EXIT_USAGE: Final = 2
SPLITS: Final = ("dev", "holdout", "all")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits on --help (0) and on usage errors (2)
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    commands = {
        "validate": lambda: _validate(args.eval_dir),
        "score": lambda: _score(args),
        "adjudicate": lambda: _adjudicate(args),
        "seed-build": lambda: _seed_build(args),
        "snapshot-upstream": lambda: _snapshot_upstream(args),
        "sandbox-commands": lambda: _sandbox_commands(args),
        "import-coderabbit": lambda: _import_coderabbit(args),
    }
    try:
        return commands[args.command]()
    except EvalInputError as exc:
        _write("\n".join(exc.messages) + "\n")
        _write(f"{_plural(len(exc.messages), 'error')}; nothing was written.\n")
        return EXIT_INVALID
    except (BundleError, GitError) as exc:
        _write(f"{exc}\n")
        return EXIT_INVALID


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aireview-eval", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    _eval_dir(commands.add_parser("validate", help="validate every case in <eval-dir>/cases"))

    for name, text in (
        ("score", "score a predictions file and write a report"),
        ("adjudicate", "record verdicts for unmatched predictions"),
    ):
        sub = commands.add_parser(name, help=text)
        _eval_dir(sub)
        sub.add_argument("--predictions", type=Path, required=True)
        sub.add_argument("--split", choices=SPLITS, default="dev")
        sub.add_argument(
            "--matching",
            choices=[m.value for m in MatchingMode],
            default=MatchingMode.STRICT.value,
            help="strict (default): categories must be compatible; location: ignore "
            "categories (external baselines and comparison runs)",
        )
        sub.add_argument(
            "--adjudications", type=Path, help="default: <eval-dir>/adjudications.jsonl"
        )
        if name == "score":
            sub.add_argument("--out-dir", type=Path, help="default: <eval-dir>/reports")
            sub.add_argument(
                "--summary-out", type=Path, help="also write a compact baseline summary here"
            )
        else:
            code = sub.add_mutually_exclusive_group()
            code.add_argument(
                "--code-dir", type=Path, help="checkouts of each case's head as <dir>/<case id>/"
            )
            code.add_argument("--no-code", action="store_true", help="do not show code")

    seed = commands.add_parser("seed-build", help="build bundles from eval/seeds (no push)")
    _eval_dir(seed)
    seed.add_argument("--case", action="append", default=[], help="only these case ids")

    upstream = commands.add_parser(
        "snapshot-upstream", help="snapshot two commits of a clone into a case bundle"
    )
    _eval_dir(upstream)
    upstream.add_argument("--repo-dir", type=Path, required=True)
    upstream.add_argument("--case", required=True)
    upstream.add_argument("--base", required=True, help="upstream base commit SHA")
    upstream.add_argument("--head", required=True, help="upstream head commit SHA")
    upstream.add_argument("--title", default=None, help="pull request title (head commit)")

    sandbox = commands.add_parser(
        "sandbox-commands", help="print the commands that push cases to the sandbox"
    )
    _eval_dir(sandbox)
    sandbox.add_argument("--org", required=True, type=_org)
    sandbox.add_argument("--split", choices=SPLITS, default="all")

    coderabbit = commands.add_parser(
        "import-coderabbit", help="convert exported CodeRabbit comments into predictions"
    )
    _eval_dir(coderabbit)
    coderabbit.add_argument(
        "--comments-dir", type=Path, help="default: <eval-dir>/baselines/coderabbit"
    )
    coderabbit.add_argument(
        "--overrides", type=Path, help="default: <eval-dir>/baselines/coderabbit_overrides.yaml"
    )
    coderabbit.add_argument("--split", choices=SPLITS, default="all")
    coderabbit.add_argument(
        "--out", type=Path, help="default: <eval-dir>/baselines/coderabbit_predictions.json"
    )
    return parser


def _eval_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--eval-dir", type=Path, default=Path("eval"))


def _org(value: str) -> str:
    if not ORG_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(f"invalid GitHub organization name: {value!r}")
    return value


# --- validate, score, adjudicate ---------------------------------------------------------------


def _validate(eval_dir: Path) -> int:
    loaded = load_cases(eval_dir)
    if loaded.errors:
        _write("\n".join(loaded.errors) + "\n")
        _write(f"{_plural(len(loaded.errors), 'error')}.\n")
        return EXIT_INVALID
    count = len(loaded.cases)
    _write(f"{_plural(count, 'case')} {'is' if count == 1 else 'are'} valid.\n")
    return EXIT_OK


def _selected_cases(eval_dir: Path, split: str) -> list[Case]:
    loaded = load_cases(eval_dir)
    if loaded.errors:
        raise EvalInputError(*loaded.errors)
    return select_split(loaded.cases, split)  # type: ignore[arg-type]


def _scorecard(args: argparse.Namespace) -> tuple[Scorecard, dict[str, Case], AdjudicationStore]:
    cases = _selected_cases(args.eval_dir, args.split)
    predictions = load_predictions(args.predictions, cases)
    store = AdjudicationStore(args.adjudications or args.eval_dir / "adjudications.jsonl")
    card = score(
        cases, predictions, store.load(), split=args.split, matching=MatchingMode(args.matching)
    )
    return card, {c.id: c for c in cases}, store


def _score(args: argparse.Namespace) -> int:
    card, _, _ = _scorecard(args)
    clock = SystemClock()
    target = write_report(card, out_dir=args.out_dir or args.eval_dir / "reports", clock=clock)
    _write((target / "report.md").read_text(encoding="utf-8"))
    _write(f"\nReport written to {target}\n")
    if args.summary_out:
        summary = summary_document(card, generated_at=clock.now())
        _write_json(args.summary_out, summary)
        _write(f"Summary written to {args.summary_out}\n")
    return EXIT_OK


def _adjudicate(args: argparse.Namespace) -> int:
    card, cases, store = _scorecard(args)
    with ExitStack() as stack:
        code: CodeLookup
        if args.no_code:
            code = NoCodeLookup()
        elif args.code_dir:
            code = DirectoryCodeLookup(args.code_dir)
        else:
            code = stack.enter_context(BundleCodeLookup(args.eval_dir))
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


# --- building the benchmark --------------------------------------------------------------------


def _seed_build(args: argparse.Namespace) -> int:
    eval_dir: Path = args.eval_dir
    seeds, errors = discover_seeds(eval_dir)
    wanted = set(args.case)
    unknown = sorted(wanted - {s.case_id for s in seeds})
    errors += [f"{case_id}: no seed directory found" for case_id in unknown]
    ignore = repository_ignore_spec(eval_dir.resolve().parent)
    for seed in seeds:
        if wanted and seed.case_id not in wanted:
            continue
        try:
            title, body = pr_description(seed.root)
            info = build_seed_bundle(
                seed.case_id,
                seed.base_dir,
                seed.head_dir,
                eval_dir / "bundles" / f"{seed.case_id}.bundle",
                title=title,
                body=body,
                ignore=ignore,
            )
        except (EvalInputError, BundleError) as exc:
            messages = exc.messages if isinstance(exc, EvalInputError) else (str(exc),)
            errors += [f"{seed.case_id}: {m}" for m in messages]
            continue
        state = "written" if info.written else "unchanged"
        _write(
            f"{seed.case_id}: base {info.base_sha[:12]} head {info.head_sha[:12]} "
            f"({info.size_bytes / 1024:.1f} KiB, {state})\n"
        )
        errors += _case_file_problems(eval_dir, seed.case_id, info.base_sha, info.head_sha)
    if errors:
        _write("\n".join(errors) + "\n")
        return EXIT_INVALID
    return EXIT_OK


def _case_file_problems(eval_dir: Path, case_id: str, base: str, head: str) -> list[str]:
    path = eval_dir / "cases" / f"{case_id}.yaml"
    if not path.is_file():
        _write(
            f"{case_id}: no case file yet (cases/{case_id}.yaml); record "
            f"bundle: bundles/{case_id}.bundle, bundle_base_sha: {base}, "
            f"bundle_head_sha: {head}\n"
        )
        return []
    try:
        data = load_yaml_mapping(
            path.read_text(encoding="utf-8"), max_bytes=MAX_CASE_BYTES, what="case file"
        )
    except ConfigFileError as exc:
        return [f"{case_id}: cases/{case_id}.yaml: {m}" for m in exc.messages]
    problems = []
    expected = {
        "bundle": f"bundles/{case_id}.bundle",
        "bundle_base_sha": base,
        "bundle_head_sha": head,
    }
    for key, value in expected.items():
        if data.get(key) != value:
            problems.append(
                f"{case_id}: cases/{case_id}.yaml has {key}: {data.get(key)!r}; "
                f"the seed gives {value} (update the case file)"
            )
    return problems


def _snapshot_upstream(args: argparse.Namespace) -> int:
    out = args.eval_dir / "bundles" / f"{args.case}.bundle"
    title = args.title or "Change under review"
    info = build_upstream_bundle(args.case, args.repo_dir, args.base, args.head, out, title=title)
    _write(
        f"{args.case}: bundle {out} ({info.size_bytes / 1024:.1f} KiB)\n"
        f"record in cases/{args.case}.yaml: bundle: bundles/{args.case}.bundle, "
        f"bundle_base_sha: {info.base_sha}, bundle_head_sha: {info.head_sha}, "
        f"source.base_sha: {args.base}, source.head_sha: {args.head}\n"
    )
    return EXIT_OK


def _sandbox_commands(args: argparse.Namespace) -> int:
    cases = _selected_cases(args.eval_dir, args.split)
    try:
        _write(sandbox_commands(cases, eval_dir=args.eval_dir, org=args.org))
    except ValueError as exc:
        raise EvalInputError(str(exc)) from None
    return EXIT_OK


def _import_coderabbit(args: argparse.Namespace) -> int:
    eval_dir: Path = args.eval_dir
    baselines = eval_dir / "baselines"
    cases = _selected_cases(eval_dir, args.split)
    overrides_path = args.overrides or baselines / "coderabbit_overrides.yaml"
    overrides = load_overrides(overrides_path) if overrides_path.is_file() else {}
    document, stats = build_predictions(
        cases, args.comments_dir or baselines / "coderabbit", overrides
    )
    out: Path = args.out or baselines / "coderabbit_predictions.json"
    _write_json(out, document)
    for case_id, counts in stats.items():
        skipped = ", ".join(f"{reason} {n}" for reason, n in counts.items() if reason != "findings")
        line = f"{case_id}: {_plural(counts['findings'], 'finding')}"
        _write(f"{line} (skipped: {skipped})\n" if skipped else f"{line}\n")
    _write(f"Predictions written to {out}\n")
    return EXIT_OK


# --- helpers ----------------------------------------------------------------------------------


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


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
