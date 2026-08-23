---
description: When to use roulette vs trending vs peek, and how to present a pick.
---

# Discovery vs lookup

Three tools, three jobs:

| Tool | Job | When |
|---|---|---|
| `roulette` | LONG-TAIL discovery | "find me a show about X", "surprise me", "something I haven't heard of" |
| `trending` | What's popular NOW | "what's everyone listening to", chart check, genre health |
| `peek` | Recency on a known feed | "what has <show> released lately", new-episode checks |

The roulette is deliberately NOT a chart recommender: probes are randomized,
filters exclude dead shows and one-episode experiments, and picks are random
from the surviving pool. Expect unfamiliar names. That is the product.

## Presenting a pick (always)

1. Title + publisher.
2. `why_picked` verbatim — it names the probe that surfaced the show.
3. `cadence` and `typical_episode` (commute-fit facts, computed server-side).
4. `feed_url` — the subscribable address. If the user asks "where do I listen",
   the feed URL works in any podcast app; `itunes_url` is the store page.

## Multi-pick spins

`count>1` returns distinct publishers. If the user rejects a pick, do not
re-run with the same seed — either spin again (new randomness) or add the
rejected show to `exclude`.
