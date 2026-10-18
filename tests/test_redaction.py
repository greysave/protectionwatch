from __future__ import annotations

import json
import logging

import pytest

from protectionwatch.collector import Poller
from protectionwatch.config import Config
from protectionwatch.redact import REDACTED, RedactingFilter, redact

from .helpers import FakeClock, ScriptedClient


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("Authorization: Bearer abc.DEF-123", "abc.DEF-123"),
        ("password=hunter2 next", "hunter2"),
        ("api_key: 'k-12345'", "k-12345"),
        ("token=\"t0k3n\"", "t0k3n"),
        ("GET https://user:s3cret@example.invalid/x", "s3cret"),
        ("client_secret=zzz&other=1", "zzz"),
    ],
)  # fmt: skip
def test_redact_masks_secret(raw: str, secret: str) -> None:
    out = redact(raw)
    assert secret not in out
    assert REDACTED in out


LEAK_CASES: list[tuple[str, list[str]]] = [
    # Basic and other Authorization schemes
    ("Authorization: Basic dXNlcjpwYXNzd29yZA==", ["dXNlcjpwYXNzd29yZA"]),
    ("authorization=Basic dXNlcjpwYXNz", ["dXNlcjpwYXNz"]),
    ("Proxy-Authorization: Basic c2VjcmV0OnNlY3JldA==", ["c2VjcmV0OnNlY3JldA"]),
    ("Authorization: Digest username=bob", ["Digest username"]),
    ("Authorization: Negotiate YIIabc123", ["YIIabc123"]),
    ("Authorization: rawtokenvalue99", ["rawtokenvalue99"]),
    ('"Authorization": "Basic dXNlcjpwYXNz"', ["dXNlcjpwYXNz"]),
    ("Basic dXNlcjpwYXNzd29yZA==", ["dXNlcjpwYXNzd29yZA"]),
    # Quoted values containing spaces
    ('{"password": "correct horse battery staple"}', ["correct", "staple"]),
    ('{"token": "two words"}', ["two words"]),
    ("{'secret': 'has several spaces here'}", ["several spaces"]),
    ('password="a b c"', ["a b c"]),
    ("password='a b c'", ["a b c"]),
    ('{"client_secret":"x y z","other":1}', ["x y z"]),
    ('{"password": "say \\"hi\\" there"}', ["hi", "there"]),
    ('{\\"password\\": \\"esc aped value\\"}', ["esc aped"]),
    ('{"access_token": "abc def", "refresh_token": "ghi jkl"}', ["abc def", "ghi jkl"]),
    # api_key with spaces (quoted) and bare
    ('api_key="my api key value"', ["my api key"]),
    ("api_key='my api key value'", ["my api key"]),
    ("API-KEY: 'spaced key 123'", ["spaced key"]),
    ('{"apiKey": "spaced key 123"}', ["spaced key"]),
    ("api_key=abc123", ["abc123"]),
    ("X-Api-Key: abc123", ["abc123"]),
    # Cookie headers
    ("Cookie: sessionid=abc123; csrftoken=def456; theme=dark", ["abc123", "def456", "dark"]),
    ("Set-Cookie: sid=abc123; Path=/; HttpOnly; Secure", ["abc123"]),
    ("cookie=abc123def", ["abc123def"]),
    ('{"Cookie": "sid=abc; other=def"}', ["sid=abc", "other=def"]),
    # URL userinfo
    ("GET https://bob:hunter2@host.example.invalid/path", ["bob", "hunter2"]),
    ("ftp://svc-account:p%40ss@files.example.invalid", ["svc-account", "p%40ss"]),
    ("git clone https://ghp_abcdef123456@host.example.invalid/r.git", ["ghp_abcdef123456"]),
    # Bearer and existing key=value forms
    ("Bearer abc.def-ghi_123", ["abc.def-ghi_123"]),
    ("auth failed: bearer TOKEN123", ["TOKEN123"]),
    ("password=hunter2", ["hunter2"]),
    ("passwd: hunter2", ["hunter2"]),
    ("secret=s3cr3t&next=1", ["s3cr3t"]),
    ("token: Bearer xyz", ["xyz"]),
    ("https://h.example.invalid/x?api_key=k3y&page=2", ["k3y"]),
]


@pytest.mark.parametrize(("text", "secrets"), LEAK_CASES)
def test_no_secret_survives(text: str, secrets: list[str]) -> None:
    out = redact(text)
    assert REDACTED in out
    for secret in secrets:
        assert secret not in out, out


@pytest.mark.parametrize(("text", "_"), LEAK_CASES)
def test_redaction_is_idempotent(text: str, _: list[str]) -> None:
    once = redact(text)
    assert redact(once) == once


@pytest.mark.parametrize(
    "text", ["connection reset by peer", "basic authentication failed", "retrying in 2s (3/5)"]
)
def test_benign_text_untouched(text: str) -> None:
    assert redact(text) == text


def test_json_structure_preserved() -> None:
    assert json.loads(redact('{"password": "a b", "n": 1}')) == {"password": REDACTED, "n": 1}


def test_redact_leaves_innocuous_text() -> None:
    assert redact("polled 12 targets in 0.3s") == "polled 12 targets in 0.3s"


def test_filter_redacts_args_and_tracebacks() -> None:
    logger = logging.getLogger("protectionwatch.test_filter")
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Capture()
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        try:
            raise RuntimeError("login failed password=swordfish")
        except RuntimeError:
            logger.exception("auth with token=%s", "abc123")
    finally:
        logger.removeHandler(handler)
    rec = records[0]
    assert "abc123" not in rec.getMessage()
    assert rec.exc_text is not None
    assert "swordfish" not in rec.exc_text


def test_poll_failure_log_is_redacted(caplog: pytest.LogCaptureFixture) -> None:
    caplog.handler.addFilter(RedactingFilter())
    poller = Poller(ScriptedClient(RuntimeError("bad token=sekret-value")), Config(), FakeClock())
    with caplog.at_level(logging.WARNING, logger="protectionwatch.collector"):
        poller.poll_once()
    assert "sekret-value" not in caplog.text
    assert REDACTED in caplog.text
