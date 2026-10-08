"""Structured JSON logging with redaction of secrets."""

from __future__ import annotations

import io
import json
import logging
import sys
import threading
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import structlog

from aireviewer.logging import MASK, MAX_REPR_CHARS, configure_logging, get_logger

pytestmark = pytest.mark.p0

# Fake values only; none of these is a real credential.
GHS_TOKEN = "ghs_FAKEinstallationTOKENforTESTS0000000000"
GHP_TOKEN = "ghp_FAKEpersonalTOKENforTESTS00000000000000"
PAT_TOKEN = "github_pat_FAKE0fineGRAINED_tokenFORtests000000000000"
BEARER_VALUE = "FAKEbearerVALUEforTESTS.abc-def_123"
KNOWN_SECRET = "fake-known-webhook-secret-0123456789abcdef"
SHORT_SECRET = "postgres"
PEM_BODY = "MIIEFAKEkeyBODYforTESTSonlyNOTaREALkey0123456789abcdefABCDEF"
PEM_BLOCK = "\n".join(
    ["-----BEGIN RSA PRIVATE KEY-----", PEM_BODY, PEM_BODY, "-----END RSA PRIVATE KEY-----"]
)

Records = Callable[[], list[dict[str, Any]]]


@pytest.fixture
def capture() -> Iterator[tuple[io.StringIO, Records]]:
    stream = io.StringIO()
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, sys.excepthook, threading.excepthook)
    configure_logging("DEBUG", secrets=[KNOWN_SECRET, SHORT_SECRET], stream=stream)

    def records() -> list[dict[str, Any]]:
        return [json.loads(line) for line in stream.getvalue().splitlines()]

    yield stream, records

    structlog.reset_defaults()
    root.handlers[:] = saved[0]
    root.setLevel(saved[1])
    sys.excepthook = saved[2]
    threading.excepthook = saved[3]


class Opaque:
    """A non-JSON object whose repr carries secrets."""

    def __init__(self, secret: str) -> None:
        self.secret = secret

    def __repr__(self) -> str:
        return f"Opaque(secret={self.secret!r}, api_key='fake-api-key-value-123')"


