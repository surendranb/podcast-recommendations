---
description: Setup, client harness configuration, and zero-key quickstart guide for podcast-recommendations.
---

# Setting Up Podcast Recommendations MCP Server

A zero-configuration, long-tail podcast discovery, topic recommendation, and RSS feed inspection engine for AI agents.

Official Repository: [github.com/surendranb/podcast-recommendations](https://github.com/surendranb/podcast-recommendations)

---

## 1. Quickstart (Zero API Keys Required)

`podcast-recommendations` probes open podcast directories:
- **Apple Podcasts / iTunes Search API**: Global catalog indexing millions of podcast shows and genre charts
- **Direct RSS Feed Parsing**: Real-time inspection of podcast XML feeds for episode cadence, durations, and freshness

**Zero API keys, zero accounts, and zero credit cards required.**

---

## 2. Client Configuration

### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "podcast-recommendations": {
      "command": "uvx",
      "args": ["podcast-recommendations"]
    }
  }
}
```

Or via NPX:
```json
{
  "mcpServers": {
    "podcast-recommendations": {
      "command": "npx",
      "args": ["-y", "podcast-recommendations"]
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "podcast-recommendations": {
      "command": "uvx",
      "args": ["podcast-recommendations"]
    }
  }
}
```

### Command Line / CLI Testing
```bash
uvx podcast-recommendations
```

---

## 3. Core Tools & Workflow

1. **`roulette(topic="artificial intelligence", genre="technology")`**:
   Surfaces long-tail shows via randomized probes with computed episode cadence and duration filters.
2. **`trending(genre="technology", limit=10)`**:
   Inspects current popular shows across iTunes genre charts.
3. **`peek(feed_url="https://...")`**:
   Inspects recent episodes directly from the RSS feed, returning publication cadence and episode lengths.
4. **`list_genres()`**:
   Lists accepted genre names and chart IDs.
5. **`skills_list()` / `skill_read(name="discovery-vs-lookup")`**:
   Guidance on presenting picks (why_picked, feed_url, commute fit) and interpreting errors.

---

## 4. Troubleshooting & Operational Guidance

- **Empty Candidate Pool**: If `roulette` returns "No shows survived the filters", loosen filters by lowering `min_episodes` or setting `allow_explicit=True`.
- **Feed URL vs Store URL**: `peek` requires the direct RSS `feed_url` (returned by roulette/trending), not an iTunes store page URL.
- **Update Verification**: Call `check_for_updates()` to check PyPI for newer versions and upgrade commands.
- **Dynamic Skills**: Call `skill_read(name='interpreting-errors')` for detailed error code guidance.
