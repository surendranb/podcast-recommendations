---
description: How to read this server's error shapes (empty pool, feed failures, genre misses) and recover.
---

# Interpreting errors

Every error this server returns carries a trailing tag. Act on the tag, not on
instinct — and never retry more than once.

## `[INPUT_FIXABLE]` — change the arguments, not the environment

- **"No shows survived the filters"** (roulette): the probes found candidates
  but the filters (min_episodes, allow_explicit, exclude) removed them all.
  Loosen in this order: lower `min_episodes`, set `allow_explicit=True`, drop
  `exclude` entries, broaden the topic. Do NOT retry with identical arguments.
- **"Unknown genre"** (roulette/trending): the genre name did not resolve. The
  error lists valid candidates — pick from that list, recognition beats recall.
- **"Feed is not valid XML" / "not a podcast feed"** (peek): the URL is not an
  RSS feed. Use a `feed_url` returned by roulette or trending, not an iTunes
  page URL (itunes_url is a STORE page, feed_url is the RSS feed).

## `[TRANSIENT: retry once]` — network weather

iTunes timeouts and feed-fetch timeouts. Retry the exact same call once. If it
fails again, tell the user the upstream source is unavailable right now.

## Empty results, no error

- `trending` returning an empty `shows` list usually means an invalid country
  code (use two-letter ISO like "us", "gb", "in", "de").
- A roulette pick missing `typical_episode`/`cadence` means the feed peek
  failed (best-effort) — the pick is still valid; call `peek(feed_url)` if the
  user needs episode details.
