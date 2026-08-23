# Podcast Recommendations — Podcast Discovery MCP 🎰🎙️

[![CI](https://github.com/surendranb/podcast-recommendations/actions/workflows/package-checks.yml/badge.svg)](https://github.com/surendranb/podcast-recommendations/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/podcast-recommendations.svg)](https://pypi.org/project/podcast-recommendations/)

> **Podcast recommendations beyond the charts: long-tail podcast discovery, recommendations, and random spins — randomized probe queries surface shows the charts recycle forever, and every pick carries its feed URL, cadence, and typical episode length.**

Ask any agent: *"find me a podcast about Byzantine history I haven't heard of"*
or *"surprise me with a podcast"* — `podcast-recommendations` is the tool that answers.
**Zero API keys, zero configuration.** Built on Apple's keyless iTunes podcast
endpoints (verified) and direct RSS feed reads: a 300KB feed becomes ~200
tokens of show intelligence, all arithmetic done server-side.

## Why this exists

Search APIs return the same chart toppers for every query; LLMs recommend the
same famous podcasts everyone already knows. `podcast-recommendations` fixes discovery:

- **Randomized probe queries** ("lesser known true crime", "history
  dispatches") fish the long tail instead of recycling the top 10.
- **Hard filters** remove dead shows, one-episode experiments, explicit
  content (opt-in), and anything on your exclude list — with publisher-level
  dedupe so multi-picks stay diverse.
- **Feed peeks** compute cadence (daily/weekly/…) and typical episode length
  server-side — commute-fit facts the model never has to calculate.
- **Honest attribution**: every pick says which probe surfaced it. Discovery
  you can trust.

## Tools

| Tool | What it does |
|---|---|
| `roulette` | The discovery spin: long-tail picks by topic (or fully random), 1–5 distinct shows |
| `trending` | Apple's charts overall or by genre, enriched with feed URLs + episode counts |
| `peek` | Read any podcast RSS feed → cadence, typical length, latest episodes |
| `list_genres` | Genre names accepted by `roulette`/`trending` |
| `skills_list` / `skill_read` | Updatable usage playbooks (fetched from this repo at runtime) |

Plus prompts: `surprise-me`, `commute-pick`.

## Quickstart

```bash
# 1-Line Universal Installer (auto-configures Claude Desktop, Cursor, Claude Code, VS Code, ...)
curl -fsSL "https://podcast-recommendations.builditwithai.xyz/install" | bash

# Or run directly via your preferred runtime:
uvx podcast-recommendations
npx -y podcast-recommendations
```

## Example

```
User:  find me a podcast about true crime I haven't heard of

roulette(topic="true crime", exclude=["Serial", "Casefile"])
→ picks: [{
     title: "Milk and Murder", episode_count: 23,
     cadence: "biweekly", typical_episode: "24m",
     why_picked: "surfaced by the probe query “true crime chronicles”…",
     feed_url: "https://www.spreaker.com/show/4529395/episodes/feed",
     recent_episodes: ["24. Lindsey Baum - Part Two (2022-05-11, 10m)", ...] }]
```

## Telemetry & privacy

Anonymous usage telemetry (no PII, no queries, no paths) via the fleet
standard (schema v2, dual-endpoint fallback). Opt out any time:
`PODCAST_RECOMMENDATIONS_TELEMETRY=false` or `DO_NOT_TRACK=1`.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
DO_NOT_TRACK=1 .venv/bin/python -m pytest tests/ -q   # unit + live + e2e
```

Live tests hit the real iTunes endpoints and real podcast feeds; they skip
themselves when offline.

## License

MIT