def test_redacts_tokens_in_message(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test")

    log.info(f"cloning with {GHS_TOKEN}, user {GHP_TOKEN}, pat {PAT_TOKEN}")
    log.info(f"sending Bearer {BEARER_VALUE} upstream")

    output = stream.getvalue()
    for secret in (GHS_TOKEN, GHP_TOKEN, PAT_TOKEN, BEARER_VALUE):
        assert secret not in output
    first, second = records()
    assert first["event"] == f"cloning with {MASK}, user {MASK}, pat {MASK}"
    assert second["event"] == f"sending Bearer {MASK} upstream"


def test_redacts_bound_fields(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test").bind(installation_token=GHS_TOKEN)

    log.info(
        "request",
        headers={
            "Authorization": f"token {GHS_TOKEN}",
            "Proxy-Authorization": "Basic ZmFrZTpmYWtl",
            "Cookie": "session=fake-cookie",
            "Set-Cookie": "session=fake-cookie",
            "X-API-Key": "fake-x-api-key",
            "Accept": "application/json",
        },
        password="fake-password",
        secret="fake-secret",
        token="fake-token",
        api_key="fake-api-key",
        apikey="fake-apikey",
        private_key="fake-private-key",
        client_secret="fake-client-secret",
        webhook_secret="fake-webhook-secret",
        db_password="fake-db-password",
        model_api_key="fake-model-api-key",
        github_private_key="fake-github-private-key",
        nested=[{"inner": (f"see {GHP_TOKEN}",)}],
        obj=Opaque(PAT_TOKEN),
        known=f"value is {KNOWN_SECRET}",
        header_text=f"Authorization: Bearer {BEARER_VALUE}",
    )

    output = stream.getvalue()
    for secret in (GHS_TOKEN, GHP_TOKEN, PAT_TOKEN, KNOWN_SECRET, BEARER_VALUE, "fake-"):
        assert secret not in output
    (record,) = records()
    headers = record["headers"]
    for name in ("Authorization", "Proxy-Authorization", "Cookie", "Set-Cookie", "X-API-Key"):
        assert headers[name] == MASK
    assert headers["Accept"] == "application/json"
    for key in (
        "installation_token",
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "private_key",
        "client_secret",
        "webhook_secret",
        "db_password",
        "model_api_key",
        "github_private_key",
    ):
        assert record[key] == MASK, key
    assert record["nested"] == [{"inner": [f"see {MASK}"]}]
    assert record["obj"].startswith("Opaque(")
    assert record["known"] == f"value is {MASK}"
    assert record["header_text"] == f"Authorization: {MASK}"


def test_redacts_exception_text(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test")

    try:
        raise RuntimeError(f"auth failed for Authorization: token {GHS_TOKEN}")
    except RuntimeError:
        log.exception("call_failed")

    assert GHS_TOKEN not in stream.getvalue()
    (record,) = records()
    assert "Traceback (most recent call last)" in record["exception"]
    assert "RuntimeError: auth failed for Authorization: ***" in record["exception"]


def test_traceback_does_not_include_locals(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test")
    # Built at runtime so the value never appears in a source line of the traceback,
    # and shaped so no text pattern would catch it: only "no locals" keeps it out.
    local_value = "-".join(["plain", "local", "value", "kept", "out", "of", "logs"])

    def fail(value: str) -> None:
        held = value.upper()
        raise ValueError("boom " + str(len(held)))

    try:
        fail(local_value)
    except ValueError:
        log.exception("failed")

    output = stream.getvalue()
    assert local_value not in output
    assert local_value.upper() not in output
    assert "ValueError: boom" in records()[0]["exception"]


def test_redacts_pem_block(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test")

    log.info(f"loaded key\n{PEM_BLOCK}\ndone")
    log.info("truncated", value="-----BEGIN PRIVATE KEY-----\n" + PEM_BODY)

    assert PEM_BODY not in stream.getvalue()
    first, second = records()
    assert first["event"] == f"loaded key\n{MASK}\ndone"
    assert second["value"] == MASK


def test_redacts_url_credentials(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    log = get_logger("test")

    log.info("db", url="postgresql+psycopg://aireviewer:fake-db-pw@localhost:55432/aireviewer")
    log.info("clone", url=f"https://x-access-token:{GHS_TOKEN}@github.com/o/r.git")

    output = stream.getvalue()
    assert "fake-db-pw" not in output
    assert GHS_TOKEN not in output
    first, second = records()
    assert first["url"] == f"postgresql+psycopg://aireviewer:{MASK}@localhost:55432/aireviewer"
    assert second["url"] == f"https://x-access-token:{MASK}@github.com/o/r.git"


def test_short_secret_not_replaced_globally(capture: tuple[io.StringIO, Records]) -> None:
    _, records = capture
    log = get_logger("test")

    log.info("connecting to postgres", dsn="postgresql://postgres:postgres@db:5432/postgres")
    log.info(f"webhook secret is {KNOWN_SECRET}")

    first, second = records()
    assert first["event"] == "connecting to postgres"
    assert first["dsn"] == f"postgresql://postgres:{MASK}@db:5432/postgres"
    assert second["event"] == f"webhook secret is {MASK}"


def test_does_not_redact_usage_fields(capture: tuple[io.StringIO, Records]) -> None:
    _, records = capture
    log = get_logger("test")

    log.info("model_call", input_tokens=1234, output_tokens=56, max_tokens=4096, token_count=7)

    (record,) = records()
    assert record["input_tokens"] == 1234
    assert record["output_tokens"] == 56
    assert record["max_tokens"] == 4096
    assert record["token_count"] == 7


def test_redacts_stdlib_log_records(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    stdlib_logger = logging.getLogger("httpx")

    stdlib_logger.info("HTTP Request: GET %s", f"https://x-access-token:{GHS_TOKEN}@github.com/")
    try:
        raise ConnectionError(f"Authorization: Bearer {BEARER_VALUE}")
    except ConnectionError:
        stdlib_logger.exception("request failed")

    output = stream.getvalue()
    assert GHS_TOKEN not in output
    assert BEARER_VALUE not in output
    first, second = records()
    assert first["logger"] == "httpx"
    assert first["event"] == f"HTTP Request: GET https://x-access-token:{MASK}@github.com/"
    assert "ConnectionError: Authorization: ***" in second["exception"]


def test_excepthook_routes_through_redaction(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture
    error = RuntimeError(f"crashed holding {GHS_TOKEN}")

    sys.excepthook(RuntimeError, error, None)

    assert GHS_TOKEN not in stream.getvalue()
    (record,) = records()
    assert record["level"] == "critical"
    assert f"RuntimeError: crashed holding {MASK}" in record["exception"]


def test_repr_of_large_objects_is_capped(capture: tuple[io.StringIO, Records]) -> None:
    _, records = capture

    class Huge:
        def __repr__(self) -> str:
            return "x" * (MAX_REPR_CHARS * 5)

    get_logger("test").info("big", obj=Huge())

    (record,) = records()
    assert len(record["obj"]) <= MAX_REPR_CHARS + 50


def test_output_is_json_lines(capture: tuple[io.StringIO, Records]) -> None:
    stream, records = capture

    get_logger("aireviewer.test").warning("something_happened", run_id=42)

    assert len(stream.getvalue().splitlines()) == 1
    (record,) = records()
    assert record["event"] == "something_happened"
    assert record["level"] == "warning"
    assert record["logger"] == "aireviewer.test"
    assert record["run_id"] == 42
    assert record["timestamp"].endswith("Z")
