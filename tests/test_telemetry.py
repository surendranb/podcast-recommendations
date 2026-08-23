# SPDX-License-Identifier: MIT

"""Telemetry opt-out / privacy contract tests (fleet standard)."""

from podcast_recommendations import telemetry as t


def test_telemetry_disabled_flags(monkeypatch):
    for flag, value in (
        ("PODCAST_RECOMMENDATIONS_TELEMETRY", "false"),
        ("PODCAST_RECOMMENDATIONS_TELEMETRY", "0"),
        ("DISABLE_TELEMETRY", "1"),
        ("DO_NOT_TRACK", "true"),
        ("NO_TELEMETRY", "on"),
    ):
        monkeypatch.setenv(flag, value)
        assert t._telemetry_disabled() is True, flag


def test_telemetry_enabled_by_default(monkeypatch):
    monkeypatch.delenv("PODCAST_RECOMMENDATIONS_TELEMETRY", raising=False)
    monkeypatch.delenv("DISABLE_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("NO_TELEMETRY", raising=False)
    assert t._telemetry_disabled() is False


def test_scrub_redacts_pii():
    assert t._scrub("see https://example.com/a and /Users/me/secret.txt") == \
        "see <url> and <path>"
    assert t._scrub("mail reachsuren@gmail.com") == "mail <email>"
    assert t._scrub({"nested": "https://x.io"}) == {"nested": "<url>"}


def test_send_telemetry_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(t, "TELEMETRY_DISABLED", True)
    assert t.send_telemetry("mcp_started") is None


def test_opt_out_never_writes_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(t, "TELEMETRY_DISABLED", True)
    monkeypatch.setenv("HOME", str(tmp_path))
    install_id, _ = t._init_anonymous_identity()
    assert install_id.startswith("anon_")
    assert not (tmp_path / ".podcast_recommendations").exists()
