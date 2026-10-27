"""Audit log secret-redaction tests."""

from __future__ import annotations

from zuzu.audit.service import redact_value


def test_redacts_sensitive_keys() -> None:
    detail = {
        "api_key": "nvapi-super-secret",
        "password": "hunter2",
        "authorization": "Bearer abc123",
        "safe": "normal value",
        "nested": {"token": "tok_123", "public": "visible"},
        "list": [{"secret_value": "x", "note": "ok"}],
    }
    red = redact_value(detail)
    assert red["api_key"] == "***REDACTED***"
    assert red["password"] == "***REDACTED***"
    assert red["authorization"] == "***REDACTED***"
    assert red["safe"] == "normal value"
    assert red["nested"]["token"] == "***REDACTED***"
    assert red["nested"]["public"] == "visible"
    assert red["list"][0]["secret_value"] == "***REDACTED***"
    assert red["list"][0]["note"] == "ok"


def test_redacts_bearer_strings_in_text() -> None:
    text = "Calling provider with token=abcdef1234567890abcdef1234567890 and key=nvapi-xyz987654321"
    red = redact_value(text)
    assert "abcdef1234567890" not in red
    assert "nvapi-xyz987654321" not in red


def test_redacts_secrets_inside_urls() -> None:
    url = "https://example.com/?api_key=sk-1234567890abcdef1234&x=1"
    red = redact_value({"url": url})
    assert "sk-1234567890abcdef1234" not in red["url"]
