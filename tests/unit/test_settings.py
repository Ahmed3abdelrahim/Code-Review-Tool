"""Settings: fail fast with variable names, never values."""

from __future__ import annotations

import os
import traceback
from pathlib import Path

import pytest

from aireviewer.errors import ConfigError
from aireviewer.settings import ApiSettings, WorkerSettings, load_settings

pytestmark = pytest.mark.p0

# Fake values only; none of these is a real credential.
WEBHOOK_SECRET = "fake-webhook-secret-0123456789abcdef0123456789abcdef"
DB_PASSWORD = "fake-db-password-sentinel"
DATABASE_URL = f"postgresql+psycopg://aireviewer:{DB_PASSWORD}@localhost:55432/aireviewer"
SENTINEL = "VALUE-MUST-NOT-APPEAR"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(os.environ):
        if key.upper().startswith("AIREVIEW_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def common_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIREVIEW_DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AIREVIEW_GITHUB_APP_ID", "123456")
    monkeypatch.setenv("AIREVIEW_GITHUB_APP_SLUG", "ai-reviewer-dev")


def _full_text(error: BaseException) -> str:
    return "".join(traceback.format_exception(error)) + repr(error)


def test_missing_required_setting_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)

    with pytest.raises(ConfigError) as excinfo:
        load_settings(ApiSettings)

    message = str(excinfo.value)
    for name in ("AIREVIEW_DATABASE_URL", "AIREVIEW_GITHUB_APP_ID", "AIREVIEW_GITHUB_APP_SLUG"):
        assert name in message
    assert "AIREVIEW_GITHUB_WEBHOOK_SECRET" not in message
    assert WEBHOOK_SECRET not in _full_text(excinfo.value)
    # Not chained to pydantic's ValidationError (not even as hidden context): its text
    # includes input values.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


@pytest.mark.usefixtures("common_env")
def test_invalid_setting_message_hides_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIREVIEW_GITHUB_APP_ID", f"not-a-number-{SENTINEL}")
    monkeypatch.setenv("AIREVIEW_DATABASE_URL", f"mysql://user:{SENTINEL}@db/x")
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", f"short-{SENTINEL}")
    monkeypatch.setenv("AIREVIEW_LOG_LEVEL", f"LOUD-{SENTINEL}")
    # 11 characters: one short of the known-value redaction minimum.
    monkeypatch.setenv("AIREVIEW_MODEL_API_KEY", "fake-key-11")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(ApiSettings)

    message = str(excinfo.value)
    for name in (
        "AIREVIEW_GITHUB_APP_ID",
        "AIREVIEW_DATABASE_URL",
        "AIREVIEW_GITHUB_WEBHOOK_SECRET",
        "AIREVIEW_LOG_LEVEL",
        "AIREVIEW_MODEL_API_KEY",
    ):
        assert name in message
    assert SENTINEL not in _full_text(excinfo.value)
    assert "fake-key-11" not in _full_text(excinfo.value)
    # A rejected secret's length is not disclosed either, only the requirement.
    assert "AIREVIEW_GITHUB_WEBHOOK_SECRET: must be at least 32 characters" in message
    assert "AIREVIEW_MODEL_API_KEY: must be at least 12 characters" in message
    assert f"not {len(f'short-{SENTINEL}')}" not in message


@pytest.mark.usefixtures("common_env")
def test_role_specific_required_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as api_error:
        load_settings(ApiSettings)
    assert "AIREVIEW_GITHUB_WEBHOOK_SECRET" in str(api_error.value)
    assert "AIREVIEW_GITHUB_PRIVATE_KEY_PATH" not in str(api_error.value)

    with pytest.raises(ConfigError) as worker_error:
        load_settings(WorkerSettings)
    assert "AIREVIEW_GITHUB_PRIVATE_KEY_PATH" in str(worker_error.value)
    assert "AIREVIEW_GITHUB_WEBHOOK_SECRET" not in str(worker_error.value)

    key_file = tmp_path / "app-key.txt"
    key_file.write_text("not a real key\n", encoding="utf-8")
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIREVIEW_GITHUB_PRIVATE_KEY_PATH", str(key_file))

    api = load_settings(ApiSettings)
    worker = load_settings(WorkerSettings)

    assert api.github_webhook_secret.get_secret_value() == WEBHOOK_SECRET
    assert worker.github_private_key_path == key_file
    for settings in (api, worker):
        assert WEBHOOK_SECRET not in repr(settings)
        assert DB_PASSWORD not in repr(settings)


@pytest.mark.usefixtures("common_env")
def test_private_key_path_must_exist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AIREVIEW_GITHUB_PRIVATE_KEY_PATH", str(tmp_path / "missing"))

    with pytest.raises(ConfigError) as excinfo:
        load_settings(WorkerSettings)

    assert "AIREVIEW_GITHUB_PRIVATE_KEY_PATH" in str(excinfo.value)


@pytest.mark.usefixtures("common_env")
def test_settings_defaults_match_appendix_e(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)

    settings = load_settings(ApiSettings)

    assert settings.github_app_id == 123456
    assert settings.github_app_slug == "ai-reviewer-dev"
    assert settings.model_provider is None
    assert settings.model_id is None
    assert settings.model_api_key is None
    assert settings.model_base_url is None
    assert settings.model_timeout_s == 120
    assert settings.daily_cost_limit_usd is None
    assert settings.workspace_root == Path("/var/lib/aireviewer/work")
    assert settings.workspace_quota_mb == 2048
    assert settings.max_concurrent_runs == 2
    assert settings.tool_parallelism == 3
    assert settings.llm_parallelism == 3
    assert settings.log_level == "INFO"


@pytest.mark.usefixtures("common_env")
def test_secret_values_for_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    api_key = "fake-model-api-key-0123456789"
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIREVIEW_MODEL_API_KEY", api_key)

    values = load_settings(ApiSettings).secret_values()

    assert {WEBHOOK_SECRET, api_key, DATABASE_URL, DB_PASSWORD} - set(values) == set()


@pytest.mark.usefixtures("common_env")
def test_unknown_prefixed_variable_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRT", f"typo-{SENTINEL}")  # typo'd name
    monkeypatch.setenv("AIREVIEW_LOG_LEVL", f"DEBUG-{SENTINEL}")

    with pytest.raises(ConfigError) as excinfo:
        load_settings(ApiSettings)

    message = str(excinfo.value)
    assert "AIREVIEW_GITHUB_WEBHOOK_SECRT: unknown variable" in message
    assert "AIREVIEW_LOG_LEVL: unknown variable" in message
    assert SENTINEL not in _full_text(excinfo.value)
    assert excinfo.value.__context__ is None


@pytest.mark.usefixtures("common_env")
def test_allowlisted_non_setting_variable_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "app-key.txt"
    key_file.write_text("not a real key\n", encoding="utf-8")
    monkeypatch.setenv("AIREVIEW_PG_PORT", "55432")
    monkeypatch.setenv("AIREVIEW_RECORD", "1")
    # A shared env file carries both roles' settings; neither role rejects the other's.
    monkeypatch.setenv("AIREVIEW_GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("AIREVIEW_GITHUB_PRIVATE_KEY_PATH", str(key_file))

    assert load_settings(ApiSettings).github_app_slug == "ai-reviewer-dev"
    assert load_settings(WorkerSettings).github_private_key_path == key_file
