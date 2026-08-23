# SPDX-License-Identifier: MIT

"""E2E: a real MCP stdio session against the actual server binary.
Spawns `python -m podcast_recommendations` as a host would, initializes, lists
tools, and calls the surface. DO_NOT_TRACK=1 keeps telemetry silent."""

import sys
import json

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.live]


async def test_stdio_session_full_surface():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "podcast_recommendations"],
        env={"DO_NOT_TRACK": "1", "PATH": "/usr/bin:/bin"})
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            # --- tools/list ---
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"roulette", "trending", "peek", "list_genres",
                    "skills_list", "skill_read"} <= names

            # --- list_genres ---
            result = await session.call_tool("list_genres", {})
            payload = json.loads(result.content[0].text)
            assert any(g["name"] == "technology" for g in payload["genres"])

            # --- trending (live iTunes) ---
            result = await session.call_tool("trending", {"genre": "tech", "limit": 3})
            payload = json.loads(result.content[0].text)
            assert len(payload["shows"]) == 3
            assert payload["shows"][0]["rank"] == 1
            feed_url = payload["shows"][0].get("feed_url")

            # --- peek (live feed fetch) ---
            if feed_url:
                result = await session.call_tool(
                    "peek", {"feed_url": feed_url, "episodes": 3})
                payload = json.loads(result.content[0].text)
                assert payload["show"]["title"]
                assert 1 <= len(payload["episodes"]) <= 3


async def test_stdio_session_roulette_error_has_candidates():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "podcast_recommendations"],
        env={"DO_NOT_TRACK": "1", "PATH": "/usr/bin:/bin"})
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()

            # Unknown genre -> error WITH candidate list (recognition > recall)
            result = await session.call_tool(
                "trending", {"genre": "not-a-genre"})
            payload = json.loads(result.content[0].text)
            assert "error" in payload
            assert "INPUT_FIXABLE" in payload["error"]
            assert "technology" in payload["error"]
