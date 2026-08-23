# SPDX-License-Identifier: MIT

"""The roulette engine: long-tail podcast discovery, not top-10 recycling.

Search APIs return the same chart-toppers for every query. The roulette fixes
that by firing several randomized probe queries (seed modifiers x the user's
topic), pooling results, filtering out dead/one-episode shows and known names,
then picking randomly from the surviving long tail — and being honest about
WHY the pick surfaced (which probe found it).
"""

import random

from . import itunes

# Words that fish the long tail when combined with a topic. Chosen so the
# queries still return results (they match real naming patterns: "… Files",
# "A History of…", "The … Society").
_MODIFIERS = [
    "underappreciated", "obscure", "unsung", "lesser known", "hidden",
    "brief history of", "short history of", "field guide to", "introduction to",
    "deep dive into", "conversations about", "notes on", "dispatches from",
]
_NOUNS = [
    "files", "society", "club", "chronicles", "dispatch", "review", "journal",
    "notes", "lab", "report", "hour", "digest", "circle", "project", "club",
]

MAX_FEED_FETCHES = 3  # peek at most 3 feeds per spin to stay fast


class RouletteError(Exception):
    """Pool-empty or transport failure with model-facing guidance."""

    def __init__(self, message, candidates=None):
        super().__init__(message)
        self.candidates = candidates or []


def build_probes(topic, rng, n=3):
    """Randomized probe queries. With no topic: random modifier+noun pairs."""
    probes = []
    if topic:
        probes.append(topic)  # one honest direct query for calibration
        for _ in range(n - 1):
            if rng.random() < 0.5:
                probes.append(f"{rng.choice(_MODIFIERS)} {topic}")
            else:
                probes.append(f"{topic} {rng.choice(_NOUNS)}")
    else:
        probes = [f"{rng.choice(_MODIFIERS)} {rng.choice(_NOUNS)}".strip()
                  for _ in range(n)]
    return probes


def _excluded(show, exclude):
    """Case-insensitive substring match on title/publisher against the
    user's exclusion list (e.g. brands they already know)."""
    if not exclude:
        return False
    hay = f"{show.get('title') or ''} {show.get('publisher') or ''}".lower()
    return any(str(e).lower() in hay for e in exclude)


def filter_pool(pool, min_episodes, exclude, allow_explicit):
    """Apply the hard filters + dedupe by id AND publisher (publisher dedupe
    keeps a multi-pick spin diverse: no two shows from the same network)."""
    seen_ids, seen_publishers, kept = set(), set(), []
    for show in pool:
        if not show.get("id") or show["id"] in seen_ids:
            continue
        if not show.get("feed_url"):
            continue  # cannot peek or subscribe without a feed
        if (show.get("episode_count") or 0) < min_episodes:
            continue
        if not allow_explicit and (show.get("advisory") or "").lower() == "explicit":
            continue
        if _excluded(show, exclude):
            continue
        publisher = (show.get("publisher") or "").lower()
        if publisher and publisher in seen_publishers:
            continue
        seen_ids.add(show["id"])
        if publisher:
            seen_publishers.add(publisher)
        kept.append(show)
    return kept


def _card(show, probe, feed_info):
    """Final projection: everything the model needs to present the pick in
    ~200 tokens. Server-side arithmetic (cadence, median duration) happens in
    feeds.read_feed, not in the model."""
    card = {
        "title": show.get("title"),
        "publisher": show.get("publisher"),
        "genre": show.get("genre"),
        "episode_count": show.get("episode_count"),
        "advisory": show.get("advisory"),
        "feed_url": show.get("feed_url"),
        "itunes_url": show.get("itunes_url"),
        "artwork": show.get("artwork"),
        "why_picked": f"surfaced by the probe query “{probe}” — a long-tail "
                      f"discovery spin, not a chart pick",
    }
    if feed_info:
        card.update({
            "typical_episode": feed_info.get("median_duration_label"),
            "cadence": feed_info.get("cadence_label"),
            "about": (feed_info.get("show") or {}).get("description", "")[:280],
            "recent_episodes": [
                {"title": e.get("title"), "published": e.get("published"),
                 "duration": e.get("duration")}
                for e in (feed_info.get("episodes") or [])[:3]
            ],
        })
    return card


def spin(topic=None, country="us", count=1, min_episodes=3,
         exclude=None, allow_explicit=False, seed=None):
    """Run one discovery spin. Returns {picks, probes, pool_size, tried_feed};
    raises RouletteError when the filtered pool is empty."""
    rng = random.Random(seed)
    probes = build_probes(topic, rng)

    pool, errors = [], []
    for probe in probes:
        try:
            pool.extend(itunes.search_podcasts(probe, country=country, limit=25))
        except itunes.ItunesError as e:
            errors.append(str(e))

    filtered = filter_pool(pool, min_episodes, exclude, allow_explicit)
    if not filtered:
        raise RouletteError(
            f"No shows survived the filters after {len(probes)} probes "
            f"({len(pool)} raw candidates). Fixes: loosen min_episodes "
            f"(currently {min_episodes}), allow_explicit=true, drop some "
            f"exclude entries, or use a broader topic. "
            f"[INPUT_FIXABLE]" + (f" Transport notes: {'; '.join(errors)}"
                                  if errors else ""),
            candidates=probes)

    picks, tried_feed = [], 0
    for show in rng.sample(filtered, min(count, len(filtered))):
        feed_info = None
        if tried_feed < MAX_FEED_FETCHES:
            tried_feed += 1
            try:
                from . import feeds
                feed_info = feeds.read_feed(show["feed_url"])
            except feeds.FeedError:
                feed_info = None  # peek is best-effort; the card is still valid
        picks.append(_card(show, _probe_for(show, probes), feed_info))
    return {
        "picks": picks,
        "probes": probes,
        "pool_size": len(filtered),
        "note": "Long-tail discovery spin. Present each pick with its feed_url "
                "so the user can subscribe; mention why_picked verbatim.",
    }


def _probe_for(show, probes):
    """Which probe actually surfaced this show (honest attribution)."""
    title = (show.get("title") or "").lower()
    for probe in probes:
        words = [w for w in probe.lower().split() if len(w) > 3]
        if words and any(w in title for w in words):
            return probe
    return probes[-1]
