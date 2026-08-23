# SPDX-License-Identifier: MIT

"""Unit tests for RSS feed parsing: durations, cadence, medians, atom basics.
Fixture XML — no network."""

from podcast_recommendations import feeds


def _rss(items, title="Test Show", author="Test Author"):
    item_xml = ""
    for i, (t, date, dur) in enumerate(items):
        item_xml += f"""
        <item>
          <title>{t}</title>
          <pubDate>{date}</pubDate>
          <itunes:duration>{dur}</itunes:duration>
          <enclosure url="https://audio.example.com/{i}.mp3" type="audio/mpeg"/>
          <itunes:subtitle>Subtitle {i}</itunes:subtitle>
        </item>"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
      <channel>
        <title>{title}</title>
        <itunes:author>{author}</itunes:author>
        <description>A show for tests.</description>
        <language>en-us</language>
        <itunes:type>episodic</itunes:type>
        {item_xml}
      </channel>
    </rss>"""


def _parse(monkeypatch, xml_bytes):
    monkeypatch.setattr(feeds, "_fetch", lambda url: xml_bytes)
    return feeds.read_feed("https://example.com/feed.xml")


def test_parse_duration_variants():
    assert feeds.parse_duration("1:02:03") == 3723
    assert feeds.parse_duration("42:30") == 2550
    assert feeds.parse_duration("900") == 900
    assert feeds.parse_duration("") is None
    assert feeds.parse_duration("about ten") is None


def test_read_feed_projection_and_cadence(monkeypatch):
    # 6 weekly episodes (Jun 1, 8, 15, 22, 29, Jul 6), ~30min -> weekly, 30m
    weekly_dates = ["Mon, 01 Jun 2026 10:00:00 GMT", "Mon, 08 Jun 2026 10:00:00 GMT",
                    "Mon, 15 Jun 2026 10:00:00 GMT", "Mon, 22 Jun 2026 10:00:00 GMT",
                    "Mon, 29 Jun 2026 10:00:00 GMT", "Mon, 06 Jul 2026 10:00:00 GMT"]
    items = [(f"ep {i}", d, "30:00") for i, d in enumerate(weekly_dates)]
    info = _parse(monkeypatch, _rss(items).encode())
    assert info["show"]["title"] == "Test Show"
    assert info["show"]["author"] == "Test Author"
    assert info["median_duration_label"] == "30m"
    assert info["cadence_label"] == "weekly"
    assert len(info["episodes"]) == 6
    assert info["episodes"][0]["published"] == "2026-06-01"
    assert info["episodes"][0]["audio_url"].startswith("https://audio")


def test_read_feed_daily_and_monthly_cadence(monkeypatch):
    daily = [(f"d{i}", f"Mon, 0{i + 1} Jun 2026 10:00:00 GMT", "10:00")
             for i in range(4)]
    assert _parse(monkeypatch, _rss(daily).encode())["cadence_label"] == "daily"
    monthly = [(f"m{i}", d, "10:00") for i, d in enumerate([
        "Thu, 01 Jan 2026 10:00:00 GMT", "Sun, 01 Feb 2026 10:00:00 GMT",
        "Sun, 01 Mar 2026 10:00:00 GMT", "Wed, 01 Apr 2026 10:00:00 GMT"])]
    assert _parse(monkeypatch, _rss(monthly).encode())["cadence_label"] == "monthly"


def test_read_feed_atom_fallback(monkeypatch):
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
      <title>Atom Show</title>
      <entry>
        <title>Atom Episode</title>
        <published>2026-08-01T10:00:00Z</published>
        <link href="https://audio.example.com/1.mp3"/>
      </entry>
    </feed>"""
    info = _parse(monkeypatch, atom)
    assert info["show"]["title"] == "Atom Show"
    assert info["episodes"][0]["title"] == "Atom Episode"
    assert info["episodes"][0]["published"] == "2026-08-01"


def test_read_feed_invalid_xml_raises_input_fixable(monkeypatch):
    import pytest

    monkeypatch.setattr(feeds, "_fetch", lambda url: b"<not-xml")
    with pytest.raises(feeds.FeedError) as exc:
        feeds.read_feed("https://example.com/x")
    assert exc.value.input_fixable


def test_fetch_rejects_non_http(monkeypatch):
    import pytest

    with pytest.raises(feeds.FeedError) as exc:
        feeds.read_feed("ftp://example.com/feed")
    assert exc.value.input_fixable
