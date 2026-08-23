# SPDX-License-Identifier: MIT

"""Unit tests for the roulette engine: probes, filters, dedupe, cards.
Pure logic — no network. Live iTunes behavior is covered by test_itunes_live."""

import random

import pytest

from podcast_recommendations import roulette as engine
from podcast_recommendations.genres import resolve_genre, genre_suggestions


def _show(id, title, publisher, episodes=10, feed=True, advisory="Clean"):
    return {
        "id": id, "title": title, "publisher": publisher,
        "feed_url": f"https://example.com/{id}.xml" if feed else None,
        "episode_count": episodes, "advisory": advisory, "genre": "Society & Culture",
        "artwork": None, "itunes_url": f"https://podcasts.apple.com/x{len(title) and id}",
    }


# --- probes ---

def test_probes_with_topic_start_with_topic_and_are_deterministic():
    rng = random.Random(42)
    probes = engine.build_probes("true crime", rng, n=3)
    assert probes[0] == "true crime"
    assert len(probes) == 3
    assert engine.build_probes("true crime", random.Random(42), n=3) == probes


def test_probes_without_topic_are_random_pairs():
    rng = random.Random(7)
    probes = engine.build_probes(None, rng, n=4)
    assert len(probes) == 4
    for p in probes:
        assert p and isinstance(p, str)


# --- filtering ---

def test_filter_pool_dedupes_ids_and_publishers():
    pool = [
        _show(1, "A Show", "Big Network"),
        _show(1, "A Show", "Big Network"),          # id dup
        _show(2, "Another", "Big Network"),          # publisher dup
        _show(3, "Third", "Small Indie"),
    ]
    kept = engine.filter_pool(pool, min_episodes=3, exclude=None, allow_explicit=False)
    assert [s["id"] for s in kept] == [1, 3]


def test_filter_pool_respects_min_episodes_feed_and_explicit():
    pool = [
        _show(10, "Dead", "X", episodes=1),                       # too few
        _show(11, "No Feed", "Y", feed=False),                    # no feed_url
        _show(12, "Explicit", "Z", advisory="Explicit"),          # filtered
        _show(13, "Good", "W"),
    ]
    kept = engine.filter_pool(pool, 3, None, allow_explicit=False)
    assert [s["id"] for s in kept] == [13]
    kept_x = engine.filter_pool(pool, 3, None, allow_explicit=True)
    assert 12 in [s["id"] for s in kept_x]


def test_filter_pool_exclusion_is_substring_case_insensitive():
    pool = [_show(20, "The Daily Boring", "NYT"), _show(21, "Hidden Gems", "Indie")]
    kept = engine.filter_pool(pool, 3, exclude=["the daily", "nyt"], allow_explicit=False)
    assert [s["id"] for s in kept] == [21]


# --- card ---

def test_card_with_feed_info_projection():
    show = _show(30, "Archive Show", "Some Network")
    feed_info = {
        "median_duration_label": "42m", "cadence_label": "weekly",
        "show": {"description": "A show about old things. " * 40},
        "episodes": [{"title": f"ep{i}", "published": "2026-08-0%d" % (i + 1),
                      "duration": "42m"} for i in range(5)],
    }
    card = engine._card(show, "probe words", feed_info)
    assert card["typical_episode"] == "42m"
    assert card["cadence"] == "weekly"
    assert len(card["about"]) <= 280
    assert len(card["recent_episodes"]) == 3
    assert "probe" in card["why_picked"] and "long-tail" in card["why_picked"]
    assert card["feed_url"].endswith(".xml")


def test_card_without_feed_info_still_has_core_fields():
    card = engine._card(_show(31, "Silent", "X"), "p", None)
    assert card["title"] == "Silent"
    assert "typical_episode" not in card


def test_probe_for_matches_title_words():
    probes = ["history files", "unsung history"]
    assert engine._probe_for(_show(1, "The History Files", "X"), probes) == "history files"
    assert engine._probe_for(_show(2, "Unrelated", "X"), probes) == probes[-1]


# --- spin (network monkeypatched) ---

def _patch_itunes(monkeypatch, pool_by_term):
    from podcast_recommendations import itunes

    default = pool_by_term.get("_default", [])

    def fake_search(term, country="us", limit=25):
        return pool_by_term.get(term, default)

    monkeypatch.setattr(itunes, "search_podcasts", fake_search)


def test_spin_returns_pick_with_probe_attribution(monkeypatch):
    _patch_itunes(monkeypatch, {"true crime": [_show(100, "True Crime Files", "A"),
                                                _show(101, "Crime Cabal", "B")]})
    result = engine.spin(topic="true crime", count=1, seed=5)
    assert result["pool_size"] == 2
    assert len(result["picks"]) == 1
    assert result["picks"][0]["title"] in ("True Crime Files", "Crime Cabal")
    assert result["probes"][0] == "true crime"
    assert result["note"]


def test_spin_empty_pool_raises_with_input_fixable(monkeypatch):
    _patch_itunes(monkeypatch, {"true crime": [_show(1, "Only Dead", "X", episodes=1)]})
    with pytest.raises(engine.RouletteError) as exc:
        engine.spin(topic="true crime", min_episodes=3)
    assert "INPUT_FIXABLE" in str(exc.value)


def test_spin_count_capped_by_pool(monkeypatch):
    _patch_itunes(monkeypatch, {"x": [_show(1, "One", "A")]})
    result = engine.spin(topic="x", count=5)
    assert len(result["picks"]) == 1


# --- genres ---

def test_resolve_genre_exact_alias_and_fuzzy():
    assert resolve_genre("tech") == ("technology", 1313)
    assert resolve_genre("Technology") == ("technology", 1313)
    assert resolve_genre("sports") == ("sports", 1312)
    assert resolve_genre("true crime")[0] == "society-and-culture"  # aliased
    assert resolve_genre("nonsense-zzz") == (None, None)
    assert "technology" in genre_suggestions()
