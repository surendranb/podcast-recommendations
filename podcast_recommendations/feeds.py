# SPDX-License-Identifier: MIT

"""Podcast RSS feed reader — the token-asymmetry layer.

A podcast feed is 50–500KB of XML. The model needs 150–300 tokens: what the
show is, how often it publishes, how long episodes run, and the latest few
titles. Everything here exists to make that one clean projection.
"""

import io
import re
import gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

USER_AGENT = "podcast-recommendations/0.1.0 (MCP server; +https://github.com/surendranb/podcast-recommendations)"
TIMEOUT = 6.0
MAX_BYTES = 3 * 1024 * 1024  # hard cap: never parse an unbounded feed

_ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


class FeedError(Exception):
    def __init__(self, message, input_fixable=False):
        super().__init__(message)
        self.input_fixable = input_fixable


def _fetch(url):
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise FeedError(f"Not an http(s) URL: {url!r} [INPUT_FIXABLE]", True)
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={
            "User-Agent": USER_AGENT, "Accept-Encoding": "gzip"},
        )
        resp.raise_for_status()
        raw = resp.content[:MAX_BYTES]
        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return raw
    except requests.Timeout as e:
        raise FeedError(f"Feed fetch timed out [TRANSIENT: retry once]") from e
    except requests.RequestException as e:
        raise FeedError(f"Feed fetch failed ({e}) "
                        f"[INPUT_FIXABLE if the URL is wrong, else TRANSIENT]", True) from e


_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _text(node, *paths):
    for path in paths:
        child = node.find(path)
        if child is not None and child.text:
            return child.text.strip()
        if not path.startswith("{"):  # atom feeds namespace every tag
            child = node.find(_ATOM_NS + path)
            if child is not None and child.text:
                return child.text.strip()
    return None


def parse_duration(raw):
    """itunes:duration comes as 'HH:MM:SS', 'MM:SS', or bare seconds."""
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    parts = raw.split(":")
    if not all(p.isdigit() for p in parts) or len(parts) > 3:
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + int(p)
    return seconds


def _hhmm(seconds):
    if seconds is None:
        return None
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m"


def _pub_date(item):
    raw = _text(item, "pubDate", "published", "{http://purl.org/dc/elements/1.1/}date")
    if not raw:
        return None, None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.date().isoformat(), dt.timestamp()


def _median(values):
    vals = sorted(v for v in values if v)
    if not vals:
        return None
    n = len(vals)
    return vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) // 2


def read_feed(url):
    """Fetch + parse any podcast RSS/Atom feed.

    Returns {show, episodes, median_duration_s, median_duration_label,
    cadence_label, episode_count_seen} or raises FeedError. All server-side
    arithmetic (medians, cadence) happens here — the model never computes.
    """
    raw = _fetch(url)
    try:
        root = ET.parse(io.BytesIO(raw)).getroot()
    except ET.ParseError as e:
        raise FeedError(f"Feed is not valid XML ({e}) [INPUT_FIXABLE: is this a "
                        f"podcast RSS URL? pass feed_url from roulette/trending]",
                        True) from e

    is_atom = root.tag.endswith("}feed") or root.tag == "feed"
    channel = root if is_atom else root.find("channel")
    if channel is None:
        raise FeedError("Feed has no RSS channel [INPUT_FIXABLE: not a podcast feed]")

    items = channel.findall(_ATOM_NS + "entry" if is_atom else "item") or []
    episodes, durations, dates = [], [], []
    for item in items[:30]:
        title = _text(item, "title")
        date_iso, ts = _pub_date(item)
        enclosure = item.find("enclosure")
        if enclosure is None:  # atom feeds: <link rel="enclosure" href=.../>
            for link in item.findall(_ATOM_NS + "link"):
                href = link.get("href")
                if href and (link.get("rel") in (None, "enclosure") or
                             (link.get("type") or "").startswith("audio")):
                    enclosure = link
                    break
        audio_url = (enclosure.get("url") or enclosure.get("href")
                     if enclosure is not None else _text(item, "link"))
        dur = parse_duration(_text(item, f"{_ITUNES_NS}duration",
                                   "{http://www.purl.org/dc/}duration"))
        summary = _text(item, f"{_ITUNES_NS}subtitle", "description",
                        f"{_ITUNES_NS}summary", "summary") or ""
        episodes.append({
            "title": title,
            "published": date_iso,
            "duration": _hhmm(dur),
            "audio_url": audio_url,
            "summary": summary[:280],
        })
        if dur:
            durations.append(dur)
        if ts:
            dates.append(ts)

    cadence = None
    if len(dates) >= 3:
        gaps = [b - a for a, b in zip(sorted(dates), sorted(dates)[1:])]
        med_gap = _median(gaps)
        if med_gap:
            days = max(1, round(med_gap / 86400))
            cadence = ("daily" if days <= 1 else "weekly" if days <= 9
                       else "biweekly" if days <= 18 else "monthly")

    return {
        "show": {
            "title": _text(channel, "title"),
            "author": _text(channel, f"{_ITUNES_NS}author") or _text(
                channel, "author/name"),
            "description": (_text(channel, "description")
                            or _text(channel, f"{_ITUNES_NS}summary") or "")[:400],
            "language": _text(channel, "language"),
            "link": _text(channel, "link") if not is_atom else _text(
                channel, "link"),
            "type": _text(channel, f"{_ITUNES_NS}type") or "episodic",
        },
        "episodes": episodes[:10],
        "median_duration_s": _median(durations),
        "median_duration_label": _hhmm(_median(durations)),
        "cadence_label": cadence,
        "episode_count_seen": len(items),
    }
