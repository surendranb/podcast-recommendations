# SPDX-License-Identifier: MIT

"""Apple podcast genre map (chart endpoint ids) + fuzzy resolution."""

# Verified stable Apple genre ids for the chart RSS endpoint
# (https://itunes.apple.com/{cc}/rss/toppodcasts/genre={id}/json).
GENRES = {
    "arts": 1301,
    "comedy": 1303,
    "education": 1304,
    "kids-and-family": 1305,
    "health-and-fitness": 1306,
    "tv-and-film": 1307,
    "music": 1308,
    "news": 1309,
    "religion-and-spirituality": 1310,
    "science": 1311,
    "sports": 1312,
    "technology": 1313,
    "business": 1314,
    "games-and-hobbies": 1315,
    "society-and-culture": 1316,
}

_ALIASES = {
    "kids": "kids-and-family", "family": "kids-and-family",
    "health": "health-and-fitness", "fitness": "health-and-fitness",
    "film": "tv-and-film", "tv": "tv-and-film", "movies": "tv-and-film",
    "politics": "news", "world": "news",
    "spirituality": "religion-and-spirituality", "religion": "religion-and-spirituality",
    "medicine": "science", "sci": "science",
    "sport": "sports", "recreation": "sports",
    "tech": "technology",
    "games": "games-and-hobbies", "hobbies": "games-and-hobbies", "gaming": "games-and-hobbies",
    "culture": "society-and-culture", "society": "society-and-culture", "history": "society-and-culture",
    "true-crime": "society-and-culture", "crime": "society-and-culture", "documentary": "society-and-culture",
    "business": "business", "finance": "business",
    "comedy": "comedy", "arts": "arts", "education": "education",
    "learning": "education", "music": "music",
}


def resolve_genre(name):
    """'true crime' -> ('society-and-culture', 1316). Returns (canonical, id)
    or (None, None). Fuzzy: prefix/substring match over canonical names."""
    if not name:
        return None, None
    key = name.strip().lower().replace("_", "-").replace(" ", "-")
    if key in GENRES:
        return key, GENRES[key]
    if key in _ALIASES:
        alias = _ALIASES[key]
        return alias, GENRES[alias]
    for canonical, gid in GENRES.items():
        if canonical.startswith(key) or key.startswith(canonical):
            return canonical, gid
    for alias, canonical in _ALIASES.items():
        if alias.startswith(key) or key.startswith(alias):
            return canonical, GENRES[canonical]
    return None, None


def genre_suggestions():
    return sorted(GENRES.keys())
