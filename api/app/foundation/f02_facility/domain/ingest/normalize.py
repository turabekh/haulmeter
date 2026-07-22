"""AI-CONTEXT: cosmetic name normalization for ingested POIs (PRD §12, condition C).

Government feeds ship ALLCAPS codes ("REST AREA I-94 EB"); rendered raw the map
reads like a database dump and display trust collapses (design-prd §11.7 — the map
must look trustworthy). This title-cases names while preserving the things that are
NOT words: interstate/US/state-route highway codes and cardinal directions. Pure
string work, no I/O — safe to run in normalize() for every source.
"""

import re

# tokens that must stay uppercase (directions) rather than title-case to "Eb"
_DIRECTIONS = {"EB", "WB", "NB", "SB", "NE", "NW", "SE", "SW"}
# small words that stay lowercase mid-name (never first token)
_LOWER = {"at", "of", "on", "the", "and", "to", "by"}
_HIGHWAY_PREFIX = {"I", "US", "SR", "SH", "CR", "IH", "HWY", "RT", "RTE"}


def _fix_highway(token: str) -> str | None:
    # "I94" / "I-94" / "US51" / "IH35" -> "I-94" / "US-51" / "I-35"; else None
    m = re.fullmatch(r"([A-Za-z]{1,3})-?(\d+[A-Za-z]?)", token)
    if not m:
        return None
    prefix, num = m.group(1).upper(), m.group(2).upper()
    if prefix not in _HIGHWAY_PREFIX:
        return None
    if prefix in ("IH",):
        prefix = "I"  # Texas "IH" interstates render as I-
    return f"{prefix}-{num}"


def _fix_token(token: str, first: bool) -> str:
    up = token.upper()
    if up in _DIRECTIONS:
        return up
    highway = _fix_highway(token)
    if highway is not None:
        return highway
    low = token.lower()
    if not first and low in _LOWER:
        return low
    # ordinals like "#11" and pure numbers pass through; hyphenated words title each part
    if "-" in token and not token.startswith("-"):
        return "-".join(_fix_token(part, False) for part in token.split("-"))
    return token[:1].upper() + token[1:].lower() if token[:1].isalpha() else token


def normalize_name(raw: str | None) -> str:
    if not raw:
        return ""
    tokens = raw.strip().split()
    return " ".join(_fix_token(t, i == 0) for i, t in enumerate(tokens))
