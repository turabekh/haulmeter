"""AI-CONTEXT: build the Tajik reviewer's working file (E3 §E3.3, D14 Session A).

WHAT THIS DOES NOT DO: it does not translate anything. That is deliberate and it is the
whole design of this script.

E3 §E3.3 asks for the catalogue to be "drafted (LLM) then **native-reviewed before
merge**", and warns in the same breath that "machine-translated strings shipped unreviewed
are worse than the gap they hide" — the audit's named anti-pattern. 1187 keys of
machine Tajik produced without a Tajik speaker is exactly that artifact: fluent-looking,
confidently wrong in places nobody can see, and expensive to un-believe once it is in a
file that looks finished. A reviewer handed it would have to check every line against the
English anyway, which is the same work as translating, minus the trust.

So what it emits is the REVIEWER'S WORKING FILE: every key, its English source, an empty
slot, and — the part that earns its keep — a `glossary_hold` flag on every string
containing trucking jargon that must stay English inside Tajik text (§12.3). That flag is
the thing a translator most reliably gets wrong and most expensively: "detention" rendered
as a Tajik word for imprisonment is not a typo, it is a claim about what the product does.

WHERE IT WRITES, and why that matters: `docs/i18n-drafts/`, which is OUTSIDE the
CI-enforced locale path. `tg` is deliberately NOT added to `LAUNCH_LOCALES` here. E3 says
CI completeness enforces tg "from the merge onward", and adding the locale before the
catalogue exists would fail the completeness gate on 1187 missing keys — turning a
schedule risk into a red suite that a later session would be tempted to silence by
merging the draft. The locale joins the list when a native reviewer has signed the file,
which is owner-track.

Run: make m15-tg-draft
"""

import json
import os
import pathlib
import re

# AI-CONTEXT: the repo root is passed IN rather than derived from __file__, because the
# api container mounts only `api/` — `parents[2]` resolves to `/` in there and the script
# fails looking for `/ui/src/...`. The make target mounts the repo and sets this, which is
# the same shape as `vapid-keys` mounting `scripts/`.
REPO = pathlib.Path(os.environ.get("REPO_ROOT") or pathlib.Path(__file__).resolve().parents[2])
EN = REPO / "ui" / "src" / "core" / "i18n" / "en.json"
OUT_DIR = REPO / "docs" / "i18n-drafts"
OUT = OUT_DIR / "tg.draft.json"

# AI-CONTEXT: the F15 default glossary plus the M15 terms E3 names. Jargon stays ENGLISH
# inside every locale's text (§12.3), so these mark strings a reviewer must not fully
# translate. Kept in sync by hand deliberately — a script that imported the live table
# would need a database to produce a document, and this has to run on a laptop.
GLOSSARY = [
    "detention", "lumper", "rate con", "BOL", "TONU", "POD", "HOS", "IFTA",
    "ELD", "DOT", "MC", "CDL", "layover", "accessorial", "reefer", "deadhead",
    "roadside", "out of service", "ELP",
]


def _has_glossary(text: str) -> list[str]:
    found = []
    lowered = text.lower()
    for term in GLOSSARY:
        if re.search(rf"\b{re.escape(term.lower())}\b", lowered):
            found.append(term)
    return found


def _has_icu(text: str) -> bool:
    """ICU placeholders and plural forms must survive translation intact (§12.5)."""
    return bool(re.search(r"\{[^}]+\}", text))


def main() -> None:
    en = json.loads(EN.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    entries = {}
    glossary_count = 0
    icu_count = 0
    for key in sorted(en):
        source = en[key]
        if not isinstance(source, str):
            continue
        terms = _has_glossary(source)
        icu = _has_icu(source)
        glossary_count += 1 if terms else 0
        icu_count += 1 if icu else 0
        entry = {"en": source, "tg": ""}
        if terms:
            entry["glossary_hold"] = terms
        if icu:
            entry["icu_placeholders"] = re.findall(r"\{[^}]+\}", source)
        entries[key] = entry

    document = {
        "_README": [
            "TAJIK DRAFT — NOT A CATALOGUE, AND NOT MERGEABLE AS ONE.",
            "This file lives outside ui/src/core/i18n/ on purpose: `tg` is not in",
            "LAUNCH_LOCALES and must not be added until a native reviewer has signed",
            "this file. Adding it early fails the CI completeness gate on every empty",
            "key, and a red suite is exactly the pressure that gets unreviewed",
            "machine translation merged.",
            "",
            "`tg` slots are EMPTY by design. Nothing here was machine-translated:",
            "1187 keys of unreviewed Tajik is the artifact E3 §E3.3 warns about, and a",
            "reviewer would have to check every line against the English regardless.",
            "",
            "`glossary_hold` marks trucking jargon that STAYS ENGLISH inside Tajik text",
            "(design-prd §12.3). 'detention' rendered as a Tajik word for imprisonment",
            "is not a typo, it is a claim about what this product does.",
            "",
            "`icu_placeholders` must survive translation exactly, including the braces.",
            "Full ICU messages only — never concatenate fragments (§12.5).",
        ],
        "_meta": {
            "source": "ui/src/core/i18n/en.json",
            "keys": len(entries),
            "keys_with_glossary_terms": glossary_count,
            "keys_with_icu_placeholders": icu_count,
            "status": "AWAITING NATIVE REVIEW — owner-track (E3 §E3.3)",
        },
        "entries": entries,
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"  {len(entries)} keys")
    print(f"  {glossary_count} carry trucking jargon that must stay English")
    print(f"  {icu_count} carry ICU placeholders that must survive intact")
    print("  tg slots are EMPTY — this is a reviewer's working file, not a translation")


if __name__ == "__main__":
    main()
