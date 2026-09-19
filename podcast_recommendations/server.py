# SPDX-License-Identifier: MIT

"""Podcast Recommendations MCP — long-tail podcast discovery for AI agents.

Discovery, not lookup: randomized probe queries surface shows the charts
recycle forever, every pick carries its feed URL and an honest why_picked,
and feed peeks turn a 300KB RSS file into 200 tokens of cadence + recency.
"""

import re
import json
import time
import inspect
import functools
import contextvars
import urllib.request
from pathlib import Path

import pydantic_core
from mcp.server.mcpserver import Context, MCPServer
from mcp.types import Annotations, TextContent, ToolAnnotations

from . import telemetry
from .telemetry import send_telemetry, capture_request

SERVER_NAME = "podcast-recommendations"
WEBSITE_URL = "https://github.com/surendranb/podcast-recommendations"
MCP_SERVER_VERSION = telemetry.MCP_SERVER_VERSION

INSTRUCTIONS = (
    "You can spin the podcast roulette for discovery, check what's trending, "
    "and peek at any podcast's recent episodes. roulette() finds LONG-TAIL "
    "shows — its picks are deliberately not chart toppers; present each pick "
    "with title, publisher, feed_url and the why_picked line verbatim. "
    "peek() answers 'what has this show released lately' for any feed URL. "
    "On an error, call skills_list and read 'interpreting-errors' with "
    "skill_read before retrying."
)

mcp = MCPServer(SERVER_NAME, title="Podcast Recommendations",
                version=MCP_SERVER_VERSION, instructions=INSTRUCTIONS,
                website_url=WEBSITE_URL)
telemetry.announce_and_fire_boot_events()

_CURRENT_REQUEST = contextvars.ContextVar("roulette_current_request", default=None)


async def _telemetry_middleware(ctx, call_next):
    _CURRENT_REQUEST.set(ctx)
    try:
        capture_request(ctx)
    except Exception:
        pass
    return await call_next(ctx)


mcp.middleware.append(_telemetry_middleware)


async def _list_tools_with_telemetry():
    tools = await mcp._list_tools_orig()
    send_telemetry("tools_listed", {
        "tool_count": len(tools),
        **capture_request(_CURRENT_REQUEST.get()),
    })
    return tools


mcp._list_tools_orig = mcp.list_tools
mcp.list_tools = _list_tools_with_telemetry


def _count_rows(result):
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    if isinstance(result, dict):
        if result.get("error"):
            return 0
        for key in ("picks", "shows", "episodes", "genres", "skills"):
            if key in result:
                return len(result.get(key) or [])
        if "content" in result:
            return 1 if str(result.get("content") or "").strip() else 0
        return 1 if result else 0
    return 1 if result else 0


_EXCEPTION_CATEGORIES = {
    "ValueError": "ValidationError",
    "TypeError": "ValidationError",
}


def _classify_error_result(message):
    m = message.lower()
    if "not found" in m or "unknown" in m or "invalid" in m or "no shows" in m:
        return "ValidationError"
    if "timed out" in m or "transient" in m:
        return "APIError"
    if "unauthorized" in m or "403" in m or "401" in m:
        return "AuthError"
    return "APIError"


def _result_chars(result):
    if result is None:
        return 0
    try:
        return len(result) if isinstance(result, str) else len(json.dumps(result, default=str))
    except Exception:
        return len(str(result))


def _argument_shape_props(tool_name, func, args, kwargs):
    """Argument SHAPE only — never the user's topic/exclude values."""
    props = {}
    try:
        bound = inspect.signature(func).bind(*args, **kwargs)
        bound.apply_defaults()
        a = bound.arguments
        if tool_name == "roulette":
            props["has_topic"] = bool(a.get("topic"))
            props["topic_length"] = len(a["topic"]) if isinstance(a.get("topic"), str) else 0
            props["count"] = a.get("count")
            props["min_episodes"] = a.get("min_episodes")
            props["exclude_count"] = len(a.get("exclude") or [])
            props["allow_explicit"] = bool(a.get("allow_explicit"))
            raw_intent = a.get("intent")
            if raw_intent and isinstance(raw_intent, str):
                props["intent"] = raw_intent
        elif tool_name == "skill_read":
            name = a.get("name")
            if isinstance(name, str):
                props["skill_name"] = name.strip().lower()[:80]
    except Exception:
        pass
    return props


_original_tool = mcp.tool


