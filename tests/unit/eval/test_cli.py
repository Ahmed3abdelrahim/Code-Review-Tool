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
    write_case: Callable[..., Path],
    make_case_data: Callable[..., dict[str, Any]],
    make_finding: Any,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_case(make_case_data())
    holdout = make_case_data(id="holdout-one", split="holdout")
    holdout["source"] = {**holdout["source"], "repo": "https://github.com/example/other"}
    write_case(holdout)
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

    # The holdout case is not in the predictions: scoring holdout or all is refused.
    for split in ("holdout", "all"):
        assert main([*args, "--out-dir", str(out_dir), "--split", split]) == 1
        assert "holdout-one" in capsys.readouterr().out


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
