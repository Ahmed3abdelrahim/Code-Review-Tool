"""The aireview-eval command line (T0.5)."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any

import pytest

from aireviewer.eval.cli import main

pytestmark = pytest.mark.p0


def predictions_file(path: Path, by_case: dict[str, list[Any]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "producer": {"engine": "cli-test"},
                "cases": {k: [f.model_dump(mode="json") for f in v] for k, v in by_case.items()},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_console_script_declared() -> None:
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("aireview-eval") == "aireviewer.eval.cli:main"


def test_validate_exit_codes(
    eval_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    assert main(["validate", "--eval-dir", str(eval_dir)]) == 0
    assert "1 case is valid" in capsys.readouterr().out

    write_case(make_case_data(id="bad-case", split="test"))
    assert main(["validate", "--eval-dir", str(eval_dir)]) == 1
    out = capsys.readouterr().out
    assert "cases/bad-case.yaml (bad-case): split:" in out
    assert "1 error" in out


def test_usage_errors_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert main(["score"]) == 2  # --predictions is required
    assert main(["score", "--predictions", "p.json", "--split", "test"]) == 2
    capsys.readouterr()


def test_score_writes_and_prints_report(
    eval_dir: Path,
    holdout_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    make_finding: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    holdout = make_case_data(id="holdout-one", split="holdout")
    holdout["source"] = {**holdout["source"], "repo": "https://github.com/example/other"}
    write_case(holdout, holdout=True)
    predictions = predictions_file(tmp_path / "p.json", {"case-one": [make_finding()]})
    out_dir = tmp_path / "reports"
    args = ["score", "--eval-dir", str(eval_dir), "--predictions", str(predictions)]
    assert main([*args, "--out-dir", str(out_dir)]) == 0
    out = capsys.readouterr().out
    assert "# Evaluation report" in out
    assert "100.0% (n=1)" in out  # the finding matches L1
    (report_dir,) = out_dir.iterdir()
    assert report_dir.name.endswith("-dev-score")
    assert f"Report written to {report_dir}" in out
    assert {p.name for p in report_dir.iterdir()} == {"report.md", "metrics.json"}

    # The holdout case is not in these predictions: scoring holdout with them is refused.
    assert main([*args, "--out-dir", str(out_dir), "--split", "holdout"]) == 1
    assert "holdout-one" in capsys.readouterr().out
    # Splits are scored one root at a time; there is no "all".
    assert main([*args, "--split", "all"]) == 2
    capsys.readouterr()


def test_split_selects_root(
    eval_dir: Path,
    holdout_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    make_finding: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    holdout = make_case_data(id="holdout-one", split="holdout", kind="clean", labels=[])
    holdout["source"] = {**holdout["source"], "repo": "https://github.com/example/other"}
    write_case(holdout, holdout=True)
    predictions = predictions_file(tmp_path / "h.json", {"holdout-one": [make_finding()]})
    base = ["--eval-dir", str(eval_dir), "--predictions", str(predictions), "--split", "holdout"]

    assert main(["score", *base]) == 0
    capsys.readouterr()
    (report,) = (holdout_dir / "reports").iterdir()
    assert report.name.endswith("-holdout-score")
    assert not (eval_dir / "reports").exists()

    monkeypatch.setattr("sys.stdin", io.StringIO("i\nnot a bug\n"))
    assert main(["adjudicate", *base, "--no-code"]) == 0
    capsys.readouterr()
    assert (holdout_dir / "adjudications.jsonl").is_file()
    assert not (eval_dir / "adjudications.jsonl").exists()

    comments = holdout_dir / "baselines" / "coderabbit"
    comments.mkdir(parents=True)
    (comments / "holdout-one.json").write_text("[]", encoding="utf-8")
    assert main(["import-coderabbit", "--eval-dir", str(eval_dir), "--split", "holdout"]) == 0
    capsys.readouterr()
    assert (holdout_dir / "baselines" / "coderabbit_predictions.json").is_file()
    assert not (eval_dir / "baselines").exists()


def test_score_refuses_invalid_input(
    eval_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    args = ["score", "--eval-dir", str(eval_dir), "--out-dir", str(tmp_path / "r")]
    assert main([*args, "--predictions", str(bad)]) == 1
    assert "bad.json" in capsys.readouterr().out
    assert not (tmp_path / "r").exists()

    write_case(make_case_data(id="bad-case", split="test"))
    good = predictions_file(tmp_path / "p.json", {"case-one": []})
    assert main([*args, "--predictions", str(good)]) == 1
    assert "bad-case" in capsys.readouterr().out


def test_adjudicate_uses_stdin(
    eval_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    make_finding: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data(id="clean-one", kind="clean", labels=[]))
    predictions = predictions_file(tmp_path / "p.json", {"clean-one": [make_finding()]})
    monkeypatch.setattr("sys.stdin", io.StringIO("i\nnot a bug\n"))
    args = ["adjudicate", "--eval-dir", str(eval_dir), "--predictions", str(predictions)]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "1 recorded" in out
    lines = (eval_dir / "adjudications.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["note"] == "not a bug"


CODERABBIT_COMMENT = {
    "id": 501,
    "user": {"login": "coderabbitai[bot]", "type": "Bot"},
    "path": "src/a.py",
    "line": 10,
    "side": "RIGHT",
    "commit_id": "e" * 40,
    "original_commit_id": "e" * 40,
    "subject_type": "line",
    "diff_hunk": "@@ -9,1 +9,2 @@\n a = 0\n+x = 1",
    "body": "_⚠️ Potential issue_\n\n**Bug at line 10**\n\nWhy.",
}


def test_import_coderabbit_and_score_summary(
    eval_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    comments = eval_dir / "baselines" / "coderabbit"
    comments.mkdir(parents=True)
    (comments / "case-one.json").write_text(json.dumps([CODERABBIT_COMMENT]), encoding="utf-8")
    out = eval_dir / "baselines" / "coderabbit_predictions.json"
    args = ["import-coderabbit", "--eval-dir", str(eval_dir), "--comments-dir", str(comments)]
    assert main([*args, "--out", str(out)]) == 0
    assert "case-one: 1 finding" in capsys.readouterr().out
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["producer"]["engine"] == "coderabbit"
    assert len(document["cases"]["case-one"]) == 1

    summary = eval_dir / "baselines" / "coderabbit.json"
    score_args = [
        "score",
        "--eval-dir",
        str(eval_dir),
        "--predictions",
        str(out),
        "--split",
        "dev",
        "--matching",
        "location",
        "--out-dir",
        str(tmp_path / "reports"),
        "--summary-out",
        str(summary),
    ]
    assert main(score_args) == 0
    printed = capsys.readouterr().out
    assert "Matching: location only" in printed
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["matching"] == "location"
    assert data["inline_precision"]["all"]["n"] == 1
    assert data["comments_per_pr"]["mean"] == 1.0
    assert "high_severity_recall" in data


def test_matching_defaults_to_strict(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["score", "--predictions", "p.json", "--matching", "fuzzy"]) == 2
    capsys.readouterr()


def test_sandbox_commands_printed_not_run(
    eval_dir: Path,
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("sandbox-commands must not run anything")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    write_case(make_case_data())
    assert main(["sandbox-commands", "--eval-dir", str(eval_dir), "--org", "my-sandbox"]) == 0
    out = capsys.readouterr().out
    assert "refs/aireview/case-one/head" in out
    assert "git push" in out
    assert "gh pr create --repo my-sandbox/shop" in out
    assert "gh api --paginate" in out
    assert "baselines/coderabbit/case-one.json" in out
    # PR text never hints at the labels.
    assert "A labeled defect" not in out
    assert main(["sandbox-commands", "--eval-dir", str(eval_dir), "--org", "bad org!"]) == 2
    capsys.readouterr()