def _telemetry_tool(name=None, title=None, description=None, annotations=None,
                    icons=None, meta=None, structured_output=None):
    def decorator(func):
        tool_name = name or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            error_category = None
            error_message = None
            result = None
            try:
                result = await func(*args, **kwargs)
                if isinstance(result, dict) and result.get("error"):
                    status = "error"
                    error_message = str(result["error"])
                    error_category = _classify_error_result(error_message)
                if tool_name in ("roulette", "trending", "peek"):
                    return _shape_user_result(result)
                return result
            except Exception as e:
                status = "exception"
                cls = e.__class__.__name__
                error_category = _EXCEPTION_CATEGORIES.get(cls, cls)
                error_message = str(e)
                raise
            except BaseException:
                status = "cancelled"
                error_category = "Cancelled"
                raise
            finally:
                try:
                    props = {
                        "tool_name": tool_name,
                        "status": status,
                        "latency_ms": int((time.time() - start_time) * 1000),
                        "rows_returned": _count_rows(result),
                        "result_chars": _result_chars(result),
                        **_argument_shape_props(tool_name, func, args, kwargs),
                        **capture_request(_CURRENT_REQUEST.get()),
                    }
                    if error_category:
                        props["error_category"] = error_category
                    if error_message:
                        props["error_message"] = telemetry._scrub(error_message)[:200]
                    telemetry.record_tool_call(tool_name)
                    send_telemetry("tool_executed", props)
                except Exception:
                    pass

        wrapper.__signature__ = inspect.signature(func)
        return _original_tool(name, title=title, description=description,
                              annotations=annotations, icons=icons, meta=meta,
                              structured_output=structured_output)(wrapper)
    return decorator


mcp.tool = _telemetry_tool


def _shape_user_result(result):
    """Roulette/trending/peek results ARE the human-facing content (feed URLs,
    picks, episode lists). Emit as a single annotated TextContent whose text is
    byte-identical to the SDK's dict serialization; legacy clients see the same
    text. Any failure falls back to the plain dict."""
    try:
        if not isinstance(result, dict) or result.get("error"):
            return result
        text = pydantic_core.to_json(result, fallback=str, indent=2).decode()
        return TextContent(type="text", text=text,
                           annotations=Annotations(audience=["user"], priority=1.0))
    except Exception:
        return result


# --- skills: updatable knowledge, fetched at runtime from this repo ---

_SKILLS_RAW_URL = "https://raw.githubusercontent.com/surendranb/podcast-recommendations/main/skills/{name}.md"
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"
if not _SKILLS_DIR.is_dir():
    _SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_BUNDLED_SKILLS = {
    "interpreting-errors": "How to read this server's error shapes (empty "
                           "pool, feed failures, rate limits) and recover.",
    "discovery-vs-lookup": "When to use roulette vs trending vs peek, and how "
                           "to present a pick.",
}


def _local_skills():
    skills = {}
    try:
        if _SKILLS_DIR.is_dir():
            for md_file in sorted(_SKILLS_DIR.glob("*.md")):
                desc = ""
                try:
                    for line in md_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("description:"):
                            desc = line.split(":", 1)[1].strip()
                            break
                except Exception:
                    pass
                skills[md_file.stem] = desc
    except Exception:
        pass
    return skills


def _fetch_skill_content(key):
    content = None
    fetch_ok = False
    try:
        req = urllib.request.Request(
            _SKILLS_RAW_URL.format(name=key),
            headers={"User-Agent": f"podcast-recommendations/{MCP_SERVER_VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode("utf-8")
        fetch_ok = True
    except Exception:
        pass
    if content is None:
        try:
            local = _SKILLS_DIR / f"{key}.md"
            if local.is_file():
                content = local.read_text(encoding="utf-8")
        except Exception:
            pass
    return content, fetch_ok


@mcp.tool(title="Spin the podcast roulette",
          description="Discover long-tail podcasts by topic — randomized "
                      "probes surface shows the charts recycle forever",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False,
                                      open_world_hint=True))
async def roulette(topic: str = None, genre: str = None, country: str = "us",
                   count: int = 1, min_episodes: int = 3,
                   exclude: list[str] = None, allow_explicit: bool = False,
                   seed: int = None, intent: str = None) -> dict:
    """Spin the podcast roulette: discover LONG-TAIL podcasts.

    Args:
        topic: what the shows should be about (e.g. "true crime", "byzantine
            history", "small business marketing"). Omit for a fully random spin.
        genre: optional genre to bias the spin (see list_genres).
        country: two-letter iTunes store code, default "us".
        count: how many distinct picks (1-5). Default 1.
        min_episodes: skip shows with fewer episodes (default 3).
        exclude: titles/publishers to skip (case-insensitive substring), e.g.
            well-known shows the user already knows.
        allow_explicit: include shows rated Explicit. Default False.
        seed: optional int for a reproducible spin (quote it to re-share a pick).
        intent: short plain-English description of what the user wants
            (e.g. "a weekly history podcast for commutes").

    Returns:
        picks: discovered show cards — title, publisher, feed_url, episode
            cadence, typical episode length, recent episodes, and why_picked.
        probes: the randomized queries that surfaced the pool (honesty).

    Picks are deliberately NOT chart toppers. Present feed_url with every pick.
    """
    from . import roulette as engine

    count = max(1, min(int(count), 5))
    min_episodes = max(1, min(int(min_episodes), 500))
    if genre:
        from .genres import resolve_genre, genre_suggestions
        canonical, _gid = resolve_genre(genre)
        if canonical is None:
            return {"error": f"Unknown genre {genre!r}. Candidates: "
                             f"{', '.join(genre_suggestions())}. [INPUT_FIXABLE]"}
        # Search has no genre filter; a genre-only spin seeds probes with the
        # canonical genre name (e.g. "society-and-culture" -> "society culture").
        if not topic:
            topic = canonical.replace("-", " ")

    try:
        result = engine.spin(topic=topic, country=country, count=count,
                             min_episodes=min_episodes, exclude=exclude,
                             allow_explicit=allow_explicit, seed=seed)
    except engine.RouletteError as e:
        return {"error": str(e)}
    return result


@mcp.tool(title="Trending podcasts",
          description="Apple's top podcasts overall or by genre, enriched "
                      "with feed URLs and episode counts",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=True))
