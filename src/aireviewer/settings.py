"""Settings from AIREVIEW_* environment variables (plan Appendix E).

Each process loads its role's class through `load_settings`, which fails fast with a
ConfigError naming the offending variables and never their values. An AIREVIEW_* variable
that is neither a setting of any role nor in NON_SETTING_VARIABLES is rejected, so a typo
cannot silently fall back to a default.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import unquote, urlsplit

from pydantic import (
    Field,
    FilePath,
    HttpUrl,
    PositiveInt,
    SecretStr,
    ValidationError,
    field_validator,
)
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict

from aireviewer.errors import ConfigError

ENV_PREFIX = "AIREVIEW_"
# AIREVIEW_* variables that are deliberately not settings.
NON_SETTING_VARIABLES: Final = frozenset(
    {
        "AIREVIEW_PG_PORT",  # compose.yaml host port for Postgres
        "AIREVIEW_RECORD",  # tests: record model cassettes
    }
)
_POSTGRES_SCHEMES = ("postgresql://", "postgresql+psycopg://")

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
ModelProvider = Literal["anthropic", "openai_compatible"]


class CommonSettings(BaseSettings):
    """Settings every process needs. No .env loading: the environment is the only source."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX, extra="ignore", frozen=True, protected_namespaces=()
    )

    database_url: SecretStr  # contains the database password
    github_app_id: PositiveInt
    github_app_slug: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]

    # Required from Phase 3 on; T3.1 makes them required.
    model_provider: ModelProvider | None = None
    model_id: str | None = None
    # >= 12 so known-value log redaction (MIN_KNOWN_SECRET_LENGTH) always covers it.
    model_api_key: Annotated[SecretStr, Field(min_length=12)] | None = None
    model_base_url: HttpUrl | None = None
    model_timeout_s: Annotated[float, Field(gt=0)] = 120
    daily_cost_limit_usd: Annotated[Decimal, Field(gt=0)] | None = None

    workspace_root: Path = Path("/var/lib/aireviewer/work")
    workspace_quota_mb: PositiveInt = 2048
    max_concurrent_runs: PositiveInt = 2
    tool_parallelism: PositiveInt = 3
    llm_parallelism: PositiveInt = 3
    log_level: LogLevel = "INFO"

    @field_validator("database_url")
    @classmethod
    def _require_postgres_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(_POSTGRES_SCHEMES):
            raise ValueError("must be a postgresql:// or postgresql+psycopg:// URL")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    def secret_values(self) -> list[str]:
        """Every secret value, for the log redactor (which ignores short ones)."""
        values = [
            value.get_secret_value()
            for name in type(self).model_fields
            if isinstance(value := getattr(self, name), SecretStr)
        ]
        password = urlsplit(self.database_url.get_secret_value()).password
        if password:
            values.append(unquote(password))
        return values


class ApiSettings(CommonSettings):
    github_webhook_secret: Annotated[SecretStr, Field(min_length=32)]


class WorkerSettings(CommonSettings):
    github_private_key_path: FilePath


_ROLE_CLASSES: Final = (CommonSettings, ApiSettings, WorkerSettings)


def load_settings[S: CommonSettings](settings_class: type[S]) -> S:
    """Load settings for one process role, or raise ConfigError naming each bad variable."""
    problems = [
        f"{name}: unknown variable (not a setting of any role; check for a typo)"
        for name in _unknown_variables()
    ]
    try:
        settings = settings_class()
    except ValidationError as exc:
        problems += sorted({_describe(error) for error in exc.errors(include_input=False)})
    else:
        if not problems:
            return settings
    # Raised outside the except block so the ValidationError (whose text includes input
    # values) is not even attached as hidden context.
    raise ConfigError(
        f"Invalid configuration for {settings_class.__name__}:\n"
        + "\n".join(f"  - {problem}" for problem in problems)
    )


def _unknown_variables() -> list[str]:
    """AIREVIEW_* names in the environment that no role reads and the allowlist lacks.

    Known means known to any role: the API and the worker may share one env file.
    """
    known = NON_SETTING_VARIABLES | {
        f"{ENV_PREFIX}{field}".upper() for role in _ROLE_CLASSES for field in role.model_fields
    }
    return sorted(
        name
        for name in os.environ
        if name.upper().startswith(ENV_PREFIX) and name.upper() not in known
    )


def _describe(error: ErrorDetails) -> str:
    field = str(error["loc"][0]) if error["loc"] else "?"
    variable = f"{ENV_PREFIX}{field.upper()}"
    if error["type"] == "missing":
        return f"{variable}: required but not set"
    if error["type"] in {"too_short", "string_too_short"}:
        # pydantic's message includes the actual length, which says something about a secret.
        minimum = error.get("ctx", {}).get("min_length", "?")
        return f"{variable}: must be at least {minimum} characters"
    return f"{variable}: {error['msg']}"
