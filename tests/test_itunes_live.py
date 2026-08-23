# SPDX-License-Identifier: MIT

"""Live tests against the real keyless iTunes endpoints. Marked `live`:
each test skips itself on network failure so CI stays green offline."""

import pytest

from podcast_recommendations import itunes as itunes_mod

pytestmark = pytest.mark.live


def _reachable():
    try:
        rows = itunes_mod.search_podcasts("history", limit=3)
        return bool(rows)
    except Exception:
        return False


# Module-level probe: if iTunes is unreachable, skip the whole file quietly.
if not _reachable():
    pytest.skip("iTunes endpoints unreachable from this network", allow_module_level=True)


def test_search_returns_normalized_cards():
    rows = itunes_mod.search_podcasts("history", limit=10)
    assert len(rows) >= 5
    row = rows[0]
    assert row["id"] and row["title"] and row["publisher"]
    assert row["feed_url"].startswith("http")
    assert row["artwork"] and "600x600" in row["artwork"]
    assert isinstance(row["episode_count"], int) and row["episode_count"] > 0


def test_chart_all_and_genre():
    overall = itunes_mod.chart_podcasts(limit=10)
    assert len(overall) >= 5
    assert overall[0]["rank"] == 1
    assert overall[0]["feed_url"], "chart entries should enrich with feed_url"
    tech = itunes_mod.chart_podcasts(genre_id=1313, limit=5)
    assert len(tech) >= 3


def test_lookup_batch():
    rows = itunes_mod.search_podcasts("science", limit=5)
    found = itunes_mod.lookup_podcasts([r["id"] for r in rows])
    assert len(found) >= 4
    assert all(v["feed_url"] for v in found.values() if v.get("episode_count"))