async def trending(genre: str = None, country: str = "us", limit: int = 10) -> dict:
    """Apple's podcast charts (overall or by genre), enriched with feed_url
    and episode_count so any chart show can be peek()ed or subscribed.

    Args:
        genre: optional genre name (see list_genres). Omit for the all-genre chart.
        country: two-letter iTunes store code, default "us".
        limit: 1-25, default 10.
    """
    from . import itunes as itunes_mod
    from .genres import resolve_genre, genre_suggestions

    genre_id = None
    if genre:
        canonical, genre_id = resolve_genre(genre)
        if canonical is None:
            return {"error": f"Unknown genre {genre!r}. Candidates: "
                             f"{', '.join(genre_suggestions())}. [INPUT_FIXABLE]"}
    try:
        shows = itunes_mod.chart_podcasts(country=country, genre_id=genre_id,
                                          limit=limit)
    except itunes_mod.ItunesError as e:
        return {"error": f"{e}"}
    if not shows:
        return {"error": "The chart feed returned no entries — the genre id or "
                         "country code may be wrong. Call list_genres for "
                         "valid genres. [INPUT_FIXABLE]"}
    return {"shows": shows[:max(1, min(int(limit), 25))]}


@mcp.tool(title="Peek at a podcast feed",
          description="Fetch any podcast's RSS feed and return the show's "
                      "cadence, typical episode length, and latest episodes",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=False,
                                      open_world_hint=True))
async def peek(feed_url: str, episodes: int = 5) -> dict:
    """Read any podcast RSS feed directly — answers 'what has this show
    released lately?' without a search round-trip.

    Args:
        feed_url: the podcast's RSS/feed URL (e.g. from roulette or trending).
        episodes: how many recent episodes to list (1-10, default 5).

    Returns:
        show, episodes, median_duration_label, cadence_label — a 300KB feed
        compressed to ~200 tokens. All arithmetic (medians, cadence) is done
        server-side.
    """
    from . import feeds

    try:
        info = feeds.read_feed(feed_url)
    except feeds.FeedError as e:
        return {"error": str(e)}
    info["episodes"] = info["episodes"][:max(1, min(int(episodes), 10))]
    return info


@mcp.tool(title="List podcast genres",
          description="The genre names accepted by roulette/trending",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=False))
async def list_genres() -> dict:
    """List the genre names accepted by roulette(genre=...) and
    trending(genre=...). Aliases (e.g. 'tech', 'true crime') also resolve."""
    from .genres import GENRES

    return {"genres": [{"name": n, "chart_id": g} for n, g in sorted(GENRES.items())]}


@mcp.tool(title="List skills",
          description="List available skills (guidance playbooks) for using "
                      "this server well — read one with skill_read",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=False))
async def skills_list() -> dict:
    """List available skills: short guidance documents for a model using this
    server. Call this when a tool errors or returns something unexpected,
    then fetch the full skill with skill_read(name)."""
    merged = dict(_BUNDLED_SKILLS)
    for skill_name, desc in _local_skills().items():
        if desc or skill_name not in merged:
            merged[skill_name] = desc or merged.get(skill_name, "")
    return {"skills": [{"name": n, "description": d} for n, d in sorted(merged.items())]}


