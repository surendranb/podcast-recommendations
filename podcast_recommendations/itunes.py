# SPDX-License-Identifier: MIT

"""iTunes Podcast Catalog client — search, charts, and batch lookup.

All three endpoints are keyless (verified 2026-08-22) and documented enough to
rely on: the Search API, the per-genre top-podcast RSS charts, and the Lookup
API (which is the only place the RSS feed URL is exposed).
"""

import requests

SEARCH_URL = "https://itunes.apple.com/search"
LOOKUP_URL = "https://itunes.apple.com/lookup"
CHART_URL = "https://itunes.apple.com/{country}/rss/toppodcasts/{path}/json"

USER_AGENT = "podcast-recommendations/0.1.0 (MCP server; +https://github.com/surendranb/podcast-recommendations)"
TIMEOUT = 8.0


class ItunesError(Exception):
    """Raised on transport/HTTP failures (retryable or environment)."""

    def __init__(self, message, transient=True):
        super().__init__(message)
        self.transient = transient


def _get(url, params=None):
    try:
        resp = requests.get(
            url, params=params, timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},  # Apple rejects default lib UAs
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout as e:
        raise ItunesError("iTunes request timed out [TRANSIENT: retry once]") from e
    except requests.RequestException as e:
        raise ItunesError(f"iTunes request failed: {e} [TRANSIENT: retry once]") from e
    except ValueError as e:
        raise ItunesError(f"iTunes returned a non-JSON body [TRANSIENT]") from e


def _artwork(url, size=600):
    """Apple returns a 100x100 or 55x55 thumb; swap the size directive."""
    if not isinstance(url, str) or not url:
        return None
    for old in ("100x100bb", "60x60bb", "55x55bb", "200x200bb", "30x30bb"):
        if old in url:
            return url.replace(old, f"{size}x{size}bb")
    return url


def _normalize(result):
    """One row from search/lookup -> the card shape used everywhere else."""
    return {
        "id": result.get("collectionId"),
        "title": result.get("collectionName"),
        "publisher": result.get("artistName"),
        "feed_url": result.get("feedUrl"),
        "artwork": _artwork(result.get("artworkUrl100")),
        "genre": result.get("primaryGenreName"),
        "genres": result.get("genres") or [],
        "episode_count": result.get("trackCount"),
        "advisory": result.get("contentAdvisoryRating") or "Clean",
        "itunes_url": result.get("collectionViewUrl"),
    }


def search_podcasts(term, country="us", limit=25):
    """Search the podcast catalog. Keyless; returns normalized cards."""
    data = _get(SEARCH_URL, {
        "media": "podcast", "term": term,
        "country": country, "limit": max(1, min(int(limit), 50)),
    })
    return [_normalize(r) for r in data.get("results", [])
            if r.get("wrapperType") == "track" or r.get("kind") == "podcast"]


def lookup_podcasts(ids):
    """Batch lookup (up to ~50 ids in one keyless call). Enriches chart
    entries with feed_url / episode_count / genre."""
    if not ids:
        return {}
    data = _get(LOOKUP_URL, {"id": ",".join(str(i) for i in ids[:50]),
                             "entity": "podcast"})
    out = {}
    for r in data.get("results", []):
        if r.get("collectionId"):
            out[r["collectionId"]] = _normalize(r)
    return out


def chart_podcasts(country="us", genre_id=None, limit=25):
    """Top podcasts (optionally per genre) from Apple's chart RSS, enriched
    via batch lookup. Chart position is preserved as `rank`."""
    limit = max(1, min(int(limit), 50))
    path = f"genre={int(genre_id)}/limit={limit}" if genre_id else f"limit={limit}"
    data = _get(CHART_URL.format(country=(country or "us").lower(), path=path))

    feed = data.get("feed") or {}
    entries = feed.get("entry") or []
    if isinstance(entries, dict):  # single-entry feeds collapse to a dict
        entries = [entries]

    rows = []
    for rank, entry in enumerate(entries[:limit], start=1):
        id_attrs = ((entry.get("id") or {}).get("attributes") or {})
        pid = id_attrs.get("im:id")
        if not pid:
            continue
        rows.append({
            "id": int(pid),
            "rank": rank,
            "title": ((entry.get("im:name") or {}).get("label")),
            "publisher": ((entry.get("im:artist") or {}).get("label")),
            "artwork": _artwork((entry.get("im:image") or [{}])[-1].get("label")),
            "itunes_url": (entry.get("id") or {}).get("label"),
        })

    # Enrich with feed_url/episode_count/genre in ONE batched lookup call.
    try:
        enriched = lookup_podcasts([r["id"] for r in rows])
        for r in rows:
            extra = enriched.get(r["id"])
            if extra:
                r.update({k: extra[k] for k in
                          ("feed_url", "genre", "episode_count", "advisory")
                          if extra.get(k) is not None})
    except ItunesError:
        pass  # charts still useful without enrichment
    return rows