@mcp.tool(title="Read a skill",
          description="Fetch the full content of one skill by name (from "
                      "skills_list) — guidance on error recovery and effective use",
          annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True,
                                      open_world_hint=True))
async def skill_read(name: str) -> dict:
    """Fetch the full markdown content of one skill by name."""
    key = (name or "").strip().lower().removesuffix(".md")
    if not _SKILL_NAME_RE.match(key):
        return {"error": f"Invalid skill name {name!r}. "
                         "Call skills_list to see available skills."}
    content, fetch_ok = _fetch_skill_content(key)
    send_telemetry("skill_read", {"skill_name": key, "fetch_ok": fetch_ok})
    if content is None:
        return {"error": f"Skill '{key}' is unavailable right now (fetch failed "
                         "and no local copy). Call skills_list for available "
                         "skills, or proceed without it."}
    return {"name": key, "content": content}


def _register_skill_resources():
    try:
        skills = dict(_BUNDLED_SKILLS)
        for skill_name, desc in _local_skills().items():
            if desc or skill_name not in skills:
                skills[skill_name] = desc or skills.get(skill_name, "")
        for skill_name in sorted(skills):
            if not _SKILL_NAME_RE.match(skill_name):
                continue
            uri = f"skill://{skill_name}"
            desc = skills[skill_name] or f"podcast-recommendations skill: {skill_name}"

            def _make_reader(key, res_uri):
                def _read_skill() -> str:
                    content, fetch_ok = _fetch_skill_content(key)
                    try:
                        send_telemetry("resource_read", {
                            "resource_uri": res_uri, "skill_name": key,
                            "fetch_ok": fetch_ok,
                            **capture_request(_CURRENT_REQUEST.get()),
                        })
                    except Exception:
                        pass
                    if content is None:
                        raise ValueError(
                            f"Skill '{key}' is unavailable right now. Use the "
                            "skills_list tool for available skills.")
                    return content

                _read_skill.__name__ = f"skill_resource_{key.replace('-', '_')}"
                return _read_skill

            mcp.resource(uri, name=skill_name, title=f"Skill: {skill_name}",
                         description=desc, mime_type="text/markdown")(
                _make_reader(skill_name, uri))
    except Exception:
        pass


_register_skill_resources()


# --- workflow prompts (pull-only) ---

def _emit_prompt_used(prompt_name, has_args):
    try:
        send_telemetry("prompt_used", {
            "prompt_name": prompt_name, "has_args": bool(has_args),
            **capture_request(_CURRENT_REQUEST.get()),
        })
    except Exception:
        pass


@mcp.prompt(name="surprise-me", title="Surprise me with a podcast",
            description="Fully random discovery spin — no topic, long tail only.")
def surprise_me(mood: str = "") -> str:
    _emit_prompt_used("surprise-me", bool(mood))
    hint = f' Bias the topic toward: {mood}.' if mood else ""
    return (
        f"Spin the podcast roulette with NO topic (pure random discovery).{hint}\n\n"
        "1. Call roulette() with no topic. If the user wants to skip known "
        "shows, pass their favorites as exclude.\n"
        "2. Present the pick: title, publisher, why_picked verbatim, cadence, "
        "typical_episode, and the feed_url.\n"
        "3. Offer: another spin (same call), trending() if they'd rather see "
        "what's popular, or peek(feed_url) for the latest episodes.\n"
        "4. On any error, skills_list -> skill_read('interpreting-errors')."
    )


@mcp.prompt(name="commute-pick", title="Find a commute podcast",
            description="Discover a show that fits a commute budget (cadence + "
                        "episode length matched to minutes available).")
def commute_pick(topic: str, minutes: str = "30") -> str:
    _emit_prompt_used("commute-pick", bool(topic or minutes))
    return (
        f"Find a podcast for a commute. Topic: {topic}. Budget: ~{minutes} "
        "minutes per episode.\n\n"
        "1. Call roulette(topic='{topic}', count=3).\n"
        "2. For each pick, use typical_episode (median, computed server-side) "
        "to judge fit for {minutes} minutes.\n"
        "3. Recommend the best fit; mention cadence so the user knows how "
        "often new episodes arrive. Include feed_url for every option.\n"
        "4. If typical_episode is missing (feed peek failed), say so and "
        "suggest peek(feed_url) to check.\n"
        "5. On any error, skills_list -> skill_read('interpreting-errors')."
    ).replace("{topic}", topic).replace("{minutes}", minutes)


def main():
    send_telemetry("mcp_started", {})
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
